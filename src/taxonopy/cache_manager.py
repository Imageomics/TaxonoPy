"""Caching system for TaxonoPy.

This module provides a comprehensive caching system for storing and retrieving
Python objects during TaxonoPy's taxonomic resolution workflow. It uses a
checksum-based approach to determine when cache entries should be invalidated,
making it particularly suitable for caching results derived from file operations.

The system is designed to be extensible, with support for different serialization
formats planned for the future.
"""

import os
import hashlib
import functools
import inspect
import logging
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from diskcache import Cache

from taxonopy.config import config

logger = logging.getLogger(__name__)

# Global cache instance: Use a module-level singleton so all callers share the same diskcache.Cache handle for a given directory, avoiding repeated SQLite-backed initialization overhead. 
# DiskCache documents Cache objects as thread-safe and  shareable between threads. If the configured cache directory changes, this module closes the prior handle and opens a new Cache for the new directory.

_cache_instance: Optional[Cache] = None
_cache_path: Optional[Path] = None
META_SUFFIX = "::meta"
META_VERSION = 1
FINGERPRINT_SUFFIX_LENGTH = 16

def _close_cache() -> None:
    """Close the active diskcache instance."""
    global _cache_instance, _cache_path
    if _cache_instance is not None:
        _cache_instance.close()
        _cache_instance = None
        _cache_path = None

def get_cache() -> Cache:
    """Return a diskcache instance rooted at the current config cache dir."""
    global _cache_instance, _cache_path
    cache_dir = Path(config.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if _cache_instance is None or _cache_path != cache_dir:
        if _cache_instance is not None:
            _cache_instance.close()
        _cache_instance = Cache(directory=str(cache_dir))
        _cache_path = cache_dir
    return _cache_instance

def set_cache_namespace(namespace: str) -> Path:
    """Set the effective cache directory to a namespace under the base dir."""
    base_dir = Path(config.cache_base_dir)
    target_dir = base_dir / namespace
    config.cache_dir = str(target_dir)
    _close_cache()
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir

def get_cache_directory() -> Path:
    """Return the current cache directory as a Path."""
    cache_dir = Path(config.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir

def compute_checksum(file_paths: List[str]) -> str:
    """Compute a SHA-256 checksum for a list of file paths.
    
    Args:
        file_paths: List of file paths to include in the checksum
        
    Returns:
        A SHA-256 hex digest representing the content of the files
    """
    if not file_paths:
        return ""
        
    hash_obj = hashlib.sha256()
    for file_path in sorted(file_paths):
        try:
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    hash_obj.update(chunk)
        except (FileNotFoundError, PermissionError) as e:
            logger.warning(f"Could not include file in checksum: {file_path}, {str(e)}")
            
    return hash_obj.hexdigest()

def compute_file_metadata_hash(file_paths: List[str]) -> str:
    """Compute a hash using file paths and metadata (size + mtime).
    
    Args:
        file_paths: List of file paths to include in the fingerprint

    Returns:
        Hex digest summarizing the file metadata
    """
    if not file_paths:
        return ""

    hash_obj = hashlib.sha256()
    for file_path in sorted(file_paths):
        try:
            stat_info = os.stat(file_path)
        except (FileNotFoundError, PermissionError) as exc:
            logger.warning(f"Could not stat file for fingerprint: {file_path}, {exc}")
            continue
        hash_obj.update(file_path.encode("utf-8"))
        hash_obj.update(str(stat_info.st_size).encode("utf-8"))
        hash_obj.update(str(int(stat_info.st_mtime_ns)).encode("utf-8"))
    return hash_obj.hexdigest()

def configure_cache_namespace(
    command: str,
    version: str,
    file_paths: List[str],
    fingerprint: Optional[str] = None,
) -> Path:
    """Set cache namespace derived from command/version/input fingerprint.
    
    Args:
        command: Name of the command owning the cache (e.g., "resolve")
        version: TaxonoPy version string
        file_paths: List of files describing the input dataset
        fingerprint: Optional precomputed fingerprint override
    
    Returns:
        Path to the configured namespace directory
    """
    if fingerprint is None:
        fingerprint = compute_file_metadata_hash(file_paths)
    suffix = fingerprint[:FINGERPRINT_SUFFIX_LENGTH] if fingerprint else "default"
    namespace = f"{command}_v{version}_{suffix}"
    return set_cache_namespace(namespace)

def save_cache(key: str, obj: Any, checksum: str, 
              metadata: Optional[Dict[str, Any]] = None) -> None:
    """Save an object to the cache.
    
    Args:
        key: Cache key for the object
        obj: The object to cache
        checksum: Checksum value for validation
        metadata: Additional metadata to store with the cache entry
    """
    cache = get_cache()
    value_key = key
    meta_key = f"{key}{META_SUFFIX}"

    meta = {
        "checksum": checksum,
        "timestamp": datetime.now().isoformat(),
        "serializer": "diskcache",
        "version": META_VERSION,
    }
    if metadata:
        meta.update(metadata)

    try:
        cache.set(value_key, obj)
        cache.set(meta_key, meta)
        logger.debug(f"Saved object to cache: {key}")
    except Exception as exc:
        logger.error(f"Failed to save to cache: {key}, {exc}")
        try:
            cache.delete(value_key)
        except Exception:
            pass
        try:
            cache.delete(meta_key)
        except Exception:
            pass

def load_cache(key: str, expected_checksum: str, 
              max_age: Optional[int] = None) -> Optional[Any]:
    """Load an object from the cache if valid.
    
    Args:
        key: Cache key for the object
        expected_checksum: Expected checksum for validation
        max_age: Maximum age in seconds, or None for no limit
        
    Returns:
        The cached object if valid, otherwise None
    """
    cache = get_cache()
    value_key = key
    meta_key = f"{key}{META_SUFFIX}"
    
    meta = cache.get(meta_key, default=None)
    if meta is None:
        logger.debug(f"Cache miss (metadata not found): {key}")
        return None
    
    try:
        if meta.get("checksum") != expected_checksum:
            logger.debug(f"Cache miss (checksum mismatch): {key}")
            return None
        
        # Use configured max_age if not provided
        if max_age is None:
            max_age = config.cache_max_age


        if max_age is not None:
            timestamp = datetime.fromisoformat(meta.get("timestamp", "2000-01-01T00:00:00"))
            age = (datetime.now() - timestamp).total_seconds()
            if age > max_age:
                logger.debug(f"Cache miss (expired after {age:.1f}s): {key}")
                return None
        
        try:
            obj = cache.get(value_key, default=None)
            if obj is None:
                logger.debug(f"Cache miss (value not found): {key}")
                return None
            logger.debug(f"Cache hit: {key}")
            return obj
        except Exception as exc:
            logger.warning(f"Failed to load cached object: {key}, {exc}")
            return None
                
    except Exception as exc:
        logger.warning(f"Unexpected error loading cache: {key}, {exc}")
        return None

def clear_cache(pattern: Optional[str] = None) -> int:
    """Clear cache entries matching the given pattern.
    
    Args:
        pattern: Optional filename pattern to match, or None for all files
        
    Returns:
        Number of files removed
    """
    cache = get_cache()
    if pattern is None:
        count = len(cache)
        cache.clear()
        logger.info(f"Cleared {count} cache entries")
        return count

    keys_to_delete = [key for key in cache if pattern in str(key)]
    for key in keys_to_delete:
        try:
            del cache[key]
        except KeyError:
            continue
    logger.info(f"Cleared {len(keys_to_delete)} cache entries matching '{pattern}'")
    return len(keys_to_delete)

def _classify_cache_key(key: str) -> str:
    """Return the cache object category based on the key prefix."""
    if key.startswith("resolution_chain_"):
        return "resolution_chain"
    if key.startswith("taxonomic_entries"):
        return "taxonomic_entries"
    if key.startswith("entry_groups"):
        return "entry_groups"
    return "other"

def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the cache.
    
    Returns:
        Dictionary with cache statistics
    """
    cache_dir = get_cache_directory()
    stats: Dict[str, Any] = {
        "namespace": str(cache_dir),
        "total_size_bytes": 0,
        "db_file_count": 0,
        "entry_count": 0,
        "meta_count": 0,
        "prefix_counts": {},
    }
    
    try:
        for root, _, files in os.walk(cache_dir):
            for file_name in files:
                stats["db_file_count"] += 1
                file_path = Path(root) / file_name
                try:
                    stats["total_size_bytes"] += file_path.stat().st_size
                except OSError:
                    continue

        cache = get_cache()
        prefix_counts: Dict[str, int] = defaultdict(int)
        for key in cache:
            key_str = str(key)
            if key_str.endswith(META_SUFFIX):
                stats["meta_count"] += 1
                continue
            stats["entry_count"] += 1
            prefix = _classify_cache_key(key_str)
            prefix_counts[prefix] += 1

        stats["prefix_counts"] = dict(prefix_counts)
    except Exception as exc:
        logger.error(f"Error getting cache stats: {exc}")
    
    return stats

def cached(
    prefix: Optional[str] = None,
    key_args: Optional[List[str]] = None,
    max_age: Optional[int] = None,
    include_all_args: bool = False
):
    """Decorator to cache function results based on arguments.
    
    Args:
        prefix: Optional prefix for the cache key (defaults to function name)
        key_args: List of argument names to include in the cache key
        max_age: Maximum age of cache in seconds
        include_all_args: Whether to include all arguments in the cache key
        
    Returns:
        Decorated function with caching
    """
    def decorator(func: Callable) -> Callable:
        # Use function name as prefix if not provided
        func_prefix = prefix or func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract refresh_cache from kwargs if present
            refresh = kwargs.pop('refresh_cache', False) if 'refresh_cache' in kwargs else False
            
            # Generate cache key from arguments
            cache_key, file_checksum = _create_cache_key(
                func, func_prefix, args, kwargs, key_args, include_all_args
            )

            # Try to load from cache if not refreshing
            if not refresh and file_checksum:
                _max_age = max_age if max_age is not None else config.cache_max_age
                cached_result = load_cache(cache_key, file_checksum, max_age=_max_age)
                if cached_result is not None:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return cached_result

            # Call the original function
            start_time = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            # Save the result to cache
            if file_checksum:
                metadata = {
                    "function": func.__name__,
                    "execution_time": elapsed
                }
                save_cache(cache_key, result, file_checksum, metadata=metadata)
                logger.debug(f"Cached result for {func.__name__} (took {elapsed:.2f}s)")
            
            return result
        
        # Add a method to clear this function's cache
        def clear_function_cache() -> int:
            """Clear all cache entries for this function."""
            return clear_cache(func_prefix)
        
        # Attach the clear method to the wrapped function
        wrapper.clear_cache = clear_function_cache
        
        return wrapper
    
    return decorator

def _create_cache_key(
    func: Callable,
    prefix: str,
    args: Tuple,
    kwargs: Dict[str, Any],
    key_args: Optional[List[str]],
    include_all_args: bool
) -> Tuple[str, str]:
    """Generate a cache key and checksum for a function call.
    
    Args:
        func: The function being called
        prefix: Prefix for the cache key
        args: Positional arguments
        kwargs: Keyword arguments
        key_args: Specific argument names to include in key
        include_all_args: Whether to include all arguments
        
    Returns:
        Tuple of (cache_key, file_checksum)
    """
    # Get the function signature
    sig = inspect.signature(func)
    
    # Bind arguments to parameters
    try:
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        arg_dict = dict(bound.arguments)
    except TypeError:
        # If binding fails, fall back to a simpler approach
        arg_dict = {f"arg{i}": arg for i, arg in enumerate(args)}
        arg_dict.update(kwargs)
    
    # Filter arguments if key_args is specified
    if key_args and not include_all_args:
        arg_dict = {k: v for k, v in arg_dict.items() if k in key_args}
    
    # Extract file paths for checksum
    file_paths = []
    for k, v in list(arg_dict.items()):
        if isinstance(v, (str, Path)) and os.path.exists(v):
            if os.path.isfile(v):
                file_paths.append(str(v))
            elif os.path.isdir(v):
                # For directories, include all files in checksum
                for root, _, files in os.walk(v):
                    for file in files:
                        file_paths.append(os.path.join(root, file))
            
            # Replace path with a placeholder in arg_dict to avoid long keys
            arg_dict[k] = f"__PATH__:{os.path.basename(v)}"
    
    # Create a deterministic representation of arguments
    if include_all_args or key_args:
        arg_str = repr(sorted(arg_dict.items()))
        arg_hash = hashlib.md5(arg_str.encode()).hexdigest()
        cache_key = f"{prefix}_{arg_hash}"
    else:
        # If no specific arguments were requested, use just the prefix
        cache_key = prefix
    
    # Compute checksum of files
    file_checksum = compute_checksum(file_paths) if file_paths else ""
    
    return cache_key, file_checksum

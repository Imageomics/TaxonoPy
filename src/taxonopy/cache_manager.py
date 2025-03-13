"""Caching system for TaxonoPy.

This module provides a comprehensive caching system for storing and retrieving
Python objects during TaxonoPy's taxonomic resolution workflow. It uses a
checksum-based approach to determine when cache entries should be invalidated,
making it particularly suitable for caching results derived from file operations.

The system is designed to be extensible, with support for different serialization
formats planned for the future.
"""

import os
import json
import pickle
import hashlib
import functools
import inspect
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, Callable
from taxonopy.config import config

logger = logging.getLogger(__name__)

# Define cache directory
CACHE_DIR = Path(config.cache_dir)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def get_cache_file_path(key: str) -> Path:
    """Return the path for the cached pickle file for a given key."""
    return CACHE_DIR / f"{key}.pkl"

def get_meta_file_path(key: str) -> Path:
    """Return the path for the cache metadata file for a given key."""
    return CACHE_DIR / f"{key}.meta.json"

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

def save_cache(key: str, obj: Any, checksum: str, 
              metadata: Optional[Dict[str, Any]] = None) -> None:
    """Save an object to the cache.
    
    Args:
        key: Cache key for the object
        obj: The object to cache
        checksum: Checksum value for validation
        metadata: Additional metadata to store with the cache entry
    """
    meta_path = get_meta_file_path(key)
    data_path = get_cache_file_path(key)
    
    # Prepare metadata
    meta = {
        "checksum": checksum,
        "timestamp": datetime.now().isoformat(),
        "serializer": "pickle"  # For future extensibility
    }
    
    # Add any additional metadata
    if metadata:
        meta.update(metadata)
    
    try:
        # Save metadata first
        with open(meta_path, "w") as f:
            json.dump(meta, f)
        
        # Then save the object
        with open(data_path, "wb") as f:
            pickle.dump(obj, f)
            
        logger.debug(f"Saved object to cache: {key}")
    except Exception as e:
        logger.error(f"Failed to save to cache: {key}, {str(e)}")
        # Clean up partial writes
        if meta_path.exists():
            os.unlink(meta_path)
        if data_path.exists():
            os.unlink(data_path)

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
    meta_path = get_meta_file_path(key)
    data_path = get_cache_file_path(key)
    
    # Check if cache files exist
    if not (meta_path.exists() and data_path.exists()):
        logger.debug(f"Cache miss (files not found): {key}")
        return None
    
    try:
        # Load metadata
        with open(meta_path, "r") as f:
            try:
                meta = json.load(f)
            except json.JSONDecodeError:
                logger.warning(f"Invalid metadata format for cache key: {key}")
                return None
        
        # Check checksum
        if meta.get("checksum") != expected_checksum:
            logger.debug(f"Cache miss (checksum mismatch): {key}")
            return None
        
        # Check age if specified
        # Use configured max_age if not provided
        if max_age is None:
            max_age = config.cache_max_age


        if max_age is not None:
            timestamp = datetime.fromisoformat(meta.get("timestamp", "2000-01-01T00:00:00"))
            age = (datetime.now() - timestamp).total_seconds()
            if age > max_age:
                logger.debug(f"Cache miss (expired after {age:.1f}s): {key}")
                return None
        
        # Load the object
        with open(data_path, "rb") as f:
            try:
                obj = pickle.load(f)
                logger.debug(f"Cache hit: {key}")
                return obj
            except (pickle.PickleError, EOFError, AttributeError) as e:
                logger.warning(f"Failed to load cached object: {key}, {str(e)}")
                return None
                
    except Exception as e:
        logger.warning(f"Unexpected error loading cache: {key}, {str(e)}")
        return None

def clear_cache(pattern: Optional[str] = None) -> int:
    """Clear cache entries matching the given pattern.
    
    Args:
        pattern: Optional filename pattern to match, or None for all files
        
    Returns:
        Number of files removed
    """
    count = 0
    
    try:
        for item in os.scandir(CACHE_DIR):
            if item.is_file():
                if pattern is None or pattern in item.name:
                    os.unlink(item.path)
                    count += 1
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
    
    logger.info(f"Cleared {count} cache files")
    return count

def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the cache.
    
    Returns:
        Dictionary with cache statistics
    """
    stats = {
        "total_size_bytes": 0,
        "object_count": 0,
        "file_count": 0,
        "oldest_cache_age": None,
        "newest_cache_age": None,
    }
    
    try:
        timestamps = []
        
        for item in os.scandir(CACHE_DIR):
            if item.is_file():
                stats["file_count"] += 1
                stats["total_size_bytes"] += item.stat().st_size
                
                if item.name.endswith('.pkl'):
                    stats["object_count"] += 1
                    timestamps.append(item.stat().st_mtime)
        
        if timestamps:
            oldest = datetime.fromtimestamp(min(timestamps))
            newest = datetime.fromtimestamp(max(timestamps))
            now = datetime.now()
            
            stats["oldest_cache_age"] = str(now - oldest)
            stats["newest_cache_age"] = str(now - newest)
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
    
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

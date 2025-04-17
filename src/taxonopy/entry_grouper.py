"""Entry grouping for TaxonoPy.

This module provides functions for grouping TaxonomicEntry objects
into EntryGroupRef objects based on identical taxonomic data.
"""

import hashlib
from typing import Dict, Set, List, Iterator, Tuple, Optional

from tqdm import tqdm
import logging

from taxonopy.types.data_classes import TaxonomicEntry, EntryGroupRef
from taxonopy.stats_collector import DatasetStats
from taxonopy.cache_manager import cached
from taxonopy.input_parser import parse_input_list
from taxonopy.config import config
from taxonopy.constants import TAXONOMIC_RANKS

logger = logging.getLogger(__name__)

def group_entries(
    entries: List[TaxonomicEntry],
    total_count: Optional[int] = None,
    stats_collector: Optional[DatasetStats] = None
) -> Dict[str, EntryGroupRef]:
    """Group taxonomic entries based on identical taxonomic data.
    
    Args:
        entries: List of taxonomic entries
        total_count: Total number of entries (optional, for progress bar)
        stats_collector: Optional stats collector to update during processing
        
    Returns:
        Dictionary mapping group keys (str) to EntryGroupRef objects.
    """
    # Use a tuple of taxonomic fields as the grouping key.
    groups: Dict[Tuple[str, ...], Set[str]] = {}
    group_taxonomy: Dict[Tuple[str, ...], Dict[str, Optional[str]]] = {}

    # Create a progress bar if total_count is provided.
    entries_iter = tqdm(entries, total=total_count, desc="Grouping entries") if total_count else entries

    for entry in entries_iter:
        if stats_collector:
            stats_collector.update_from_entry(entry)
        
        # Build a grouping key tuple (empty string if field is None)
        grouping_key = tuple(
             (getattr(entry, field) or "").strip().lower() 
             for field in TAXONOMIC_RANKS + ['scientific_name'] # Consistent order
        )

        if grouping_key not in groups:
            groups[grouping_key] = set()
            group_taxonomy[grouping_key] = {
                'kingdom': entry.kingdom,
                'phylum': entry.phylum,
                'class_': entry.class_,
                'order': entry.order,
                'family': entry.family,
                'genus': entry.genus,
                'species': entry.species,
                'scientific_name': entry.scientific_name
            }
        
        groups[grouping_key].add(entry.uuid)

    # Build the final index map using the EntryGroupRef's key property
    group_index = {}
    for external_key, uuids in groups.items():
        entry_group = EntryGroupRef(
            entry_uuids=frozenset(uuids),
            **group_taxonomy[external_key]
        )
        group_index[entry_group.key] = entry_group
        
    return group_index

def count_entries_in_input(input_path: str) -> int:
    """Count the total number of entries in the input files.
    
    This is used to provide an accurate progress bar for grouping.
    
    Args:
        input_path: Path to input directory or file
        
    Returns:
        Total number of entries
    """
    import polars as pl
    from taxonopy.input_parser import find_input_files
    
    file_paths = find_input_files(input_path)
    total_count = 0
    
    for file_path in tqdm(file_paths, desc="Counting entries"):
        if file_path.endswith(".parquet"):
            # For Parquet we can efficiently get the count
            df = pl.scan_parquet(file_path)
            total_count += df.select(pl.count()).collect().item()
        else:
            # For CSV we need to read the whole file
            df = pl.read_csv(file_path)
            total_count += len(df)
    
    return total_count


@cached(
    prefix="entry_groups",
    key_args=["input_path"],
    max_age=config.cache_max_age
)
def create_entry_groups(input_path: str, 
                        total_count: Optional[int] = None, 
                        stats_collector: Optional[DatasetStats] = None
                       ) -> Tuple[List[EntryGroupRef], Dict[str, EntryGroupRef]]:
    """Create entry groups from taxonomic entries.
    
    This is the main entry point for the module. It parses input,
    groups entries, and returns both a list and an index map.
    
    Args:
        input_path: Path to input directory or file
        total_count: Total number of entries (optional, for progress bar)
        stats_collector: Optional stats collector to update during processing
        
    Returns:
        Tuple containing:
          - List of EntryGroupRef objects
          - Dictionary mapping group keys (str) to EntryGroupRef objects
    """
    # Get taxonomic entries directly from the cached parser
    # Note: parse_input_list itself is cached
    entries = parse_input_list(input_path) 
    
    # Update stats if collector is provided
    # if stats_collector:
    #     stats_collector.update_from_entries(entries)
    
    # Group entries by taxonomic data
    entry_group_index: Dict[str, EntryGroupRef] = group_entries(entries, total_count, stats_collector)
    
    # Convert values of the map to a list for the first part of the tuple
    entry_groups_list = list(entry_group_index.values())
    
    return entry_groups_list, entry_group_index

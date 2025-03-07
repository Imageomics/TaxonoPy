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


def generate_group_key(entry: TaxonomicEntry) -> str:
    """Generate a unique key for a taxonomic entry based on its taxonomic data.
    
    Args:
        entry: A taxonomic entry
        
    Returns:
        A hash string that uniquely identifies the taxonomic data
    """
    # Concatenate all taxonomic fields in a consistent order
    tax_data = "|".join([
        str(entry.kingdom or ""),
        str(entry.phylum or ""),
        str(entry.class_ or ""),
        str(entry.order or ""),
        str(entry.family or ""),
        str(entry.genus or ""),
        str(entry.species or ""),
        str(entry.scientific_name or ""),
    ]).lower()  # Convert to lowercase for case-insensitive grouping
    
    # Generate a SHA-256 hash of the taxonomic data
    return hashlib.sha256(tax_data.encode()).hexdigest()


def group_entries(entries: Iterator[TaxonomicEntry], total_count: Optional[int] = None, 
                  stats_collector: Optional[DatasetStats] = None) -> Dict[str, EntryGroupRef]:
    """Group taxonomic entries based on identical taxonomic data.
    
    Args:
        entries: Iterator of taxonomic entries
        total_count: Total number of entries (optional, for progress bar)
        stats_collector: Optional stats collector to update during processing
        
    Returns:
        Dictionary mapping group keys to EntryGroupRef objects
    """
    # Dictionary for building groups: key -> set of entry UUIDs
    groups: Dict[str, Set[str]] = {}
    
    # Dictionary for storing taxonomic data for each group: key -> taxonomic fields
    group_taxonomy: Dict[str, Dict[str, Optional[str]]] = {}
    
    # Create a progress bar if total_count is provided
    entries_iter = tqdm(entries, total=total_count, desc="Grouping entries") if total_count else entries
    
    # Group entries by taxonomic data
    for entry in entries_iter:
        # Update statistics if a collector is provided
        if stats_collector:
            stats_collector.update_from_entry(entry)
            
        group_key = generate_group_key(entry)
        
        # Initialize new groups
        if group_key not in groups:
            groups[group_key] = set()
            # Store the taxonomic data for this group
            group_taxonomy[group_key] = {
                'kingdom': entry.kingdom,
                'phylum': entry.phylum,
                'class_': entry.class_,
                'order': entry.order,
                'family': entry.family,
                'genus': entry.genus,
                'species': entry.species,
                'scientific_name': entry.scientific_name
            }
        
        # Add this entry's UUID to the group
        groups[group_key].add(entry.uuid)
    
    # Convert to EntryGroupRef objects
    return {
        key: EntryGroupRef(
            key=key,
            entry_uuids=frozenset(uuids),
            **group_taxonomy[key]  # Unpack taxonomic data into the constructor
        )
        for key, uuids in groups.items()
    }


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


def create_entry_groups(entries: Iterator[TaxonomicEntry], total_count: Optional[int] = None,
                        stats_collector: Optional[DatasetStats] = None) -> List[EntryGroupRef]:
    """Create entry groups from taxonomic entries.
    
    This is the main entry point for the module.
    
    Args:
        entries: Iterator of taxonomic entries
        total_count: Total number of entries (optional, for progress bar)
        stats_collector: Optional stats collector to update during processing
        
    Returns:
        List of EntryGroupRef objects
    """
    # Group entries by taxonomic data
    groups = group_entries(entries, total_count, stats_collector)
    
    # Convert to list of EntryGroupRef objects
    return list(groups.values())

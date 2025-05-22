"""Statistics collection for TaxonoPy.

This module provides functions for collecting and reporting statistics
about taxonomic data during processing.
"""

from typing import Dict, List, Set, Counter as CounterType
from collections import Counter

from taxonopy.types.data_classes import TaxonomicEntry, EntryGroupRef


class DatasetStats:
    """Statistics about the processed dataset."""
    
    def __init__(self):
        """Initialize statistics collectors."""
        self.entry_count = 0
        self.entry_count_by_source: CounterType[str] = Counter()
        self.null_counts: Dict[str, int] = {
            "kingdom": 0,
            "phylum": 0,
            "class_": 0,
            "order": 0,
            "family": 0,
            "genus": 0,
            "species": 0,
            "scientific_name": 0,
            "common_name": 0,
            "source_id": 0
        }
        self.entry_group_count = 0
    
    def update_from_entry(self, entry: TaxonomicEntry) -> None:
        """Update statistics from a taxonomic entry.
        
        Args:
            entry: A taxonomic entry
        """
        self.entry_count += 1
        self.entry_count_by_source[entry.source_dataset or "unknown"] += 1
        
        # Count nulls
        for field in self.null_counts:
            if field == "class_":
                if not getattr(entry, field):
                    self.null_counts[field] += 1
            else:
                if not getattr(entry, field):
                    self.null_counts[field] += 1
    def update_from_entries(self, entries: List[TaxonomicEntry]) -> None:
        """Update statistics from a list of entries.
        
        Args:
            entries: List of taxonomic entries
        """
        for entry in entries:
            self.update_from_entry(entry)
    
    def update_from_entry_groups(self, entry_groups: List[EntryGroupRef]) -> None:
        """Update statistics from entry groups.
        
        Args:
            entry_groups: List of entry group references
        """
        self.entry_group_count = len(entry_groups)
    
    def generate_report(self) -> str:
        """Generate a formatted report of the statistics."""
        report = []
        report.append("=== Dataset Statistics ===")
        report.append(f"Total entries: {self.entry_count:,}")
        report.append(f"Total unique taxonomic groups: {self.entry_group_count:,}")
        
        # Report entries by source
        report.append("\nEntries by source:")
        for source, count in sorted(self.entry_count_by_source.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / self.entry_count * 100) if self.entry_count > 0 else 0
            report.append(f"  {source}: {count:,} ({percentage:.1f}%)")
        
        # Report null counts
        report.append("\nNull/empty values by field:")
        for field, count in sorted(self.null_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / self.entry_count * 100) if self.entry_count > 0 else 0
            report.append(f"  {field}: {count:,} ({percentage:.1f}%)")
        
        return "\n".join(report)


def collect_stats_from_entries(
    entries: List[TaxonomicEntry], 
    entry_groups: List[EntryGroupRef]
) -> DatasetStats:
    """Collect statistics from taxonomic entries and entry groups.
    
    Args:
        entries: List of taxonomic entries
        entry_groups: List of entry group references
        
    Returns:
        DatasetStats object with collected statistics
    """
    stats = DatasetStats()
    
    for entry in entries:
        stats.update_from_entry(entry)
    
    stats.update_from_entry_groups(entry_groups)
    
    return stats

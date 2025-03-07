"""TaxonoPy command-line interface.

This module provides the command-line interface functionality for TaxonoPy.
It includes the argument parser and command dispatching logic.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Iterator
import logging
import time

from taxonopy import __version__
from taxonopy.logging_config import setup_logging
from taxonopy.types.data_classes import TaxonomicEntry, EntryGroupRef
from taxonopy.input_parser import parse_input
from taxonopy.entry_grouper import create_entry_groups, count_entries_in_input
from taxonopy.stats_collector import DatasetStats

def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="TaxonoPy: Resolve taxonomic names using GNVerifier",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version number and exit"
    )

    parser.add_argument(
        "-i", "--input",
        type=str,
        required=True,
        help="Path to input Parquet or CSV file/directory"
    )
    
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        required=True,
        help="Directory to save resolved and investigation output files"
    )
    
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level"
    )
    
    parser.add_argument(
        "--log-file",
        type=str,
        help="Optional file to write logs to (in addition to console output)"
    )
    
    return parser

def process_input_data(input_path: str, stats: DatasetStats) -> List[EntryGroupRef]:
    """Process input data into entry groups.
    
    Args:
        input_path: Path to input directory or file
        stats: Statistics collector to update during processing
        
    Returns:
        List of EntryGroupRef objects
    """
    # Count entries for progress bar
    total_count = count_entries_in_input(input_path)
    logging.info(f"Found {total_count:,} entries in input files")
    
    # Set the total entry count for statistics
    stats.entry_count = total_count
    
    # Parse input data into TaxonomicEntry objects
    entries = parse_input(input_path)
    
    # Create entry groups from taxonomic entries and collect statistics
    entry_groups = create_entry_groups(entries, total_count, stats)
    logging.info(f"Created {len(entry_groups):,} entry groups")
    
    return entry_groups

def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the TaxonoPy CLI.
    
    Args:
        args: Command-line arguments (defaults to sys.argv[1:])
        
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    # Setup logging based on command line arguments
    setup_logging(parsed_args.log_level, parsed_args.log_file)
    
    # Create output directory if it doesn't exist
    output_dir = Path(parsed_args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Log start time
        start_time = time.time()
        logging.info(f"Starting TaxonoPy with input: {parsed_args.input}")
        
        # Create statistics collector
        stats = DatasetStats()
        
        # Process input data and collect statistics
        entry_groups = process_input_data(parsed_args.input, stats)
        
        # Update entry group stats
        stats.update_from_entry_groups(entry_groups)
        
        # Print statistics report
        print(stats.generate_report())
        
        # Log completion
        elapsed_time = time.time() - start_time
        logging.info(f"Processing completed in {elapsed_time:.2f} seconds")
        
        return 0
    
    except Exception as e:
        logging.error(f"Error processing input data: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

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
from taxonopy.query_planner import create_query_plans
from taxonopy.stats_collector import DatasetStats
from taxonopy.gnverifier_client import GNVerifierClient
from taxonopy.query_executor import execute_all_queries
from taxonopy.resolution_attempt_manager import ResolutionAttemptManager
from taxonopy.cache_manager import clear_cache, get_cache_stats
from taxonopy.config import config


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="TaxonoPy: Resolve taxonomic names using GNVerifier",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
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
        "--output-format",
        choices=["csv", "parquet"],
        default=config.output_format,
        help="Output file format"
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

    parser.add_argument(
        "--force-input",
        action="store_true",
        help="Force use of input metadata without resolution"
    )

    gnverifier_group = parser.add_argument_group("GNVerifier Settings")
    gnverifier_group.add_argument(
        "--gnverifier-image",
        type=str,
        default=config.gnverifier_image,
        help="Docker image for GNVerifier"
    )

    gnverifier_group.add_argument(
        "--data-sources",
        type=str,
        default=config.data_sources,
        help="Comma-separated list of data source IDs (e.g., '11' for GBIF)"
    )

    gnverifier_group.add_argument(
        "--batch-size",
        type=int,
        default=config.batch_size,
        help="Number of name queries to process in each GNVerifier batch"
    )

    # Boolean flags
    gnverifier_group.add_argument(
        "--all-matches",
        action="store_true",
        default=config.all_matches,
        help="Return all matches instead of just the best one"
    )

    gnverifier_group.add_argument(
        "--capitalize",
        action="store_true",
        default=config.capitalize,
        help="Capitalize the first letter of each name"
    )

    gnverifier_group.add_argument(
        "--fuzzy-uninomial",
        action="store_true",
        default=config.fuzzy_uninomial,
        help="Enable fuzzy matching for uninomial names"
    )
    
    gnverifier_group.add_argument(
        "--fuzzy-relaxed",
        action="store_true",
        default=config.fuzzy_relaxed,
        help="Relax fuzzy matching criteria. ⚠️ Known bug: https://github.com/gnames/gnverifier/issues/128"
    )

    gnverifier_group.add_argument(
        "--species-group",
        action="store_true",
        default=config.species_group,
        help="Enable group species matching"
    )
    
    cache_group = parser.add_argument_group("Cache Management")
    cache_group.add_argument(
        "--refresh-cache",
        action="store_true",
        default=False,
        help="Force refresh of TaxonoPy object cache"
    )
    
    cache_group.add_argument(
        "--clear-cache",
        action="store_true",
        default=False,
        help="Clear the TaxonoPy object cache before running"
    )
    
    cache_group.add_argument(
        "--cache-stats",
        action="store_true",
        default=False,
        help="Display statistics about the cache and exit"
    )

    meta_group = parser.add_argument_group("Application Metadata")
    meta_group.add_argument(
        "--show-config",
        action="store_true",
        help="Show current configuration and exit"
    )

    meta_group.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version number and exit"
    )

    return parser

def process_input_data(input_path: str, stats: DatasetStats, refresh_cache: bool = False) -> List[EntryGroupRef]:
    """Process input data into entry groups.
    
    Args:
        input_path: Path to input directory or file
        stats: Statistics collector to update during processing
        refresh_cache: Whether to ignore existing cache and refresh
        
    Returns:
        List of EntryGroupRef objects
    """
    # Count entries for progress bar
    total_count = count_entries_in_input(input_path)
    logging.info(f"Found {total_count:,} entries in input files")
    
    # Set the total entry count for statistics
    stats.entry_count = total_count

    # Create entry groups directly from input path
    entry_groups = create_entry_groups(input_path, total_count, stats, refresh_cache=refresh_cache)

    logging.info(f"Created {len(entry_groups):,} entry groups")
    
    return entry_groups


def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the TaxonoPy CLI."""
    parser = create_parser()
    
    # First, parse the args without enforcing required arguments
    for action in parser._actions:
        if action.required:
            action.required = False
    
    # Parse arguments
    parsed_args = parser.parse_args(args)
    
    # Handle standalone commands first

    # Version is already handled by argparse.

    if parsed_args.show_config:
        print(config.get_config_summary())
        return 0
        
    if parsed_args.cache_stats:
        stats = get_cache_stats()
        print("\nTaxonoPy Cache Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        return 0
        
    if parsed_args.clear_cache:
        count = clear_cache()
        print(f"\nCleared {count} cache files")
        if not parsed_args.input or not parsed_args.output_dir:
            return 0
       
    # If we've reached here and no standalone command was executed,
    # enforce required arguments
    if not parsed_args.input:
        parser.error("the following arguments are required: -i/--input")
    
    if not parsed_args.output_dir:
        parser.error("the following arguments are required: -o/--output-dir")
    
    # Update the config with command-line arguments
    config.update_from_args(vars(parsed_args))
    
    # Ensure required directories exist
    config.ensure_directories()
    
    # Setup logging based on command line arguments
    setup_logging(parsed_args.log_level, parsed_args.log_file)

    # Handle cache management commands
    if parsed_args.cache_stats:
        stats = get_cache_stats()
        print("\nTaxonoPy Cache Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        return 0
    
    if parsed_args.clear_cache:
        count = clear_cache()
        print(f"\nCleared {count} cache files")

    
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
        entry_groups = process_input_data(
            parsed_args.input, 
            stats,
            refresh_cache=parsed_args.refresh_cache
        )
        
        # Update entry group stats
        stats.update_from_entry_groups(entry_groups)
        
        # Create query groups
        # query_groups = create_query_plans(entry_groups)
        query_groups = create_query_plans(parsed_args.input, refresh_cache=parsed_args.refresh_cache)
        logging.info(f"Created {len(query_groups):,} query groups")
        
        # Print statistics report
        print(stats.generate_report())
        
        # Skip resolution if force-input is specified
        if parsed_args.force_input:
            logging.info("Skipping resolution due to --force-input flag")
        else:
            # Initialize the GNVerifier client
            try:
                client = GNVerifierClient(
                    gnverifier_image=parsed_args.gnverifier_image,
                    data_sources=parsed_args.data_sources
                )
                logging.info("GNVerifier client initialized successfully")
            except RuntimeError as e:
                logging.error(f"Failed to initialize GNVerifier client: {e}")
                return 1
            
            # Create resolution attempt manager
            resolution_manager = ResolutionAttemptManager()
            
            # Execute all queries
            logging.info(f"Executing queries with batch size {parsed_args.batch_size}")
            resolution_attempts = execute_all_queries(
                query_groups,
                client,
                resolution_manager,
                batch_size=parsed_args.batch_size
            )
            
            # Log resolution statistics
            resolution_stats = resolution_manager.get_statistics()
            logging.info(f"Resolution statistics: {resolution_stats}")
            
            # Save resolution state for future processing
            # resolution_manager.save_state(output_dir / "resolution_state.json")
            
            # TODO: Add business logic for applying resolutions to taxonomic data
            # This is where we'd transform the resolved taxonomic data and write output files
        
        # Log completion
        elapsed_time = time.time() - start_time
        logging.info(f"Processing completed in {elapsed_time:.2f} seconds")
        
        return 0
    
    except Exception as e:
        logging.error(f"Error processing input data: {str(e)}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

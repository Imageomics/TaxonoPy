# """TaxonoPy command-line interface.

# This module provides the command-line interface functionality for TaxonoPy.
# It includes the argument parser and command dispatching logic.
# """

# import argparse
# import sys
# from pathlib import Path
# from typing import List, Optional, Iterator
# import logging
# import time

# from taxonopy import __version__
# from taxonopy.logging_config import setup_logging
# from taxonopy.types.data_classes import TaxonomicEntry, EntryGroupRef
# from taxonopy.input_parser import parse_input
# from taxonopy.entry_grouper import create_entry_groups, count_entries_in_input
# from taxonopy.query.planner import create_initial_query_plans
# from taxonopy.query.gnverifier_client import GNVerifierClient
# from taxonopy.query.executor import execute_all_queries
# from taxonopy.stats_collector import DatasetStats
# from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
# from taxonopy.cache_manager import clear_cache, get_cache_stats
# from taxonopy.config import config
# from taxonopy.output_manager import generate_forced_output, generate_resolution_output


# def create_parser() -> argparse.ArgumentParser:
#     """Create and configure the argument parser."""
#     parser = argparse.ArgumentParser(
#         description="TaxonoPy: Resolve taxonomic names using GNVerifier",
#         formatter_class=argparse.ArgumentDefaultsHelpFormatter
#     )

#     parser.add_argument(
#         "-i", "--input",
#         type=str,
#         required=True,
#         help="Path to input Parquet or CSV file/directory"
#     )
    
#     parser.add_argument(
#         "-o", "--output-dir",
#         type=str,
#         required=True,
#         help="Directory to save resolved and investigation output files"
#     )
    
#     parser.add_argument(
#         "--output-format",
#         choices=["csv", "parquet"],
#         default=config.output_format,
#         help="Output file format"
#     )
    
#     parser.add_argument(
#         "--log-level",
#         choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
#         default="INFO",
#         help="Set logging level"
#     )
    
#     parser.add_argument(
#         "--log-file",
#         type=str,
#         help="Optional file to write logs to (in addition to console output)"
#     )

#     parser.add_argument(
#         "--force-input",
#         action="store_true",
#         help="Force use of input metadata without resolution"
#     )

#     gnverifier_group = parser.add_argument_group("GNVerifier Settings")
#     gnverifier_group.add_argument(
#         "--batch-size",
#         type=int,
#         default=config.batch_size,
#         help="Number of name queries to process in each GNVerifier batch"
#     )

#     # Boolean flags
#     gnverifier_group.add_argument(
#         "--all-matches",
#         action="store_true",
#         default=config.all_matches,
#         help="Return all matches instead of just the best one"
#     )

#     gnverifier_group.add_argument(
#         "--capitalize",
#         action="store_true",
#         default=config.capitalize,
#         help="Capitalize the first letter of each name"
#     )

#     gnverifier_group.add_argument(
#         "--fuzzy-uninomial",
#         action="store_true",
#         default=config.fuzzy_uninomial,
#         help="Enable fuzzy matching for uninomial names"
#     )
    
#     gnverifier_group.add_argument(
#         "--fuzzy-relaxed",
#         action="store_true",
#         default=config.fuzzy_relaxed,
#         help="Relax fuzzy matching criteria. ⚠️ Known bug: https://github.com/gnames/gnverifier/issues/128"
#     )

#     gnverifier_group.add_argument(
#         "--species-group",
#         action="store_true",
#         default=config.species_group,
#         help="Enable group species matching"
#     )
    
#     cache_group = parser.add_argument_group("Cache Management")
#     cache_group.add_argument(
#         "--cache-stats",
#         action="store_true",
#         default=False,
#         help="Display statistics about the cache and exit"
#     )

#     cache_group.add_argument(
#         "--clear-cache",
#         action="store_true",
#         default=False,
#         help="Clear the TaxonoPy object cache. May be used in isolation."
#     )

#     cache_group.add_argument(
#         "--refresh-cache",
#         action="store_true",
#         default=False,
#         help="Force refresh of TaxonoPy object cache before running. Must be used with -i and -o."
#     )

#     meta_group = parser.add_argument_group("Application Metadata")
#     meta_group.add_argument(
#         "--show-config",
#         action="store_true",
#         help="Show current configuration and exit"
#     )

#     meta_group.add_argument(
#         "--version",
#         action="version",
#         version=f"%(prog)s {__version__}",
#         help="Show version number and exit"
#     )

#     return parser

# def process_input_data(input_path: str, stats: DatasetStats, refresh_cache: bool = False) -> List[EntryGroupRef]:
#     """Process input data into entry groups.
    
#     Args:
#         input_path: Path to input directory or file
#         stats: Statistics collector to update during processing
#         refresh_cache: Whether to ignore existing cache and refresh
        
#     Returns:
#         List of EntryGroupRef objects
#         Dictionary mapping entry group keys to EntryGroupRef objects
#     """
#     # Count entries for progress bar
#     total_count = count_entries_in_input(input_path)
#     logging.info(f"Found {total_count:,} entries in input files")
    
#     # Set the total entry count for statistics
#     stats.entry_count = total_count

#     # Create entry groups directly from input path
#     entry_groups = create_entry_groups(input_path, total_count, stats, refresh_cache=refresh_cache)
#     entry_group_index = {eg.key: eg for eg in entry_groups}

#     logging.info(f"Created {len(entry_groups):,} entry groups")

#     return entry_groups, entry_group_index

# def main(args: Optional[List[str]] = None) -> int:
#     """Main entry point for the TaxonoPy CLI."""
#     parser = create_parser()
    
#     # First, parse the args without enforcing required arguments
#     for action in parser._actions:
#         if action.required:
#             action.required = False
    
#     # Parse arguments
#     parsed_args = parser.parse_args(args)
    
#     # Handle standalone commands first

#     # Version is already handled by argparse.

#     if parsed_args.show_config:
#         print(config.get_config_summary())
#         return 0
        
#     if parsed_args.cache_stats:
#         stats = get_cache_stats()
#         print("\nTaxonoPy Cache Statistics:")
#         for key, value in stats.items():
#             print(f"  {key}: {value}")
#         return 0
        
#     if parsed_args.clear_cache:
#         count = clear_cache()
#         print(f"\nCleared {count} cache files")
#         if not parsed_args.input or not parsed_args.output_dir:
#             return 0
       
#     # If we've reached here and no standalone command was executed,
#     # enforce required arguments
#     if not parsed_args.input:
#         parser.error("the following arguments are required: -i/--input")
    
#     if not parsed_args.output_dir:
#         parser.error("the following arguments are required: -o/--output-dir")
    
#     # Update the config with command-line arguments
#     config.update_from_args(vars(parsed_args))
    
#     # Ensure required directories exist
#     config.ensure_directories()
    
#     # Setup logging based on command line arguments
#     setup_logging(parsed_args.log_level, parsed_args.log_file)

#     # Handle cache management commands
#     if parsed_args.cache_stats:
#         stats = get_cache_stats()
#         print("\nTaxonoPy Cache Statistics:")
#         for key, value in stats.items():
#             print(f"  {key}: {value}")
#         return 0
    
#     if parsed_args.clear_cache:
#         count = clear_cache()
#         print(f"\nCleared {count} cache files")

    
#     # Create output directory if it doesn't exist
#     output_dir = Path(parsed_args.output_dir)
#     output_dir.mkdir(parents=True, exist_ok=True)
    
#     try:
#         # Log start time
#         start_time = time.time()
#         logging.info(f"Starting TaxonoPy with input: {parsed_args.input}")
        
#         # Create statistics collector
#         stats = DatasetStats()
        
#         # Skip resolution if force-input is specified
#         if parsed_args.force_input:
#             logging.info("Skipping resolution due to --force-input flag")
            
#             # Generate forced output directly from input
#             generated_files = generate_forced_output(
#                 parsed_args.input,
#                 parsed_args.output_dir,
#                 parsed_args.output_format
#             )
            
#             logging.info(f"Generated {len(generated_files)} forced output files:")
#             for file_path in generated_files:
#                 logging.info(f"  {file_path}")
                
#             # Log completion
#             elapsed_time = time.time() - start_time
#             logging.info(f"Processing completed in {elapsed_time:.2f} seconds")
            
#             return 0
        
#         # Normal processing path (resolution)
#         # Process input data and collect statistics
#         entry_groups, entry_group_index = process_input_data(
#             parsed_args.input, 
#             stats,
#             refresh_cache=parsed_args.refresh_cache
#         )
        
#         # Update entry group stats
#         stats.update_from_entry_groups(entry_groups)
        
#         # Create query groups
#         # query_groups = create_initial_query_plans(parsed_args.input, refresh_cache=parsed_args.refresh_cache)
#         # Update to match this function signature:
#         # def create_initial_query_plans(
#         #     entry_groups: List[EntryGroupRef],
#         #     data_source_id: int = DATA_SOURCE_PRECEDENCE['GBIF'],  # Default to GBIF
#         #     progress_bar: bool = True
#         # ) -> List[QueryGroupRef]:

#         query_groups = create_initial_query_plans(entry_groups)

#         logging.info(f"Created {len(query_groups):,} query groups")

#         """
#         Example EntryGroupRef data access from QueryGroupRef objects
#         for query_group in query_groups:
#             resolved_groups = query_group.resolve_entry_groups(entry_group_index.get)
#             # Now we can e.g. log details or process the combined data:
#             for eg in resolved_groups:
#                 logging.debug(f"Resolved entry group {eg.key} with scientific name: {eg.scientific_name}")
#         """
        
#         # Print statistics report
#         print(stats.generate_report())
        
#         # Initialize the GNVerifier client
#         try:
#             client = GNVerifierClient()
#             logging.info("GNVerifier client initialized successfully")
#         except RuntimeError as e:
#             logging.error(f"Failed to initialize GNVerifier client: {e}")
#             return 1
        
#         # Create resolution attempt manager
#         resolution_manager = ResolutionAttemptManager()
        
#         # Execute all queries
#         logging.info(f"Executing queries with batch size {parsed_args.batch_size}")
#         resolution_attempts = execute_all_queries(
#             query_groups,
#             client,
#             batch_size=parsed_args.batch_size
#         )
        
#         # Log resolution statistics
#         resolution_stats = resolution_manager.get_statistics()
#         logging.info(f"Resolution statistics: {resolution_stats}")
        
#         # Generate output files based on resolution results
#         resolved_files, unsolved_files = generate_resolution_output(
#             parsed_args.input,
#             parsed_args.output_dir,
#             resolution_manager,
#             entry_groups,
#             query_groups,
#             parsed_args.output_format
#         )
        
#         logging.info(f"Generated {len(resolved_files)} resolved output files")
#         logging.info(f"Generated {len(unsolved_files)} unsolved output files")
        
#         # Log completion
#         elapsed_time = time.time() - start_time
#         logging.info(f"Processing completed in {elapsed_time:.2f} seconds")
        
#         return 0
    
#     except Exception as e:
#         logging.error(f"Error processing input data: {str(e)}", exc_info=True)
#         return 1


# if __name__ == "__main__":
#     sys.exit(main())

"""TaxonoPy command-line interface.

This module provides the command-line interface functionality for TaxonoPy.
It includes the argument parser and command dispatching logic.
"""

import argparse
import sys
import time
import logging
from pathlib import Path
from typing import List, Optional

from taxonopy import __version__
from taxonopy.config import config
from taxonopy.logging_config import setup_logging
from taxonopy.cache_manager import clear_cache, get_cache_stats
from taxonopy.stats_collector import DatasetStats
from taxonopy.input_parser import parse_input
from taxonopy.entry_grouper import create_entry_groups, count_entries_in_input
from taxonopy.query.planner import create_initial_query_plans
from taxonopy.query.gnverifier_client import GNVerifierClient
from taxonopy.query.executor import execute_all_queries
from taxonopy.output_manager import generate_forced_output, generate_resolution_output

# -----------------------------------------------------------------------------
# Parser Setup
# -----------------------------------------------------------------------------
def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser with two top-level commands: 'resolve' and 'trace'."""
    parser = argparse.ArgumentParser(
        description="TaxonoPy: Resolve taxonomic names using GNVerifier and trace data provenance.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Global options for cache management and application metadata
    parser.add_argument(
        "--cache-stats",
        action="store_true",
        default=False,
        help="Display statistics about the cache and exit"
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        default=False,
        help="Clear the TaxonoPy object cache. May be used in isolation."
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Show current configuration and exit"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version number and exit"
    )

    # Create subparsers for the top-level commands
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- 'resolve' command ---
    parser_resolve = subparsers.add_parser(
        "resolve", help="Run the taxonomic resolution workflow"
    )
    parser_resolve.add_argument(
        "-i", "--input",
        type=str,
        required=True,
        help="Path to input Parquet or CSV file/directory"
    )
    parser_resolve.add_argument(
        "-o", "--output-dir",
        type=str,
        required=True,
        help="Directory to save resolved and investigation output files"
    )
    parser_resolve.add_argument(
        "--output-format",
        choices=["csv", "parquet"],
        default=config.output_format,
        help="Output file format"
    )
    parser_resolve.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Set logging level"
    )
    parser_resolve.add_argument(
        "--log-file",
        type=str,
        help="Optional file to write logs to (in addition to console output)"
    )
    parser_resolve.add_argument(
        "--force-input",
        action="store_true",
        help="Force use of input metadata without resolution"
    )
    # GNVerifier settings group for resolve
    gnverifier_group = parser_resolve.add_argument_group("GNVerifier Settings")
    gnverifier_group.add_argument(
        "--batch-size",
        type=int,
        default=config.batch_size,
        help="Number of name queries to process in each GNVerifier batch"
    )
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
    # Cache and metadata options (also available at global level)
    cache_group = parser_resolve.add_argument_group("Cache Management")
    cache_group.add_argument(
        "--refresh-cache",
        action="store_true",
        default=False,
        help="Force refresh of TaxonoPy object cache before running. Must be used with -i and -o."
    )

    # --- 'trace' command ---
    parser_trace = subparsers.add_parser(
        "trace", help="Trace data provenance of TaxonoPy objects"
    )
    # Create subparsers for the trace subcommands
    trace_subparsers = parser_trace.add_subparsers(dest="trace_command", required=True)

    # trace entry
    parser_trace_entry = trace_subparsers.add_parser(
        "entry", help="Trace an individual taxonomic entry"
    )
    parser_trace_entry.add_argument(
        "--uuid", required=True, help="UUID of the taxonomic entry"
    )
    parser_trace_entry.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    # trace group
    parser_trace_group = trace_subparsers.add_parser(
        "group", help="Trace an entry group"
    )
    parser_trace_group.add_argument(
        "--key", required=True, help="Key of the entry group"
    )
    parser_trace_group.add_argument(
        "--verbose", action="store_true", help="Show detailed information"
    )
    parser_trace_group.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    # trace query
    parser_trace_query = trace_subparsers.add_parser(
        "query", help="Trace a query group"
    )
    parser_trace_query.add_argument(
        "--key", required=True, help="Key of the query group"
    )
    parser_trace_query.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    # trace resolution
    parser_trace_resolution = trace_subparsers.add_parser(
        "resolution", help="Trace resolution attempts"
    )
    parser_trace_resolution.add_argument(
        "--key", required=True, help="Key of the resolution attempt to start from"
    )
    parser_trace_resolution.add_argument(
        "--detailed", action="store_true", help="Show full metadata for each attempt"
    )
    parser_trace_resolution.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    # trace cache
    parser_trace_cache = trace_subparsers.add_parser(
        "cache", help="Inspect cached objects"
    )
    parser_trace_cache.add_argument(
        "--list", action="store_true", help="List all cache entries"
    )
    parser_trace_cache.add_argument(
        "--key", help="Inspect a specific cache entry"
    )
    parser_trace_cache.add_argument(
        "--verbose", action="store_true", help="Show detailed cache information"
    )
    parser_trace_cache.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )

    return parser

# -----------------------------------------------------------------------------
# Dispatch Functions for Each Top-Level Command
# -----------------------------------------------------------------------------
def run_resolve(args: argparse.Namespace) -> int:
    """Run the taxonomic resolution workflow."""
    # Update configuration with command-line arguments
    config.update_from_args(vars(args))
    # Ensure required directories exist
    config.ensure_directories()
    setup_logging(args.log_level, args.log_file)

    # Handle cache management commands if specified
    if args.cache_stats:
        stats = get_cache_stats()
        print("\nTaxonoPy Cache Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        return 0

    if args.clear_cache:
        count = clear_cache()
        print(f"\nCleared {count} cache files")
        # If input/output not provided, exit.
        if not args.input or not args.output_dir:
            return 0

    # Create output directory if it doesn't exist
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        start_time = time.time()
        logging.info(f"Starting TaxonoPy with input: {args.input}")

        # Create statistics collector
        stats = DatasetStats()

        # If forced input, generate forced output
        if args.force_input:
            logging.info("Skipping resolution due to --force-input flag")
            generated_files = generate_forced_output(args.input, args.output_dir, args.output_format)
            logging.info(f"Generated {len(generated_files)} forced output files:")
            for file_path in generated_files:
                logging.info(f"  {file_path}")
            elapsed_time = time.time() - start_time
            logging.info(f"Processing completed in {elapsed_time:.2f} seconds")
            return 0

        # Process input data and collect statistics
        entry_groups, entry_group_index = process_input_data(args.input, stats, refresh_cache=args.refresh_cache)
        stats.update_from_entry_groups(entry_groups)

        # Create query groups
        query_groups = create_initial_query_plans(entry_groups)
        logging.info(f"Created {len(query_groups):,} query groups")

        print(stats.generate_report())

        # Initialize GNVerifier client
        try:
            client = GNVerifierClient()
            logging.info("GNVerifier client initialized successfully")
        except RuntimeError as e:
            logging.error(f"Failed to initialize GNVerifier client: {e}")
            return 1

        # Create resolution attempt manager
        from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
        resolution_manager = ResolutionAttemptManager()

        logging.info(f"Executing queries with batch size {args.batch_size}")
        resolution_attempts = execute_all_queries(query_groups, client, batch_size=args.batch_size)
        resolution_stats = resolution_manager.get_statistics()
        logging.info(f"Resolution statistics: {resolution_stats}")

        resolved_files, unsolved_files = generate_resolution_output(
            args.input, args.output_dir, resolution_manager, entry_groups, query_groups, args.output_format
        )
        logging.info(f"Generated {len(resolved_files)} resolved output files")
        logging.info(f"Generated {len(unsolved_files)} unsolved output files")
        elapsed_time = time.time() - start_time
        logging.info(f"Processing completed in {elapsed_time:.2f} seconds")
        return 0

    except Exception as e:
        logging.error(f"Error processing input data: {str(e)}", exc_info=True)
        return 1

def run_trace(args: argparse.Namespace) -> int:
    """Scaffold for the trace command.
    
    Currently, this just prints the parsed arguments and a stub message.
    You can expand this function to call the appropriate trace subcommand functions.
    """
    trace_cmd = args.trace_command
    logging.info(f"Trace command: {trace_cmd}")
    # Here, you would dispatch to specific functions, e.g.:
    # if trace_cmd == "entry": trace_entry(args)
    # elif trace_cmd == "group": trace_group(args)
    # elif trace_cmd == "query": trace_query(args)
    # elif trace_cmd == "resolution": trace_resolution(args)
    # elif trace_cmd == "cache": trace_cache(args)
    # For now, we simply print the arguments.
    print("Trace functionality is not yet implemented. Parsed arguments:")
    print(args)
    return 0

# -----------------------------------------------------------------------------
# Main Entry Point
# -----------------------------------------------------------------------------
def main(args: Optional[List[str]] = None) -> int:
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    # Handle global commands if needed (e.g. --show-config, --cache-stats) before subcommand dispatch
    if parsed_args.show_config:
        print(config.get_config_summary())
        return 0

    # Dispatch based on the chosen top-level command
    if parsed_args.command == "resolve":
        # Ensure a batch-size is available for resolution (defaulting to current config if not set)
        if not hasattr(parsed_args, "batch_size"):
            setattr(parsed_args, "batch_size", config.batch_size)
        return run_resolve(parsed_args)
    elif parsed_args.command == "trace":
        return run_trace(parsed_args)
    else:
        parser.error("Unknown command")
        return 1

if __name__ == "__main__":
    sys.exit(main())

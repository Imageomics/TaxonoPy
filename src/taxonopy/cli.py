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
import json

from taxonopy import __version__
from taxonopy.config import config
from taxonopy.logging_config import setup_logging
from taxonopy.cache_manager import (
    clear_cache,
    configure_cache_namespace,
    get_cache_stats,
)
from taxonopy.stats_collector import DatasetStats
from taxonopy.entry_grouper import create_entry_groups, count_entries_in_input
from taxonopy.input_parser import find_input_files

from taxonopy.query.gnverifier_client import GNVerifierClient
from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

from taxonopy.output_manager import generate_forced_output, generate_resolution_output

from taxonopy.trace import entry as trace_entry

# from taxonopy.types.data_classes import EntryGroupRef # For future use with trace

# Parser Setup
def create_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description="TaxonoPy: Resolve taxonomic names using GNVerifier and trace data provenance.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Global options
    parser.add_argument(
        "--cache-dir", type=str, help="Directory for TaxonoPy cache (can also be set with TAXONOPY_CACHE_DIR environment variable)",
    )
    parser.add_argument(
        "--show-cache-path", action="store_true", help="Display the current cache directory path and exit"
    )
    parser.add_argument(
        "--cache-stats", action="store_true", default=False, help="Display statistics about the cache and exit"
    )
    parser.add_argument(
        "--clear-cache", action="store_true", default=False, help="Clear the TaxonoPy object cache. May be used in isolation."
    )
    parser.add_argument(
        "--show-config", action="store_true", help="Show current configuration and exit"
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}", help="Show version number and exit"
    )

    subparsers = parser.add_subparsers(dest="command", required=False)

    # Resolve command
    parser_resolve = subparsers.add_parser("resolve", help="Run the taxonomic resolution workflow")
    parser_resolve.add_argument("-i", "--input", type=str, required=True, help="Path to input Parquet or CSV file/directory")
    parser_resolve.add_argument("-o", "--output-dir", type=str, required=True, help="Directory to save resolved and unsolved output files")
    parser_resolve.add_argument("--output-format", choices=["csv", "parquet"], default=config.output_format, help="Output file format")
    parser_resolve.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set logging level")
    parser_resolve.add_argument("--log-file", type=str, help="Optional file to write logs to")
    parser_resolve.add_argument("--force-input", action="store_true", help="Force use of input metadata without resolution")

    # GNVerifier settings group for resolve
    gnverifier_group = parser_resolve.add_argument_group("GNVerifier Settings")
    gnverifier_group.add_argument(
        "--batch-size", type=int, default=config.batch_size,
        help="Max number of name queries per GNVerifier API/subprocess call"
    )
    # Other GNVerifier flags
    gnverifier_group.add_argument("--all-matches", action="store_true", default=config.all_matches, help="Return all matches instead of just the best one")
    gnverifier_group.add_argument("--capitalize", action="store_true", default=config.capitalize, help="Capitalize the first letter of each name")
    gnverifier_group.add_argument("--fuzzy-uninomial", action="store_true", default=config.fuzzy_uninomial, help="Enable fuzzy matching for uninomial names")
    gnverifier_group.add_argument("--fuzzy-relaxed", action="store_true", default=config.fuzzy_relaxed, help="Relax fuzzy matching criteria")
    gnverifier_group.add_argument("--species-group", action="store_true", default=config.species_group, help="Enable group species matching")

    # Cache and metadata options
    cache_group = parser_resolve.add_argument_group("Cache Management")
    cache_group.add_argument("--refresh-cache", action="store_true", default=False, help="Force refresh of cached objects (input parsing, grouping) before running.")

    # Trace command
    parser_trace = subparsers.add_parser("trace", help="Trace data provenance of TaxonoPy objects")
    trace_subparsers = parser_trace.add_subparsers(dest="trace_command", required=True)

    # Trace entry
    parser_trace_entry = trace_subparsers.add_parser("entry", help="Trace an individual taxonomic entry by UUID")
    parser_trace_entry.add_argument("--uuid", required=True, help="UUID of the taxonomic entry")
    parser_trace_entry.add_argument("--from-input", required=True, help="Path to the original input dataset")
    parser_trace_entry.add_argument("--format", choices=["json", "text"], default="json", help="Output format")
    parser_trace_entry.add_argument("--verbose", action="store_true", help="Show full details including all UUIDs in groups")

# Not yet implemented
    # # Trace entry groups
    # parser_trace_group = trace_subparsers.add_parser("group", help="Trace an entry group")
    # parser_trace_group.add_argument("--key", required=True, help="Key (SHA256 hash) of the EntryGroupRef")
    # parser_trace_group.add_argument("--verbose", action="store_true", help="Show detailed information")
    # parser_trace_group.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # # Trace resolution attempt chain
    # parser_trace_resolution = trace_subparsers.add_parser("resolution", help="Trace resolution attempts for an Entry Group")
    # parser_trace_resolution.add_argument("--key", required=True, help="Key (SHA256 hash) of the EntryGroupRef to trace")
    # parser_trace_resolution.add_argument("--detailed", action="store_true", help="Show full metadata for each attempt")
    # parser_trace_resolution.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # # Trace cache
    # parser_trace_cache = trace_subparsers.add_parser("cache", help="Inspect cached objects")
    # parser_trace_cache.add_argument("--list", action="store_true", help="List all cache entries")
    # parser_trace_cache.add_argument("--key", help="Inspect a specific cache entry key (e.g., taxonomic_entries_...)")
    # parser_trace_cache.add_argument("--verbose", action="store_true", help="Show detailed cache information")
    # parser_trace_cache.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    # Common names
    parser_common = subparsers.add_parser("common-names", help="Merge vernacular names (post-process) into resolved outputs")
    parser_common.add_argument("--resolved-dir", dest="annotation_dir", required=True,help="Directory containing your *.resolved.parquet files")
    parser_common.add_argument("--output-dir", required=True, help="Directory to write annotated .parquet files")

    return parser

# Dispatch functions for each top-level command
def run_resolve(args: argparse.Namespace) -> int:
    """Run the taxonomic resolution workflow."""
    config.update_from_args(vars(args))
    config.ensure_directories()
    setup_logging(args.log_level, args.log_file)

    try:
        input_files = find_input_files(args.input)
    except ValueError as exc:
        logging.error(f"Unable to prepare cache namespace: {exc}")
        return 1

    cache_path = configure_cache_namespace("resolve", __version__, input_files)
    logging.info(f"Using cache namespace: {cache_path}")

    if args.show_cache_path:
        print(f"TaxonoPy cache directory: {cache_path}")
        return 0

    if args.show_config:
        print(config.get_config_summary())
        return 0

    # Handle global flags first
    if args.cache_stats:
        stats = get_cache_stats()
        print("\nTaxonoPy Cache Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        return 0
    if args.clear_cache:
        count = clear_cache()
        print(f"\nCleared {count} cache entries")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        start_time = time.time()
        logging.info(f"Starting TaxonoPy v{__version__} with input: {args.input}")
        stats = DatasetStats()

        if args.force_input:
            logging.info("Skipping resolution due to --force-input flag")
            generated_files = generate_forced_output(args.input, args.output_dir, args.output_format)
            elapsed_time = time.time() - start_time
            logging.info(f"Forced output completed in {elapsed_time:.2f} seconds. Files: {generated_files}")
            return 0


        # 1. Count and group entries
        logging.info("Counting entries...")
        total_count = count_entries_in_input(args.input)
        logging.info(f"Found {total_count:,} entries in input files.")

        logging.info("Grouping entries...")
        _, entry_group_map = create_entry_groups(
            args.input,
            total_count=total_count,
            stats_collector=stats,
            refresh_cache=args.refresh_cache
        )
        # Update stats from the map values (EntryGroupRef objects)
        stats.update_from_entry_groups(list(entry_group_map.values()))
        logging.info(f"Created {len(entry_group_map):,} unique entry groups.")

        # 2. Initialize client and manager
        try:
            # Client pulls from global config by default
            client = GNVerifierClient()
            logging.info("GNVerifier client initialized successfully.")
        except RuntimeError as e:
            logging.error(f"Failed to initialize GNVerifier client: {e}")
            logging.error("Ensure GNVerifier is installed locally or Docker is running with the specified image.")
            return 1

        # Instantiate the manager
        resolution_manager = ResolutionAttemptManager()
        logging.info("Resolution Attempt Manager initialized.")

        # 3. Run resolution workflow
        # The manager handles planning, execution, classification, retries
        print(stats.generate_report()) # Report stats after preprocessing
        logging.info("Starting main resolution workflow...")
        try:
            # Pass the necessary map and the client
            # Batch size is implicitly handled by the client/executor based on config
            resolution_manager.resolve_all_entry_groups(entry_group_map, client)
            logging.debug("Resolution workflow completed successfully.")
        except RuntimeError as e:
             # Catch fatal errors raised by manager/executor/client
             logging.critical(f"Workflow halted due to fatal error: {e}")
             return 1 # Indicate failure
        except Exception as e:
             logging.error(f"An unexpected error occurred during the resolution workflow: {e}", exc_info=True)
             return 1 # Indicate failure


        # 4. Generate output
        logging.info("Generating output files...")
        # Pass only the manager and entry group map
        resolved_files, unsolved_files = generate_resolution_output(
            args.input,
            args.output_dir,
            resolution_manager,
            entry_group_map,
            args.output_format
        )
        logging.info(f"Generated {len(resolved_files)} resolved output files.")
        logging.info(f"Generated {len(unsolved_files)} unsolved output files.")

        # Final stats and timing
        final_stats = resolution_manager.get_statistics()
        logging.info("Final resolution statistics:")
        for key, value in final_stats.items():
            logging.info(f"  {key}: {value}")
        # Save final stats to a file at the root of the output directory
        stats_file_path = output_dir / "resolution_stats.json"
        stats_file_path.write_text(json.dumps(final_stats, indent=4))
        logging.info(f"Statistics saved to {stats_file_path}")
        elapsed_time = time.time() - start_time
        logging.info(f"Processing completed in {elapsed_time:.2f} seconds.")
        return 0

    except Exception as e:
        # Catch any other unexpected errors during the setup/overall process
        logging.error(f"An unexpected error occurred: {str(e)}", exc_info=True)
        return 1

def run_trace(args: argparse.Namespace) -> int:
    """Dispatch trace commands."""
    # Update the configuration with the passed arguments
    config.update_from_args(vars(args))
    config.ensure_directories()

    try:
        input_files = find_input_files(args.from_input)
    except ValueError as exc:
        logging.error(f"Unable to prepare cache namespace: {exc}")
        return 1

    cache_path = configure_cache_namespace("resolve", __version__, input_files)
    logging.info(f"Using cache namespace: {cache_path}")

    # Reuse global flags within trace context
    if args.show_cache_path:
        print(f"TaxonoPy cache directory: {cache_path}")
        return 0
    if args.show_config:
        print(config.get_config_summary())
        return 0
    if args.cache_stats:
        stats = get_cache_stats()
        print("\nTaxonoPy Cache Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        return 0
    if args.clear_cache:
        count = clear_cache()
        print(f"\nCleared {count} cache entries")
        return 0

    if args.trace_command == "entry":
        # Dispatch to the trace_entry function from the trace module.
        return trace_entry.trace_entry(args.uuid, args.from_input, args.format, args.verbose)
# Not yet implemented
    # elif args.trace_command == "group":
    #      # Implement trace_group using entry_group_key and manager
    #      print(f"Trace group (EntryGroupRef Key: {args.key}) - Not fully implemented")
    #      # TODO: Load manager state (if possible) or relevant cache to trace group
    #      return 1
    # elif args.trace_command == "resolution":
    #      # Implement trace_resolution using entry_group_key and manager
    #      print(f"Trace resolution (EntryGroupRef Key: {args.key}) - Not fully implemented")
    #      # TODO: Load manager state (if possible) or relevant cache to trace resolution chain
    #      return 1
    # elif args.trace_command == "cache":
    #      # Implement trace_cache (likely remains similar)
    #      print("Trace cache - Not fully implemented")
    #      # TODO: Implement cache inspection logic
    #      return 1
    else:
        print(f"Unknown trace subcommand: {args.trace_command}")
        return 1

# Main Entry Point
def main(args: Optional[List[str]] = None) -> int:
    parser = create_parser()
    parsed_args = parser.parse_args(args)

    # Handle global cache directory setting
    if parsed_args.cache_dir:
        config.update_from_args({'cache_dir': parsed_args.cache_dir})
        config.ensure_directories()

    # Handle global commands only when no subcommand is specified
    if parsed_args.command is None:
        if parsed_args.show_cache_path:
            print(f"TaxonoPy cache directory: {config.cache_dir}")
            return 0
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
            print(f"\nCleared {count} cache entries")
            return 0

        parser.print_help()
        return 1

    # Dispatch based on the chosen top-level command
    if parsed_args.command == "resolve":
        return run_resolve(parsed_args)
    elif parsed_args.command == "trace":
        return run_trace(parsed_args)
    elif parsed_args.command == "common-names":
        from taxonopy.resolve_common_names import main as cn_main
        config.update_from_args(vars(parsed_args))
        config.ensure_directories()
        if parsed_args.show_cache_path:
            print(f"TaxonoPy cache directory: {config.cache_dir}")
            return 0
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
            print(f"\nCleared {count} cache entries")
            return 0
        return cn_main(parsed_args.annotation_dir, parsed_args.output_dir)
    else:
        parser.error(f"Unknown command: {parsed_args.command}")
        return 1

if __name__ == "__main__":
    sys.exit(main())

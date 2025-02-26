"""TaxonoPy command-line interface.

This module provides the command-line interface functionality for TaxonoPy.
It includes the argument parser and command dispatching logic.
"""

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from taxonopy import __version__
from taxonopy.logging_config import setup_logging


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
    

    
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""TaxonoPy main entry point.

This module provides the entry point for running the package as a script.
It imports and calls the main function from the cli module.
"""

from taxonopy.cli import main

if __name__ == "__main__":
    exit(main())

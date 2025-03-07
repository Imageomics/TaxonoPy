"""Input parsing for TaxonoPy.

This module provides functions for reading and validating taxonomic data
from Parquet and CSV files, converting rows to TaxonomicEntry objects.
"""

import os
import glob
from pathlib import Path
from typing import List, Iterator, Dict, Set, Optional, Tuple, Any
from dataclasses import asdict

import polars as pl
from tqdm import tqdm

from taxonopy.types.data_classes import TaxonomicEntry


# Required schema for input files
REQUIRED_COLUMNS = {
    "uuid", "source_id", "scientific_name", "kingdom", "phylum", 
    "class", "order", "family", "genus", "species", "common_name"
}

# Column types for validation (for Parquet files)
COLUMN_TYPES = {
    "uuid": pl.Utf8,
    "source_id": pl.Utf8,
    "scientific_name": pl.Utf8,
    "kingdom": pl.Utf8,
    "phylum": pl.Utf8,
    "class": pl.Utf8,
    "order": pl.Utf8,
    "family": pl.Utf8,
    "genus": pl.Utf8,
    "species": pl.Utf8,
    "common_name": pl.Utf8,
}


def find_input_files(input_path: str) -> List[str]:
    """Find all data files in the input path with consistent extensions.
    
    Args:
        input_path: Path to a directory or file
        
    Returns:
        List of file paths
    
    Raises:
        ValueError: If no files found or inconsistent extensions
    """
    input_path = os.path.expanduser(input_path)
    
    if os.path.isfile(input_path):
        return [input_path]
    
    # Look for Parquet files first
    parquet_files = glob.glob(os.path.join(input_path, "**", "*.parquet"), recursive=True)
    
    # If no Parquet files, look for CSV files
    csv_files = glob.glob(os.path.join(input_path, "**", "*.csv"), recursive=True)
    
    # Check if both types exist
    if parquet_files and csv_files:
        raise ValueError(
            "Found both Parquet and CSV files. Input directory must contain only one file type."
        )
    
    # Determine which files to use
    files = parquet_files or csv_files
    
    if not files:
        raise ValueError(
            f"No Parquet or CSV files found in {input_path}"
        )
    
    return sorted(files)


def validate_schema(file_path: str) -> Tuple[bool, Optional[str], str]:
    """Validate the schema of a data file.
    
    Args:
        file_path: Path to the file to validate
        
    Returns:
        Tuple of (is_valid, error_message, file_format)
    """
    file_format = "parquet" if file_path.endswith(".parquet") else "csv"
    
    try:
        # Read just the schema for Parquet files
        if file_format == "parquet":
            schema = pl.read_parquet_schema(file_path)
            columns = set(schema.keys())
        else:
            # For CSV, we need to read a small sample to get columns
            df = pl.read_csv(file_path, n_rows=5)
            columns = set(df.columns)
        
        # Check for missing required columns
        missing_columns = REQUIRED_COLUMNS - columns
        if missing_columns:
            return False, f"Missing required columns: {', '.join(missing_columns)}", file_format
        
        return True, None, file_format
    except Exception as e:
        return False, f"Error validating file schema: {str(e)}", file_format


def validate_all_files(file_paths: List[str]) -> str:
    """Validate all input files have consistent and valid schemas.
    
    Args:
        file_paths: List of file paths to validate
        
    Returns:
        File format ('parquet' or 'csv')
    
    Raises:
        ValueError: If any file has an invalid schema
    """
    file_format = None
    
    for file_path in tqdm(file_paths, desc="Validating schemas"):
        is_valid, error, current_format = validate_schema(file_path)
        
        if not is_valid:
            raise ValueError(f"Invalid schema in {file_path}: {error}")
        
        if file_format is None:
            file_format = current_format
        elif file_format != current_format:
            raise ValueError(
                f"Inconsistent file formats: Found both {file_format} and {current_format}"
            )
    
    return file_format


def extract_source_from_path(file_path: str) -> str:
    """Extract the source dataset from a file path.
    
    Looks for 'source=X' in the path to identify the data source.
    
    Args:
        file_path: Path to a data file
        
    Returns:
        Source dataset name, or 'unknown' if not found
    """
    path_parts = Path(file_path).parts
    
    for part in path_parts:
        if part.startswith("source="):
            return part.split("=", 1)[1]
    
    # Get parent directory name as fallback
    parent_dir = os.path.basename(os.path.dirname(file_path))
    return parent_dir or "unknown"


def read_file_as_entries(
    file_path: str, 
    file_format: str
) -> Iterator[TaxonomicEntry]:
    """Read a data file and yield TaxonomicEntry objects.
    
    Args:
        file_path: Path to the data file
        file_format: File format ('parquet' or 'csv')
        
    Yields:
        TaxonomicEntry objects
    """
    source_dataset = extract_source_from_path(file_path)
    
    # Determine how to read the file
    if file_format == "parquet":
        df = pl.scan_parquet(file_path)
    else:  # csv
        df = pl.scan_csv(file_path)
    
    # Collect to materialize the data
    df = df.collect()
    
    # Convert rows to TaxonomicEntry objects
    for row in df.iter_rows(named=True):
        # Replace None values with empty strings for optional fields
        for key in row:
            if key != "uuid" and row[key] is None:
                row[key] = ""
        
        # Skip rows with missing uuid
        if row["uuid"] is None or row["uuid"] == "":
            continue
            
        # Create TaxonomicEntry with class_ instead of class
        entry_data = {k: v for k, v in row.items() if k != "class"}
        entry_data["class_"] = row.get("class", "")
        entry_data["source_dataset"] = source_dataset
        
        yield TaxonomicEntry(**entry_data)


def read_all_files(
    file_paths: List[str], 
    file_format: str
) -> Iterator[TaxonomicEntry]:
    """Read all data files and yield TaxonomicEntry objects.
    
    Args:
        file_paths: List of file paths to read
        file_format: File format ('parquet' or 'csv')
        
    Yields:
        TaxonomicEntry objects
    """
    total_files = len(file_paths)
    
    with tqdm(total=total_files, desc="Reading files") as pbar:
        for file_path in file_paths:
            for entry in read_file_as_entries(file_path, file_format):
                yield entry
            pbar.update(1)


def parse_input(input_path: str) -> Iterator[TaxonomicEntry]:
    """Parse input data and convert to TaxonomicEntry objects.
    
    This is the main entry point for the module.
    
    Args:
        input_path: Path to input directory or file
        
    Returns:
        Iterator of TaxonomicEntry objects
    """
    # Find all input files
    file_paths = find_input_files(input_path)
    
    # Validate all file schemas
    file_format = validate_all_files(file_paths)
    
    # Read all files and yield entries
    yield from read_all_files(file_paths, file_format)

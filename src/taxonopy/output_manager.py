"""Output generation for TaxonoPy.

This module provides functions for generating standardized output files
from taxonomic data processing results.
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union, Any
import polars as pl

from taxonopy.types.data_classes import TaxonomicEntry, ResolutionStatus, ResolutionAttempt, EntryGroupRef, QueryGroupRef
from taxonopy.constants import TAXONOMIC_RANKS
from taxonopy.input_parser import find_input_files, extract_source_from_path
from taxonopy.config import config
from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

logger = logging.getLogger(__name__)

def map_entry_to_output_format(
    entry: TaxonomicEntry,
    resolution_status: Optional[ResolutionStatus] = None,
    resolved_classification: Optional[Dict[str, str]] = None,
    resolution_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Map a taxonomic entry to the standard output format.
    
    Args:
        entry: The taxonomic entry to map
        resolution_status: Optional status from resolution process
        resolved_classification: Optional resolved taxonomic classification
        resolution_metadata: Optional metadata from resolution process
        
    Returns:
        Dictionary with standardized fields for output
    """
    # Start with basic fields
    result = {
        "uuid": entry.uuid,
        "scientific_name": entry.scientific_name or "",
        "common_name": entry.common_name or "",
        "source_dataset": entry.source_dataset or "",
        "source_id": entry.source_id or "",
        "resolution_status": (resolution_status or ResolutionStatus.FORCE_ACCEPTED).name,
    }
    
    # Add all taxonomic ranks
    for rank in TAXONOMIC_RANKS:
        field_name = 'class' if rank == 'class_' else rank      
          
        # If we have a resolved classification, use it
        if resolved_classification and rank in resolved_classification:
            result[field_name] = resolved_classification[rank]
        # Otherwise preserve the original data
        else:
            source_value = getattr(entry, rank) or ""
            result[field_name] = source_value
    
    # Add resolution path if applicable
    if resolution_status in [
        ResolutionStatus.EXACT_MATCH,
        ResolutionStatus.FUZZY_MATCH,
        ResolutionStatus.PARTIAL_MATCH
    ]:
        result["resolution_path"] = "RESOLVED"
    elif resolution_status == ResolutionStatus.FORCE_ACCEPTED:
        result["resolution_path"] = "FORCED"
    else:
        result["resolution_path"] = "UNSOLVED"
    
    # Add additional metadata if provided
    if resolution_metadata:
        # Add relevant metadata fields to the output
        for key, value in resolution_metadata.items():
            # Only include primitive types
            if isinstance(value, (str, int, float, bool)) and key not in result:
                result[f"meta_{key}"] = value
    
    return result

def generate_forced_output(
    input_path: str,
    output_dir: str,
    output_format: str = "parquet"
) -> List[str]:
    """Generate forced output files from input files.
    
    This function reads input files and generates corresponding forced output files,
    bypassing taxonomic resolution.
    
    Args:
        input_path: Path to input directory or file
        output_dir: Directory to save output files
        output_format: Output file format (parquet or csv)
        
    Returns:
        List of generated output file paths
    """
    # Find all input files
    input_files = find_input_files(input_path)
    
    # Create output directory if it doesn't exist
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    
    generated_files = []
    
    # Process each input file
    for input_file in input_files:
        logger.info(f"Processing {input_file} for forced output")
        
        # Determine output file path
        input_file_name = os.path.basename(input_file)
        base_name = os.path.splitext(input_file_name)[0]
        output_file_name = f"{base_name}.forced.{output_format}"
        output_file_path = output_dir_path / output_file_name
        
        # Read input data
        try:
            if input_file.endswith(".parquet"):
                df = pl.read_parquet(input_file)
            else:  # csv
                df = pl.read_csv(input_file)
        except Exception as e:
            logger.error(f"Error reading {input_file}: {e}")
            continue
        
        # Extract source dataset
        source_dataset = extract_source_from_path(input_file)
        
        # Process each entry
        output_rows = []
        for row_dict in df.to_dicts():
            # Handle 'class' field by mapping to 'class_' for TaxonomicEntry
            if "class" in row_dict and "class_" not in row_dict:
                row_dict["class_"] = row_dict.pop("class")
            
            # Create TaxonomicEntry
            entry = TaxonomicEntry(
                uuid=row_dict.get("uuid", ""),
                kingdom=row_dict.get("kingdom", ""),
                phylum=row_dict.get("phylum", ""),
                class_=row_dict.get("class_", ""),
                order=row_dict.get("order", ""),
                family=row_dict.get("family", ""),
                genus=row_dict.get("genus", ""),
                species=row_dict.get("species", ""),
                scientific_name=row_dict.get("scientific_name", ""),
                common_name=row_dict.get("common_name", ""),
                source_id=row_dict.get("source_id", ""),
                source_dataset=source_dataset
            )
            
            # Map to output format
            output_row = map_entry_to_output_format(
                entry,
                resolution_status=ResolutionStatus.FORCE_ACCEPTED
            )
            
            output_rows.append(output_row)
        
        # Create DataFrame from output rows
        output_df = pl.DataFrame(output_rows)
        
        # Write output file
        try:
            if output_format == "parquet":
                output_df.write_parquet(output_file_path)
            else:  # csv
                output_df.write_csv(output_file_path)
                
            logger.info(f"Wrote forced output to {output_file_path}")
            generated_files.append(str(output_file_path))
            
        except Exception as e:
            logger.error(f"Error writing output to {output_file_path}: {e}")
            
    return generated_files

def map_resolution_results_to_entries(
    entry_groups: List[EntryGroupRef],
    query_groups: List[QueryGroupRef],
    resolution_manager: ResolutionAttemptManager
) -> Dict[str, ResolutionAttempt]:
    """Map resolution results to individual entry UUIDs.
    
    This function creates a mapping from entry UUID to its corresponding
    resolution attempt, allowing for efficient lookup during output generation.
    
    Args:
        entry_groups: List of entry groups
        query_groups: List of query groups
        resolution_manager: The resolution attempt manager
        
    Returns:
        Dictionary mapping entry UUID to ResolutionAttempt
    """
    # Create a mapping from entry group key to entry group
    entry_group_map = {group.key: group for group in entry_groups}
    
    # Create a mapping from query term to query group
    query_group_map = {group.query_term: group for group in query_groups}
    
    # Initialize the mapping from UUID to resolution attempt
    uuid_to_attempt = {}
    
    # Process each query group
    for query_group in query_groups:
        # Get the latest resolution attempt for this query group
        latest_attempt = resolution_manager.get_latest_attempt(query_group.query_term)
        
        if not latest_attempt:
            logger.warning(f"No resolution attempt found for query group {query_group.query_term}")
            continue
        
        # For each entry group in this query group
        for entry_group_key in query_group.entry_group_keys:
            entry_group = entry_group_map.get(entry_group_key)
            
            if not entry_group:
                logger.warning(f"Entry group {entry_group_key} not found")
                continue
            
            # Map each entry UUID to this resolution attempt
            for uuid in entry_group.entry_uuids:
                uuid_to_attempt[uuid] = latest_attempt
    
    logger.info(f"Mapped resolution results to {len(uuid_to_attempt)} entries")
    return uuid_to_attempt

def generate_resolution_output(
    input_path: str,
    output_dir: str,
    resolution_manager: ResolutionAttemptManager,
    entry_groups: List[EntryGroupRef],
    query_groups: List[QueryGroupRef],
    output_format: str = "parquet"
) -> Tuple[List[str], List[str]]:
    """Generate resolved and unsolved output files from resolution attempts.
    
    This function reads input files and generates corresponding resolved and unsolved
    output files based on resolution attempts.
    
    Args:
        input_path: Path to input directory or file
        output_dir: Directory to save output files
        resolution_manager: The resolution attempt manager
        entry_groups: List of entry groups
        query_groups: List of query groups
        output_format: Output file format (parquet or csv)
        
    Returns:
        Tuple of (resolved_files, unsolved_files)
    """
    # Find all input files
    input_files = find_input_files(input_path)
    
    # Create output directory if it doesn't exist
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    
    # Map resolution results to entry UUIDs
    uuid_to_attempt = map_resolution_results_to_entries(entry_groups, query_groups, resolution_manager)
    
    resolved_files = []
    unsolved_files = []
    
    # Process each input file
    for input_file in input_files:
        logger.info(f"Processing {input_file} for resolution output")
        
        # Determine base output file path
        input_file_name = os.path.basename(input_file)
        base_name = os.path.splitext(input_file_name)[0]
        
        # Define output file paths
        resolved_file_name = f"{base_name}.resolved.{output_format}"
        unsolved_file_name = f"{base_name}.unsolved.{output_format}"
        resolved_file_path = output_dir_path / resolved_file_name
        unsolved_file_path = output_dir_path / unsolved_file_name
        
        # Read input data
        try:
            if input_file.endswith(".parquet"):
                df = pl.read_parquet(input_file)
            else:  # csv
                df = pl.read_csv(input_file)
        except Exception as e:
            logger.error(f"Error reading {input_file}: {e}")
            continue
        
        # Extract source dataset
        source_dataset = extract_source_from_path(input_file)
        
        # Containers for resolved and unsolved entries
        resolved_rows = []
        unsolved_rows = []
        
        # Process each entry
        for row_dict in df.to_dicts():
            # Handle 'class' field by mapping to 'class_' for TaxonomicEntry
            if "class" in row_dict and "class_" not in row_dict:
                row_dict["class_"] = row_dict.pop("class")
            
            # Skip entries without a UUID
            uuid = row_dict.get("uuid")
            if not uuid:
                logger.warning(f"Entry without UUID found in {input_file}, skipping")
                continue
            
            # Create TaxonomicEntry
            entry = TaxonomicEntry(
                uuid=uuid,
                kingdom=row_dict.get("kingdom", ""),
                phylum=row_dict.get("phylum", ""),
                class_=row_dict.get("class_", ""),
                order=row_dict.get("order", ""),
                family=row_dict.get("family", ""),
                genus=row_dict.get("genus", ""),
                species=row_dict.get("species", ""),
                scientific_name=row_dict.get("scientific_name", ""),
                common_name=row_dict.get("common_name", ""),
                source_id=row_dict.get("source_id", ""),
                source_dataset=source_dataset
            )
            
            # Get the resolution attempt for this entry
            attempt = uuid_to_attempt.get(uuid)
            
            if attempt and attempt.is_successful:
                # Process resolved entry
                output_row = map_entry_to_output_format(
                    entry,
                    resolution_status=attempt.status,
                    resolved_classification=attempt.resolved_classification,
                    resolution_metadata=attempt.metadata
                )
                resolved_rows.append(output_row)
            else:
                # Process unsolved entry
                status = attempt.status if attempt else ResolutionStatus.UNPROCESSED
                output_row = map_entry_to_output_format(
                    entry,
                    resolution_status=status,
                    resolution_metadata=attempt.metadata if attempt else None
                )
                unsolved_rows.append(output_row)
        
        # Write the output files if they have entries
        if resolved_rows:
            try:
                resolved_df = pl.DataFrame(resolved_rows)
                if output_format == "parquet":
                    resolved_df.write_parquet(resolved_file_path)
                else:  # csv
                    resolved_df.write_csv(resolved_file_path)
                
                logger.info(f"Wrote {len(resolved_rows)} resolved entries to {resolved_file_path}")
                resolved_files.append(str(resolved_file_path))
            except Exception as e:
                logger.error(f"Error writing resolved output to {resolved_file_path}: {e}")
        
        if unsolved_rows:
            try:
                unsolved_df = pl.DataFrame(unsolved_rows)
                if output_format == "parquet":
                    unsolved_df.write_parquet(unsolved_file_path)
                else:  # csv
                    unsolved_df.write_csv(unsolved_file_path)
                
                logger.info(f"Wrote {len(unsolved_rows)} unsolved entries to {unsolved_file_path}")
                unsolved_files.append(str(unsolved_file_path))
            except Exception as e:
                logger.error(f"Error writing unsolved output to {unsolved_file_path}: {e}")
    
    logger.info(f"Generated {len(resolved_files)} resolved files and {len(unsolved_files)} unsolved files")
    return (resolved_files, unsolved_files)

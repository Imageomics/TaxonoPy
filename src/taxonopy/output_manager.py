import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union, Any
import polars as pl
from tqdm import tqdm

from taxonopy.types.data_classes import (
    TaxonomicEntry,
    ResolutionStatus,
    ResolutionAttempt,
    EntryGroupRef,
)
from taxonopy.constants import TAXONOMIC_RANKS
from taxonopy.input_parser import find_input_files, extract_source_from_path, REQUIRED_COLUMNS
from taxonopy.config import config
from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

logger = logging.getLogger(__name__)

def map_entry_to_output_format(
    entry: TaxonomicEntry,
    final_attempt: Optional[ResolutionAttempt] = None
) -> Dict[str, Any]:
    """Map a taxonomic entry and its final resolution attempt to the standard output format.

    Args:
        entry: The taxonomic entry to map.
        final_attempt: The final ResolutionAttempt object for this entry's group.

    Returns:
        Dictionary with standardized fields for output.
    """
    # Determine status and classification from the final attempt
    status = ResolutionStatus.FAILED # Default if no attempt found
    resolved_classification = None
    resolution_info = {} # For storing error, strategy, etc.

    if final_attempt:
        status = final_attempt.status
        if final_attempt.is_successful:
            resolved_classification = final_attempt.resolved_classification
        # Populate resolution_info from the attempt
        if final_attempt.error: resolution_info['error'] = final_attempt.error
        if final_attempt.failure_reason: resolution_info['failure_reason'] = final_attempt.failure_reason
        if final_attempt.resolution_strategy_name: resolution_info['resolution_strategy_name'] = final_attempt.resolution_strategy_name
        if final_attempt.metadata: resolution_info['metadata'] = final_attempt.metadata
        # Add query info used for the final successful/failed step (optional but useful)
        resolution_info['final_query_term'] = final_attempt.query_term
        resolution_info['final_query_rank'] = final_attempt.query_rank
        resolution_info['final_data_source_id'] = final_attempt.data_source_id
    else:
        # Handle case where an entry somehow didn't get a final attempt mapped
        status = ResolutionStatus.FAILED
        resolution_info['error'] = "Entry not mapped to any resolution attempt"
        resolution_info['failure_reason'] = "Processing error or missing attempt"

    # Build the output row
    result = {
        "uuid": entry.uuid,
        "scientific_name": entry.scientific_name or "",
        "common_name": entry.common_name or "",
        "source_dataset": entry.source_dataset or "",
        "source_id": entry.source_id or "",
        "resolution_status": status.name, # Use name from the final status
    }

    # Add all taxonomic ranks
    for rank_field in TAXONOMIC_RANKS:
        field_name = 'class' if rank_field == 'class_' else rank_field
        resolved_value = None
        is_successful = final_attempt.is_successful if final_attempt else False # Get success status safely

        # Check if resolution was successful AND the classification dictionary exists
        if is_successful and resolved_classification:
             # Attempt to get the value for this specific rank from the resolved data
            resolved_value = resolved_classification.get(rank_field)

        if resolved_value is not None:
            # If we got a resolved value for this rank (from the stored dictionary)
            result[field_name] = resolved_value
        elif is_successful:
            # If resolution was successful overall, but this specific rank
            # is missing from the stored resolved_classification (e.g., below the retry cutoff),
            # output an empty string, effectively nullifying the original input for this rank.
            result[field_name] = ""
        else:
            # If resolution was not successful (FAILED, EXHAUSTED, etc.) or no attempt exists,
            # fall back to the original input value for this rank.
            source_value = getattr(entry, rank_field, None) or ""
            result[field_name] = source_value

    # Determine resolution path based on final status
    if status == ResolutionStatus.FORCE_ACCEPTED:
        result["resolution_path"] = "FORCED" # Keep forced status separate
    elif status.is_successful:
        result["resolution_path"] = "RESOLVED"
    else:
        result["resolution_path"] = "UNSOLVED" # Includes FAILED, EXHAUSTED, etc.


    # Add additional diagnostic info if available
    if 'error' in resolution_info:
         result['resolution_error'] = str(resolution_info['error'])
    if 'failure_reason' in resolution_info:
         result['resolution_failure_reason'] = str(resolution_info['failure_reason'])
    if 'resolution_strategy_name' in resolution_info:
         result['resolution_strategy'] = str(resolution_info['resolution_strategy_name'])
    # Add optional final query info
    if 'final_query_term' in resolution_info: result['final_query_term'] = resolution_info['final_query_term']
    if 'final_query_rank' in resolution_info: result['final_query_rank'] = resolution_info['final_query_rank']
    if 'final_data_source_id' in resolution_info: result['final_data_source_id'] = resolution_info['final_data_source_id']

    # Add generic metadata fields if needed (prefixing)
    if 'metadata' in resolution_info and isinstance(resolution_info['metadata'], dict):
         for key, value in resolution_info['metadata'].items():
              # Check type and avoid overwriting existing keys
              if isinstance(value, (str, int, float, bool)) and f"meta_{key}" not in result:
                  result[f"meta_{key}"] = value

    return result

def map_resolution_results_to_entries(
    resolution_manager: ResolutionAttemptManager,
    entry_group_map: Dict[str, EntryGroupRef]
) -> Dict[str, ResolutionAttempt]:
    """
    Maps final resolution results (latest attempts) to individual entry UUIDs.

    Iterates through the final state recorded in the resolution manager.

    Args:
        resolution_manager: Manager holding the final resolution states.
        entry_group_map: Dictionary mapping entry group keys to objects.

    Returns:
        Dictionary mapping individual entry UUIDs (str) to their final
        ResolutionAttempt object.
    """
    uuid_to_final_attempt: Dict[str, ResolutionAttempt] = {}
    processed_groups = 0
    mapped_uuids = 0

    logger.info("Mapping final resolution attempts to individual entry UUIDs...")
    # Iterate through the manager's record of the latest attempt for each group
    for entry_group_key, latest_attempt_key in tqdm(
        resolution_manager._entry_group_latest_attempt.items(),
        desc="Mapping results to entries"
    ):
        # Get the final attempt object
        final_attempt = resolution_manager.get_attempt(latest_attempt_key)
        if not final_attempt:
            logger.warning(f"Final attempt object not found for key: {latest_attempt_key} (referenced by group {entry_group_key}). Skipping group.")
            continue

        # Get the corresponding EntryGroupRef to find the UUIDs
        entry_group = entry_group_map.get(entry_group_key)
        if not entry_group:
            logger.warning(f"EntryGroupRef not found for key: {entry_group_key} while mapping final attempt {latest_attempt_key}. Skipping group.")
            continue

        # Map this final attempt to all UUIDs within the group
        for uuid in entry_group.entry_uuids:
            if uuid in uuid_to_final_attempt:
                 # This shouldn't happen if entry grouping is correct, but log if it does
                 logger.warning(f"UUID {uuid} is being mapped to a final attempt ({final_attempt.key}) but was already mapped previously. Check grouping logic.")
            uuid_to_final_attempt[uuid] = final_attempt
            mapped_uuids += 1
        processed_groups += 1

    logger.info(f"Mapped final resolution results for {processed_groups} entry groups to {mapped_uuids} individual entries.")
    return uuid_to_final_attempt

def generate_resolution_output(
    input_path: str,
    output_dir: str,
    resolution_manager: ResolutionAttemptManager,
    entry_group_map: Dict[str, EntryGroupRef],
    output_format: str = "parquet"
) -> Tuple[List[str], List[str]]:
    """Generate resolved and unsolved output files from final resolution attempts.

    Args:
        input_path: Path to input directory or file.
        output_dir: Directory to save output files, preserving input directory structure.
        resolution_manager: Manager holding final resolution attempt states.
        entry_group_map: Dictionary mapping entry group keys to objects.
        output_format: Output file format ('parquet' or 'csv').

    Returns:
        Tuple of (list_of_resolved_files, list_of_unsolved_files).
    """
    input_files = find_input_files(input_path)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    # Use the refactored mapping function
    logger.info("Creating mapping from entry UUIDs to final resolution attempts...")
    uuid_to_final_attempt = map_resolution_results_to_entries(
        resolution_manager, entry_group_map
    )

    resolved_files = []
    unsolved_files = []

    for input_file in input_files:
        logger.info(f"Generating resolution output for: {input_file}")

        input_file_name = os.path.basename(input_file)

        # Preserve directory structure
        rel_path = os.path.relpath(input_file, input_path if os.path.isdir(input_path) else os.path.dirname(input_path))
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        rel_dir = os.path.dirname(rel_path)
        
        resolved_dir = os.path.join(output_dir, rel_dir)
        unsolved_dir = os.path.join(output_dir, rel_dir)
        os.makedirs(resolved_dir, exist_ok=True)
        os.makedirs(unsolved_dir, exist_ok=True)
        
        resolved_file_name = f"{base_name}.resolved.{output_format}"
        unsolved_file_name = f"{base_name}.unsolved.{output_format}"
        resolved_file_path = os.path.join(resolved_dir, resolved_file_name)
        unsolved_file_path = os.path.join(unsolved_dir, unsolved_file_name)

        try:
            if input_file.endswith(".parquet"):
                df = pl.read_parquet(input_file)
            else:
                # Define dtypes based on REQUIRED_COLUMNS for robustness
                dtypes = {col: pl.Utf8 for col in REQUIRED_COLUMNS if col != 'class'}
                dtypes['class'] = pl.Utf8 # Ensure class is read as Utf8
                df = pl.read_csv(input_file, dtypes=dtypes, try_parse_dates=False) # Avoid auto date parsing
        except Exception as e:
            logger.error(f"Error reading input file {input_file}: {e}")
            continue

        source_dataset = extract_source_from_path(input_file)
        resolved_rows = []
        unsolved_rows = []

        # Iterate through input rows
        for row_dict in tqdm(df.to_dicts(), desc=f"Processing {input_file_name}", leave=False):
            if "class" in row_dict and "class_" not in row_dict:
                row_dict["class_"] = row_dict.pop("class")

            uuid = row_dict.get("uuid")
            if not uuid:
                logger.warning(f"Entry without UUID found in {input_file}, skipping")
                continue

            try:
                # Create TaxonomicEntry, provide None defaults for missing optional keys
                entry = TaxonomicEntry(
                    uuid=uuid,
                    kingdom=row_dict.get("kingdom"),
                    phylum=row_dict.get("phylum"),
                    class_=row_dict.get("class_"),
                    order=row_dict.get("order"),
                    family=row_dict.get("family"),
                    genus=row_dict.get("genus"),
                    species=row_dict.get("species"),
                    scientific_name=row_dict.get("scientific_name"),
                    common_name=row_dict.get("common_name"),
                    source_id=row_dict.get("source_id"),
                    source_dataset=source_dataset
                )
            except (TypeError, KeyError) as te:
                 logger.error(f"Error creating TaxonomicEntry for UUID {uuid} from row: {row_dict}. Error: {te}")
                 continue

            # Get the FINAL resolution attempt for this entry's UUID
            final_attempt = uuid_to_final_attempt.get(uuid) # Returns None if UUID wasn't mapped

            # Map entry and its final attempt to the output row format
            output_row = map_entry_to_output_format(entry, final_attempt)

            # Append to the correct list based on the final status
            if final_attempt and final_attempt.is_successful:
                 resolved_rows.append(output_row)
            else:
                 # Includes cases where final_attempt is None (mapping failed) or status is failure/exhausted
                 unsolved_rows.append(output_row)

        # Write output files
        if resolved_rows:
            try:
                resolved_df = pl.DataFrame(resolved_rows)
                # Explicitly define schema for consistency? Optional.
                if output_format == "parquet":
                    resolved_df.write_parquet(resolved_file_path)
                else:
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
                else:
                    unsolved_df.write_csv(unsolved_file_path)
                logger.info(f"Wrote {len(unsolved_rows)} unsolved entries to {unsolved_file_path}")
                unsolved_files.append(str(unsolved_file_path))
            except Exception as e:
                 logger.error(f"Error writing unsolved output to {unsolved_file_path}: {e}")

    logger.info("Completed output generation.")
    return resolved_files, unsolved_files

def generate_forced_output(
    input_path: str,
    output_dir: str,
    output_format: str = "parquet"
) -> List[str]:
    """Generate forced output files from input files, bypassing resolution.
    
    Preserves the directory structure from the input path.
    """
    input_files = find_input_files(input_path)
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    generated_files = []

    for input_file in input_files:
         try:
             if input_file.endswith(".parquet"):
                 df = pl.read_parquet(input_file)
             else:
                 dtypes = {col: pl.Utf8 for col in REQUIRED_COLUMNS if col != 'class'}
                 dtypes['class'] = pl.Utf8
                 df = pl.read_csv(input_file, dtypes=dtypes, try_parse_dates=False)
         except Exception as e:
             logger.error(f"Error reading input file {input_file} for forced output: {e}")
             continue

         source_dataset = extract_source_from_path(input_file)
         output_rows = []

         for row_dict in tqdm(df.to_dicts(), desc=f"Forcing {os.path.basename(input_file)}", leave=False):
            if "class" in row_dict and "class_" not in row_dict:
                 row_dict["class_"] = row_dict.pop("class")

            uuid = row_dict.get("uuid")
            if not uuid: continue

            try:
                 entry = TaxonomicEntry(
                     uuid=uuid,
                     kingdom=row_dict.get("kingdom"), phylum=row_dict.get("phylum"),
                     class_=row_dict.get("class_"), order=row_dict.get("order"),
                     family=row_dict.get("family"), genus=row_dict.get("genus"),
                     species=row_dict.get("species"), scientific_name=row_dict.get("scientific_name"),
                     common_name=row_dict.get("common_name"), source_id=row_dict.get("source_id"),
                     source_dataset=source_dataset
                 )
            except (TypeError, KeyError) as te:
                  logger.error(f"Forced output: Error creating TaxonomicEntry for UUID {uuid} from row: {row_dict}. Error: {te}")
                  continue

            # Map to output format with FORCE_ACCEPTED status (pass None for attempt)
            output_row = map_entry_to_output_format(
                 entry=entry,
                 final_attempt=None # Indicate no resolution attempt was made
                 # Override status specifically for forced output
            )
            # Manually set forced status after default mapping
            output_row["resolution_status"] = ResolutionStatus.FORCE_ACCEPTED.name
            output_row["resolution_path"] = "FORCED"

            output_rows.append(output_row)

         if output_rows:
            try:
                output_df = pl.DataFrame(output_rows)

                # Preserve directory structure
                rel_path = os.path.relpath(input_file, input_path if os.path.isdir(input_path) else os.path.dirname(input_path))
                base_name = os.path.splitext(os.path.basename(input_file))[0]
                rel_dir = os.path.dirname(rel_path)
                
                output_dir_for_file = os.path.join(output_dir, rel_dir)
                os.makedirs(output_dir_for_file, exist_ok=True)
                
                output_file_name = f"{base_name}.forced.{output_format}"
                output_file_path = os.path.join(output_dir_for_file, output_file_name)

                if output_format == "parquet":
                    output_df.write_parquet(output_file_path)
                else:
                    output_df.write_csv(output_file_path)

                logger.info(f"Wrote forced output ({len(output_rows)} entries) to {output_file_path}")
                generated_files.append(str(output_file_path))
            except Exception as e:
                logger.error(f"Error writing forced output for {input_file} to {output_file_path}: {e}")

    return generated_files

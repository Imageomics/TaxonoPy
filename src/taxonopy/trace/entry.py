import dataclasses
import json
import logging
from taxonopy.input_parser import parse_input_list
from taxonopy.entry_grouper import create_entry_groups

logger = logging.getLogger(__name__)

def make_serializable(obj):
    """
    Recursively convert objects (e.g. frozensets) to JSON-serializable types.
    """
    if isinstance(obj, frozenset):
        return list(obj)
    elif isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_serializable(item) for item in obj]
    else:
        return obj

def trace_entry(uuid: str, input_path: str, output_format: str = "text", verbose: bool = False) -> int:    
    """
    Trace a taxonomic entry by its UUID.

    This function:
    - Reads the input dataset (using the cached input parser).
    - Searches for the TaxonomicEntry with the given UUID.
    - Locates the associated EntryGroupRef.
    - Retrieves the initial query plan for the entry group
    - (Optionally) includes the corresponding ResolutionAttempt if available.
      
    The resulting trace shows the provenance from the raw entry through its grouping,
    query planning, and (if present) resolution.

    Args:
        uuid: The UUID of the taxonomic entry to trace.
        input_path: Path to the input dataset.
        output_format: "json" or "text" (default "text").
        verbose: Whether to include all UUIDs in the entry group (default False).

    Returns:
        0 on success, or a nonzero error code.
    """
    try:
        entries = parse_input_list(input_path)
    except Exception as e:
        logger.error(f"Error parsing input from {input_path}: {e}")
        return 1

    # Find the matching TaxonomicEntry.
    matching_entry = None
    for entry in entries:
        if entry.uuid == uuid:
            matching_entry = entry
            break

    if not matching_entry:
        logger.error(f"No entry found with UUID: {uuid}")
        return 1

    # Retrieve the entry groups.
    try:
        _, entry_group_map = create_entry_groups(input_path)
    except Exception as e:
        logger.error(f"Error grouping entries: {e}")
        entry_group_map = {}

    matching_group = None
    for group_key, group in entry_group_map.items():
        if uuid in group.entry_uuids:
            matching_group = group
            break

    trace_result = {
        "entry": dataclasses.asdict(matching_entry),
    }

    if matching_group:
        # Convert the group to a dict and add the computed key property
        group_dict = dataclasses.asdict(matching_group)
        group_dict["key"] = matching_group.key

        if not verbose and "entry_uuids" in group_dict and len(group_dict["entry_uuids"]) > 3:
            # Take first 3 UUIDs and add count indicator
            full_count = len(group_dict["entry_uuids"])
            # Convert to list first since entry_uuids is a frozenset
            uuids_list = list(group_dict["entry_uuids"])
            group_dict["entry_uuids"] = uuids_list[:3]
            group_dict["entry_uuids_note"] = f"Showing 3 of {full_count} UUIDs. Use --verbose to see all."
        
        group_dict["group_count"] = matching_group.group_count
        trace_result["group"] = group_dict
        
        # Get the initial query plan for this entry group
        from taxonopy.query.planner import plan_initial_queries
        entry_group_map = {matching_group.key: matching_group}
        query_plans = plan_initial_queries(entry_group_map)
        initial_plan = query_plans.get(matching_group.key)
        if initial_plan:
            trace_result["query_plan"] = dataclasses.asdict(initial_plan)
        
        # Load attempt chain from cache using the existing infrastructure
        from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
        resolution_attempts = ResolutionAttemptManager.load_chain_from_cache(matching_group.key)
        if resolution_attempts:
            trace_result["resolution_attempts"] = resolution_attempts
        else:
            trace_result["trace_note"] = "No resolution attempts found for this entry group."
    else:
        # No matching group found
        trace_result["group"] = None
        trace_result["trace_note"] = "Entry group not found. Trace stops at the raw entry level."
            


    if output_format == "json":
        serializable_result = make_serializable(trace_result)
        print(json.dumps(serializable_result, indent=4))
    else:
        print("--- ENTRY ---")
        for key, value in dataclasses.asdict(matching_entry).items():
            print(f"{key}: {value}")
        print("\n--- GROUP ---")
        if matching_group:
            # Convert to dict for easier handling
            group_dict = dataclasses.asdict(matching_group)
            
            # Special handling for entry_uuids based on verbose flag
            uuids = list(group_dict.get("entry_uuids", []))
            total_uuids = len(uuids)
            
            # Handle most fields
            for key, value in group_dict.items():
                if key != "entry_uuids":  # Handle separately
                    print(f"{key}: {value}")
            
            # Now handle UUIDs with verbose flag consideration
            print(f"\nGroup UUIDs ({total_uuids} total):")
            if not verbose and total_uuids > 3:
                # Limited display for non-verbose mode
                for uuid_val in sorted(uuids)[:3]:
                    print(f"  {uuid_val}")
                print(f"  ... and {total_uuids - 3} more. Use --verbose to see all.")
            else:
                # Full display for verbose mode
                for uuid_val in sorted(uuids):
                    print(f"  {uuid_val}")
        else:
            print("No group found for this entry.")
        
        # Query Plan section
        if 'query_plan' in trace_result:
            print("\n--- QUERY PLAN ---")
            for key, value in trace_result['query_plan'].items():
                print(f"{key}: {value}")
                
        # Resolution Attempts section
        if 'resolution_attempts' in trace_result and trace_result['resolution_attempts']:
            print("\n--- RESOLUTION ATTEMPTS ---")
            for attempt in trace_result['resolution_attempts']:
                print(f"Status: {attempt['status']}")
                print(f"Strategy: {attempt['resolution_strategy_name'] or 'N/A'}")
                if attempt.get('resolved_classification'):
                    print("Resolved Classification:")
                    for rank, value in attempt['resolved_classification'].items():
                        print(f"  {rank}: {value}")
                print("------")
        print()

    return 0

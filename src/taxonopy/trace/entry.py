import dataclasses
import json
import logging
from taxonopy.input_parser import parse_input_list
from taxonopy.entry_grouper import create_entry_groups
from taxonopy.query.planner import plan_initial_queries

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

def trace_entry(uuid: str, input_path: str, output_format: str = "text") -> int:
    """
    Trace a taxonomic entry by its UUID.

    This function:
      - Reads the input dataset (using the cached input parser).
      - Searches for the TaxonomicEntry with the given UUID.
      - Locates the associated EntryGroupRef.
      - Computes the QueryGroupRef objects that include that entry group.
      - (Optionally) includes the corresponding ResolutionAttempt if available.
      
    The resulting trace shows the provenance from the raw entry through its grouping,
    query planning, and (if present) resolution.

    Args:
        uuid: The UUID of the taxonomic entry to trace.
        input_path: Path to the input dataset.
        output_format: "json" or "text" (default "text").

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
        entry_groups = create_entry_groups(input_path)
    except Exception as e:
        logger.error(f"Error grouping entries: {e}")
        entry_groups = []

    matching_group = None
    for group in entry_groups:
        if uuid in group.entry_uuids:
            matching_group = group
            break

    trace_result = {
        "entry": dataclasses.asdict(matching_entry),
        "group": dataclasses.asdict(matching_group) if matching_group else None,
    }

    if not matching_group:
        trace_result["trace_note"] = "Entry group not found. Trace stops at the raw entry level."
    else:
        # Compute QueryGroupRef objects from the entry groups.
        query_groups = create_initial_query_plans(entry_groups)
        matching_query_groups = [
            qg for qg in query_groups if matching_group.key in qg.entry_group_keys
        ]
        trace_result["query_groups"] = [dataclasses.asdict(qg) for qg in matching_query_groups]
        # If you have ResolutionAttempt objects (e.g. stored or computed during resolution),
        # you could add them here. For now, we set it to None.
        trace_result["resolution_attempts"] = None

    if output_format == "json":
        serializable_result = make_serializable(trace_result)
        print(json.dumps(serializable_result, indent=4))
    else:
        print("--- ENTRY ---")
        for key, value in dataclasses.asdict(matching_entry).items():
            print(f"{key}: {value}")
        print("\n--- GROUP ---")
        if matching_group:
            for key, value in dataclasses.asdict(matching_group).items():
                print(f"{key}: {value}")
        else:
            print("No group found for this entry.")
        if matching_group:
            print("\n--- QUERY GROUPS ---")
            for qg in matching_query_groups:
                for key, value in dataclasses.asdict(qg).items():
                    print(f"{key}: {value}")
                print("------")
        print()

    return 0

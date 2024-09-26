import os
import subprocess

def extract_required_ranks(entry, required_ranks):
    """
    Extracts the required taxonomic ranks from the GNVerifier output entry.
    """
    best_result = entry.get('bestResult', {})

    # Ensure paths are available in the best result
    path_segments = best_result.get('classificationPath', '').split('|')
    rank_segments = best_result.get('classificationRanks', '').lower().split('|')

    filtered_classification = {}
    for rank, name in zip(rank_segments, path_segments):
        if rank in required_ranks:
            filtered_classification[rank] = name

    return {
        "supplied_name": entry.get("name"),
        "matched_name": best_result.get("matchedName"),
        "classification": filtered_classification
    }

def check_environment(tool):
    """
    Check if Docker or Apptainer is available on the system.
    """
    try:
        subprocess.run([tool, "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError:
        return False

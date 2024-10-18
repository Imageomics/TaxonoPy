KINGDOM_SYNONYMS = {
    'Metazoa': 'Animalia',
    'Animalia': 'Animalia',  # Ensure 'Animalia' maps to itself
}
# Archaeplastida and Plantae?

def extract_required_ranks(entry, supplied_name, required_ranks):
    """
    Extracts the required taxonomic ranks from the GNVerifier output entry.
    """
    # Ensure paths are available in the result
    path_segments = entry.get('classificationPath', '').split('|')
    rank_segments = entry.get('classificationRanks', '').lower().split('|')

    filtered_classification = {}
    for rank, name in zip(rank_segments, path_segments):
        if rank in required_ranks:
            if rank == 'kingdom':
                # Normalize the kingdom name using the KINGDOM_SYNONYMS mapping
                name = KINGDOM_SYNONYMS.get(name, name)
            filtered_classification[rank] = name

    return {
        "supplied_name": supplied_name,
        "matched_name": entry.get("matchedName"),
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

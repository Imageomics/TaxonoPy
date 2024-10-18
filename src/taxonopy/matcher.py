from taxonopy.utils import KINGDOM_SYNONYMS

def check_match_case(resolved, input_ranks, input_classification, query_term):
    """
    Logic to determine case a, b, c, d, e based on the matching of ranks.
    """
    case = 'a'  # Default case is 'a'
    resolved_ranks = []
    resolved_path = []

    for rank in input_ranks:
        input_term = input_classification.get(rank)
        resolved_term = resolved['classification'].get(rank)

        if input_term == resolved_term:
            resolved_ranks.append(rank)
            resolved_path.append(input_term)
        else:
            if rank == 'species' and resolved_term == query_term:
                # Case c: Leaf rank mismatch, use query term
                resolved_ranks.append(rank)
                resolved_path.append(query_term)
                case = 'c'
            elif resolved_term is None:
                # Handle missing ranks (Case e)
                resolved_ranks.append(rank)
                resolved_path.append(input_term)
                if not case.startswith('e-'):
                    case = f'e-{case}'
            else:
                # Case b or d: Handle mismatches at various levels
                if rank == 'kingdom':
                    case = 'd'
                else:
                    case = 'b'
                resolved_ranks.append(rank)
                resolved_path.append(resolved_term)

    return case, resolved_ranks, resolved_path

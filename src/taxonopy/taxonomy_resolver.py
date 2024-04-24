import json
from tqdm import tqdm
from opentree import OT
from taxonopy.error_handler import log_error
from taxonopy.api_service import APIService

class TaxonomyResolver:
    def __init__(self):
        self.api_service = APIService()
        self.required_ranks = ('kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species')

    def process_batch(self, names, vernaculars=False, synonyms=False):
        batch_results = []

        try:
            response = self.api_service.query_gnr(names, vernaculars=vernaculars)
            batch_result, _ = self.process_data(response, vernaculars, synonyms=synonyms)
            batch_results.extend(batch_result)
        except Exception as e:
            # If an error occurs, the whole batch failed.
            # Unbatch and process each name individually.
            # TODO: More robust, detailed error handling and logging

            print(f"Error processing batch: {str(e)}")
            print("Processing batched names individually.")
            for name in tqdm(names, desc='Processing unbatched names'):
                try:
                    response = self.api_service.query_gnr([name], vernaculars=vernaculars)
                    result, _ = self.process_data(response, vernaculars, synonyms=synonyms)
                    batch_results.extend(result)
                except Exception as inner_e:
                    # If another error occurs, sometimes it can work with `with_canonical_ranks=false`
                    print(f"Error processing '{name}': {str(inner_e)}")
                    print(f"Trying with `with_canonical_ranks=false`.")

                    try:
                        response = self.api_service.query_gnr([name], with_canonical_ranks=False, vernaculars=vernaculars)
                        result, _ = self.process_data(response, vernaculars, synonyms=synonyms)
                        batch_results.extend(result)
                    except Exception as inner_inner_e:
                        print(f"Error processing '{name}': {str(inner_inner_e)}")

        return batch_results

    def process_data(self, data, vernaculars=False, synonyms=False):
        results = []
        status = data.get('status')
        status_message = data.get('message')

        for entry in data.get('data', []):
            if 'results' in entry:
                best_match = self.determine_best_match(entry['results'], vernaculars, synonyms=synonyms)
                if best_match:
                    # Include additional fields from the entry and data levels
                    best_match.update({
                        'supplied_name_string': entry.get('supplied_name_string'),
                        'is_known_name': entry.get('is_known_name'),
                        'status': status,
                        'status_message': status_message
                    })
                    results.append(best_match)
        return results, vernaculars

    def determine_best_match(self, results, vernaculars=False, synonyms=False):
        # First try to find a direct match without using synonyms
        direct_matches = [
            result for result in results
            if self.has_exact_required_ranks(result, self.required_ranks, synonyms=synonyms)
        ]

        # If direct matches are found, return the best match from these
        if direct_matches:
            max_score = max(result['score'] for result in direct_matches)
            best_matches = [result for result in direct_matches if result['score'] == max_score]
            return self.aggregate_tied_scores(self.trim_ranks_for_matches(best_matches), vernaculars)

        # If no direct matches, then use synonyms to find a match
        synonym_matches = [
            result for result in results
            if self.has_exact_required_ranks(result, self.required_ranks, synonyms=synonyms)
        ]

        if synonym_matches:
            max_score = max(result['score'] for result in synonym_matches)
            best_matches = [result for result in synonym_matches if result['score'] == max_score]
            return self.aggregate_tied_scores(self.trim_ranks_for_matches(best_matches), vernaculars)

        # If no matches at all, return None
        return None

    def trim_ranks_for_matches(self, matches):
        return [self.trim_ranks(match, self.required_ranks) for match in matches]

        
    def trim_ranks(self, result, required_ranks):
        # Split classification path and its corresponding ranks
        path_segments = result['classification_path'].split('|')
        rank_segments = result['classification_path_ranks'].lower().split('|')
        
        # Filter out the segments corresponding with required ranks
        trimmed_path = []
        trimmed_ranks = []
        for path, rank in zip(path_segments, rank_segments):
            if rank in required_ranks:
                trimmed_path.append(path)
                trimmed_ranks.append(rank)
        
        # Update the result with the trimmed path and ranks
        result['classification_path'] = '|'.join(trimmed_path)
        result['classification_path_ranks'] = '|'.join(trimmed_ranks)
        return result
    
   
    def has_exact_required_ranks(self, result, required_ranks, synonyms=False):
        path = result.get('classification_path', '')
        path_ranks = result.get('classification_path_ranks', '')

        if path and path_ranks:
            path = path.split('|')
            path_ranks = path_ranks.split('|')
            canonical_form = result.get('canonical_form', '')

            # Check direct match first
            if canonical_form in path:
                index = path.index(canonical_form)
                input_rank = path_ranks[index].strip().lower() if index < len(path_ranks) else ''

                if input_rank and input_rank in required_ranks:
                    observed_ranks = {rank.strip().lower() for rank in path_ranks[:index + 1] if rank.strip()}
                    required_up_to_input = [rank for rank in required_ranks if required_ranks.index(rank) <= required_ranks.index(input_rank)]
                    return set(required_up_to_input) <= observed_ranks

            # If no direct match and synonyms are allowed, check synonyms
            if synonyms:
                synonym_or_name = self.resolve_using_synonyms(canonical_form, path)
                if synonym_or_name and synonym_or_name in path:
                    index = path.index(synonym_or_name)
                    input_rank = path_ranks[index].strip().lower() if index < len(path_ranks) else ''
                    if input_rank and input_rank in required_ranks:
                        observed_ranks = {rank.strip().lower() for rank in path_ranks[:index + 1] if rank.strip()}
                        required_up_to_input = [rank for rank in required_ranks if required_ranks.index(rank) <= required_ranks.index(input_rank)]
                        return set(required_up_to_input) <= observed_ranks

        return False

    def resolve_using_synonyms(self, canonical_form, path):
        print("")
        print(f"Resolving '{canonical_form}' using synonyms...")
        print(f"Path: {path}")
        print("")
        # Initialize OTT ID outside the try block to handle scope
        ott_id = None

        try:
            # Attempt to fetch synonyms for the canonical_form
            ott_id = OT.get_ottid_from_name(canonical_form)
            taxon_info = OT.taxon_info(ott_id=ott_id)
            synonyms = taxon_info.response_dict.get('synonyms', [])
        except Exception as e:
            print(f"Error fetching synonyms for '{canonical_form}': {str(e)}")
            synonyms = []

        # Check if any synonyms match the classification path
        matched_synonym = next((syn for syn in synonyms if syn in path), None)
        if matched_synonym:
            return matched_synonym 

        # If no direct synonyms match, check each path term from the end towards the beginning for synonyms that match the canonical_form
        total = len(path)
        for term in tqdm(reversed(path), desc="Checking synonyms from most to least specific (stop on first match)", total=total):
            try:
                ott_id_term = OT.get_ottid_from_name(term)
                taxon_info_term = OT.taxon_info(ott_id=ott_id_term)
                synonyms_term = taxon_info_term.response_dict.get('synonyms', [])
            except Exception as e:
                print(f"Error fetching synonyms for term '{term}' in path: {str(e)}")
                continue

            if canonical_form in synonyms_term:
                return term 

        return None

    def resolve_names(self, names, vernaculars=False, synonyms=False):
        # TODO: optimize batch size
        batch_size = 10
        batches = [names[i:i + batch_size] for i in range(0, len(names), batch_size)]
        all_results = []

        for batch in tqdm(batches, desc='Processing batches'):
            batch_results = self.process_batch(batch, vernaculars=vernaculars, synonyms=synonyms)
            all_results.extend(batch_results)
            self.save_results(batch_results)
        return all_results, vernaculars

    def aggregate_tied_scores(self, results, vernaculars):
        aggregated_info = {
            'supplied_name_string': results[0].get('supplied_name_string'),
            'is_known_name': results[0].get('is_known_name'),
            'data_source_id': [result['data_source_id'] for result in results],
            'gni_uuid': [result.get('gni_uuid') for result in results],
            'name_string': [result.get('name_string') for result in results],
            'canonical_form': [result.get('canonical_form') for result in results],
            'classification_path': [result.get('classification_path') for result in results], # TODO: address cases of discrepant paths among sources
            'classification_path_ids': [result.get('classification_path_ids') for result in results],
            'classification_path_ranks': [result.get('classification_path_ranks') for result in results],
            'taxon_id': [result.get('taxon_id') for result in results],
            'local_id': [result.get('local_id') for result in results],
            'match_type': [result['match_type'] for result in results],
            'match_value': [result['match_value'] for result in results],
            'prescore': [result.get('prescore') for result in results],
            'imported_at': [result.get('imported_at') for result in results],
            'current_taxon_id': [result.get('current_taxon_id') for result in results],
            'score': results[0]['score'],
            'status': results[0].get('status'),
            'status_message': results[0].get('status_message'),
            'sources': [result['data_source_title'] for result in results],
            'data_source_ids': [result['data_source_id'] for result in results],
        }

        if vernaculars:
            aggregated_info['vernaculars'] = [result.get('vernaculars') for result in results if 'vernaculars' in result]

        return aggregated_info

    # TODO: decide on a better way to save results
    def save_results(self, data):
        with open('resolved_taxonomies.jsonl', 'a', encoding='utf-8') as f:
            for entry in data:
                json.dump(entry, f, ensure_ascii=False)
                f.write('\n')

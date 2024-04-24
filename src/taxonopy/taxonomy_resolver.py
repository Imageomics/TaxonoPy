import json
from tqdm import tqdm
from taxonopy.error_handler import log_error
from taxonopy.api_service import APIService

class TaxonomyResolver:
    def __init__(self):
        self.api_service = APIService()
        self.required_ranks = ('kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species')

    def process_batch(self, names, vernaculars=False):
        batch_results = []

        try:
            response = self.api_service.query_gnr(names, vernaculars=vernaculars)
            batch_result, _ = self.process_data(response, vernaculars)
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
                    result, _ = self.process_data(response, vernaculars)
                    batch_results.extend(result)
                except Exception as inner_e:
                    # If another error occurs, sometimes it can work with `with_canonical_ranks=false`
                    print(f"Error processing '{name}': {str(inner_e)}")
                    print(f"Trying with `with_canonical_ranks=false`.")

                    try:
                        response = self.api_service.query_gnr([name], with_canonical_ranks=False, vernaculars=vernaculars)
                        result, _ = self.process_data(response, vernaculars)
                        batch_results.extend(result)
                    except Exception as inner_inner_e:
                        print(f"Error processing '{name}': {str(inner_inner_e)}")

        return batch_results

    def process_data(self, data, vernaculars=False):
        results = []
        status = data.get('status')
        status_message = data.get('message')

        for entry in data.get('data', []):
            if 'results' in entry:
                best_match = self.determine_best_match(entry['results'], vernaculars)
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

    def determine_best_match(self, results, vernaculars=False):
        # Filter results to only include complete hierarchies with exact required ranks
        filtered_results = [
            result for result in results
            if self.has_exact_required_ranks(result, self.required_ranks)
        ]

        if not filtered_results:
            return None

        # Find the highest score among the filtered results
        max_score = max(result['score'] for result in filtered_results)
        best_matches = [result for result in filtered_results if result['score'] == max_score]
        best_matches = [self.trim_ranks(match, self.required_ranks) for match in best_matches]
        return self.aggregate_tied_scores(best_matches, vernaculars)
        
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
    
    def has_exact_required_ranks(self, result, required_ranks):
        path = result.get('classification_path', '')
        path_ranks = result.get('classification_path_ranks', '')

        if path and path_ranks:
            path = path.split('|')
            path_ranks = path_ranks.split('|')
            canonical_form = result.get('canonical_form', '')

            if canonical_form in path:
                index = path.index(canonical_form)
                input_rank = path_ranks[index].strip().lower()

                if input_rank in required_ranks:
                    observed_ranks = {rank.strip().lower() for rank in path_ranks[:index + 1]}
                    required_up_to_input = [rank for rank in required_ranks if required_ranks.index(rank) <= required_ranks.index(input_rank)]

                    return set(required_up_to_input) <= observed_ranks

        return False

    def resolve_names(self, names, vernaculars=False):
        # TODO: optimize batch size
        batch_size = 300
        batches = [names[i:i + batch_size] for i in range(0, len(names), batch_size)]
        all_results = []

        for batch in tqdm(batches, desc='Processing batches'):
            batch_results = self.process_batch(batch, vernaculars=vernaculars)
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
            'prescore': [result.get('prescore') for result in results],
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

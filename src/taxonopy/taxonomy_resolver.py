import json
from tqdm import tqdm
from taxonopy.error_handler import log_error
from taxonopy.api_service import APIService

class TaxonomyResolver:
    def __init__(self):
        self.api_service = APIService()

    def process_batch(self, names):
        try:
            response = self.api_service.query_gnr(names)
            return self.process_data(response)
        except Exception as e:
            log_error(f'Error processing batch: {str(e)}')
            return []

    def process_data(self, data):
        results = []
        status = data.get('status')
        status_message = data.get('message')
        for entry in data.get('data', []):
            if 'results' in entry:
                best_match = self.determine_best_match(entry['results'])
                if best_match:
                    # Include additional fields from the entry and data levels
                    best_match.update({
                        'supplied_name_string': entry.get('supplied_name_string'),
                        'is_known_name': entry.get('is_known_name'),
                        'status': status,
                        'status_message': status_message
                    })
                    results.append(best_match)
        return results

    def determine_best_match(self, results):
        # Filter results to only include complete hierarchies with exact required ranks
        required_ranks = {'kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species'}
        filtered_results = [
            result for result in results
            if self.has_exact_required_ranks(result, required_ranks)
        ]

        if not filtered_results:
            return None

        # Find the highest score among the filtered results
        max_score = max(result['score'] for result in filtered_results)
        best_matches = [result for result in filtered_results if result['score'] == max_score]

        if len(best_matches) > 1:
            # Include all results when multiple sources have the same score
            return self.aggregate_tied_scores(best_matches)
        else:
            return best_matches[0]

    def has_exact_required_ranks(self, result, required_ranks):
        ranks = set(result.get('classification_path_ranks', '').lower().split('|'))
        return ranks == required_ranks

    def resolve_names(self, names):
        # TODO: optimize batching
        batches = [names[i:i + 300] for i in range(0, len(names), 300)]
        all_results = []
        for batch in tqdm(batches, desc='Processing batches'):
            batch_results = self.process_batch(batch)
            all_results.extend(batch_results)
            self.save_results(batch_results)
        return all_results
    
    def aggregate_tied_scores(self, results):
        aggregated_info = {
            'supplied_name_string': results[0].get('supplied_name_string'),
            'is_known_name': results[0].get('is_known_name'),
            'data_source_id': [result['data_source_id'] for result in results],
            'gni_uuid': [result.get('gni_uuid') for result in results],
            'name_string': [result.get('name_string') for result in results],
            'canonical_form': [result.get('canonical_form') for result in results],
            'classification_path': [result.get('classification_path') for result in results], # TODO: address cases of discrepant paths among sources
            'classification_path_ids': [result.get('classification_path_ids') for result in results],
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
        return aggregated_info


    # TODO: decide on a better way to save results
    def save_results(self, data):
        with open('resolved_taxonomies.jsonl', 'a') as f:
            for entry in data:
                json.dump(entry, f)
                f.write('\n')

"""Query execution for TaxonoPy.

This module provides functions for executing taxonomic queries against
the GNVerifier service, processing the results, and preparing data for
ResolutionAttempt objects.
"""

import logging
from typing import List, Dict, Optional, Tuple, Iterator
from datetime import datetime
import itertools

from tqdm import tqdm
from pydantic import ValidationError

from taxonopy.types.data_classes import QueryParameters
from taxonopy.types.gnverifier import Name as GNVerifierName
from taxonopy.query.gnverifier_client import GNVerifierClient
from taxonopy.config import config

logger = logging.getLogger(__name__)

def execute_queries(
    queries_to_run: Dict[str, QueryParameters],
    client: GNVerifierClient,
    batch_size: Optional[int] = None
) -> Dict[str, Tuple[QueryParameters, Optional[GNVerifierName]]]:
    """
    Executes GNVerifier queries for the given parameters in batches.

    Args:
        queries_to_run: Dictionary mapping EntryGroupRef keys to QueryParameters.
        client: An initialized GNVerifierClient instance.
        batch_size: The maximum number of queries to send to the client in one batch.
                    Defaults to config.batch_size if None.

    Returns:
        Dictionary mapping EntryGroupRef keys back to a tuple containing the
        original QueryParameters used and the parsed GNVerifierName result (or None).

    Raises:
        RuntimeError: If critical integrity checks fail (count mismatch, name mismatch)
                      or if the client raises an error during execution.
    """
    if not queries_to_run:
        logger.info("No queries provided to execute.")
        return {}

    if batch_size is None:
        batch_size = config.batch_size
    logger.info(f"Executing {len(queries_to_run)} queries in batches of size {batch_size}...")

    all_results: Dict[str, Tuple[QueryParameters, Optional[GNVerifierName]]] = {}
    
    # Prepare items for batching
    items_to_process = list(queries_to_run.items())
    total_queries = len(items_to_process)

    with tqdm(total=total_queries, desc="Executing queries", unit="query") as pbar:
        for i in range(0, total_queries, batch_size):
            batch_items = items_to_process[i:i+batch_size]
            
            # Prepare input for this specific batch
            batch_eg_keys = [item[0] for item in batch_items]
            batch_params = [item[1] for item in batch_items]
            batch_query_terms = [param.term for param in batch_params]
            # Get unique source ID for this batch (assuming all use same source in batch)
            source_id = batch_params[0].source_id if batch_params else None
            # Convert to string for the client
            source_id_str = str(source_id) if source_id is not None else None
            
            batch_start_index = i
            batch_end_index = min(i + batch_size, total_queries)
            logger.debug(f"Processing batch {batch_start_index+1}-{batch_end_index}...")

            try:
                # Call the client with the list of terms for this batch
                gnverifier_results_dicts: List[Dict] = client.execute_query(
                    batch_query_terms, 
                    source_id_override=source_id_str
                )

                # Integrity check 1: Count
                if len(gnverifier_results_dicts) != len(batch_query_terms):
                    error_msg = (
                        f"Fatal Error: GNVerifier returned {len(gnverifier_results_dicts)} results for batch, "
                        f"but {len(batch_query_terms)} queries were sent. Halting execution."
                    )
                    logger.critical(error_msg)
                    raise RuntimeError(error_msg)

                # Process results for this batch
                for j, result_dict in enumerate(gnverifier_results_dicts):
                    original_eg_key = batch_eg_keys[j]
                    original_params = batch_params[j]
                    sent_term = batch_query_terms[j]
                    parsed_response: Optional[GNVerifierName] = None
                    parsing_error: Optional[str] = None

                    # Integrity check 2: Name
                    # Ensure the result dict corresponds to the sent term
                    # Allow empty dicts (client might return {} on error)
                    if result_dict and result_dict.get("name") != sent_term:
                         error_msg = (
                            f"Fatal Error: Result name mismatch in batch. "
                            f"Sent term '{sent_term}' (index {j}), but received result "
                            f"with name '{result_dict.get('name', 'N/A')}'. Halting execution."
                         )
                         logger.critical(error_msg)
                         raise RuntimeError(error_msg)

                    # Parse result
                    if result_dict: # Only parse if the dict isn't empty/None
                        try:
                            parsed_response = GNVerifierName.model_validate(result_dict)
                        except ValidationError as val_err:
                            parsing_error = f"Pydantic validation failed: {val_err}"
                            logger.error(f"Query Term: '{sent_term}' (EG Key: {original_eg_key}) - {parsing_error}")
                        except Exception as parse_err: # Catch other potential errors
                            parsing_error = f"Unexpected error parsing response: {parse_err}"
                            logger.error(f"Query Term: '{sent_term}' (EG Key: {original_eg_key}) - {parsing_error}", exc_info=True)

                    # Store result mapped back to original EntryGroupRef key
                    if parsing_error:
                         # Store None for the response object if parsing failed
                         all_results[original_eg_key] = (original_params, None)
                         # TODO: store the error somewhere.For now, just log.
                    else:
                         all_results[original_eg_key] = (original_params, parsed_response)

                pbar.update(len(batch_items))

            except RuntimeError: # Catch fatal integrity errors or client execution errors
                 raise # Re-raise to halt the process as per design
            except Exception as e:
                logger.error(f"Unexpected error processing batch {batch_start_index+1}-{batch_end_index}: {e}", exc_info=True)
                # Handle non-fatal batch error: record None for all items in this batch
                for k in range(len(batch_items)):
                    original_eg_key = batch_eg_keys[k]
                    original_params = batch_params[k]
                    if original_eg_key not in all_results: # Avoid overwriting successful results from previous batches if error occurs later
                        all_results[original_eg_key] = (original_params, None)
                pbar.update(len(batch_items)) # Ensure progress bar updates even on batch error
                # Decide whether to continue to next batch or halt? For now, let's halt.
                raise RuntimeError(f"Batch processing error: {e}")


    logger.info(f"Finished executing queries. Obtained results for {len(all_results)} EntryGroupRefs.")
    if len(all_results) != total_queries:
         logger.warning(f"Number of results ({len(all_results)}) does not match total queries ({total_queries}). Some queries may have failed.")

    return all_results

from typing import Dict, List, Optional, Set, Tuple, Union
import logging
from datetime import datetime
import json

from taxonopy.types.data_classes import (
    EntryGroupRef,
    QueryParameters,
    ResolutionStatus,
    ResolutionAttempt,
)

from taxonopy.resolution.strategy.profiles import (
    empty_input_taxonomy,
    # Exact matches
    exact_match_primary_source_accepted,
    exact_match_primary_source_accepted_retry,
    exact_match_primary_source_accepted_inner_rank_disambiguation,
    exact_match_primary_source_accepted_rank_level_disambiguation,
    exact_match_primary_source_accepted_synonym_disambiguation,
    exact_match_primary_source_accepted_multi_result_disambiguation,
    # Fuzzy matches
    fuzzy_match_primary_source_accepted,
    # Partial matches
    partial_exact_match_primary_source_accepted_multi_result_disambiguation,
    # Synonym matches
    exact_match_primary_source_synonym,
    # Retry cases
    no_match_nonempty_query,
    exact_match_primary_source_accepted_inner_rank_missing_in_result,
    exact_match_secondary_source_accepted_pruned,
    exact_match_primary_source_accepted_result_within_query,
    # adding profiles as they are implemented
)
from taxonopy.types.gnverifier import Name as GNVerifierName
from taxonopy.query.planner import plan_initial_queries, plan_retry_query
from taxonopy.query.executor import execute_queries
from taxonopy.query.gnverifier_client import GNVerifierClient

import hashlib

from tqdm import tqdm

# Each function with signature:
# (attempt: ResolutionAttempt, entry_group: EntryGroupRef, manager: "ResolutionAttemptManager") -> Optional[ResolutionAttempt]
# The function should return the newly created final/retry attempt if the profile matches, otherwise None.
CLASSIFICATION_CASES = [
    empty_input_taxonomy.check_and_resolve,
    # Exact matches
    exact_match_primary_source_accepted.check_and_resolve,
    exact_match_primary_source_accepted_retry.check_and_resolve,
    exact_match_primary_source_accepted_inner_rank_disambiguation.check_and_resolve,
    exact_match_primary_source_accepted_rank_level_disambiguation.check_and_resolve,
    exact_match_primary_source_accepted_synonym_disambiguation.check_and_resolve,
    exact_match_primary_source_accepted_multi_result_disambiguation.check_and_resolve,
    # Fuzzy matches
    fuzzy_match_primary_source_accepted.check_and_resolve,
    # Partial matches
    partial_exact_match_primary_source_accepted_multi_result_disambiguation.check_and_resolve,
    # Synonym matches
    exact_match_primary_source_synonym.check_and_resolve,
    # Retry cases
    no_match_nonempty_query.check_and_resolve,
    exact_match_primary_source_accepted_inner_rank_missing_in_result.check_and_resolve,
    exact_match_secondary_source_accepted_pruned.check_and_resolve,
    exact_match_primary_source_accepted_result_within_query.check_and_resolve,
    # add more cases
]

class ResolutionAttemptManager:
    """
    Manages the resolution lifecycle for EntryGroupRefs, including creating attempts,
    orchestrating queries, applying classification strategies, and handling retries.
    """

    def __init__(self):
        """Initialize a new resolution manager."""
        self._attempts: Dict[str, ResolutionAttempt] = {} # Stores all attempts by attempt.key
        self._entry_group_latest_attempt: Dict[str, str] = {} # Maps entry_group.key -> latest attempt.key
        self.logger = logging.getLogger(__name__)

    @property
    def attempts(self) -> Dict[str, ResolutionAttempt]:
        """Get a dictionary of all resolution attempts."""
        return dict(self._attempts) # Return a copy

    def create_attempt(
        self,
        entry_group_key: str,
        query_term: str,
        query_rank: Optional[str],
        data_source_id: Optional[int],
        status: ResolutionStatus,
        gnverifier_response: Optional[GNVerifierName] = None,
        resolved_classification: Optional[Dict[str, str]] = None,
        error: Optional[str] = None,
        resolution_strategy_name: Optional[str] = None,
        failure_reason: Optional[str] = None,
        scheduled_query_params: Optional[QueryParameters] = None,
        metadata: Optional[Dict[str, Union[str, int, float, bool]]] = None,
    ) -> ResolutionAttempt:
        """
        Creates/updates a resolution attempt. If an attempt with the same identifying key
        (entry_group_key, query params, response) exists, it updates the existing entry
        if the status is different; otherwise, it creates a new entry.
        Handles linking via previous_key and updates the latest attempt pointer.
        """
        if metadata is None:
            metadata = {}

        # Determine previous_key before potentially overwriting the latest pointer target
        previous_key_leading_to_this = self._entry_group_latest_attempt.get(entry_group_key)

        # Calculate the key based on identifying information
        # Use a consistent way to represent the response for hashing
        response_str = ""
        if gnverifier_response is not None:
            try:
                # Ensure deterministic serialization
                # response_str = gnverifier_response.model_dump_json(sort_keys=True)
                response_dict = gnverifier_response.model_dump(mode='json')
                response_str = json.dumps(response_dict, sort_keys=True)
            except Exception as e:
                 self.logger.warning(f"Could not serialize gnverifier_response for key generation: {e}")
                 response_str = "" # Fallback

        key_components = [
            entry_group_key or "", query_term or "", query_rank or "",
            str(data_source_id) if data_source_id is not None else "",
            response_str
        ]
        combined = "|".join(key_components)
        attempt_key = hashlib.sha256(combined.encode("utf-8")).hexdigest()

        existing_attempt = self._attempts.get(attempt_key)

        if existing_attempt:
            # Collision detected
            self.logger.debug(f"Attempt key {attempt_key} collision detected. Existing status: {existing_attempt.status.name}, New status: {status.name}")

            # If status is identical, just update latest pointer and return existing
            if existing_attempt.status == status:
                self.logger.debug(f"Collision with identical status ({status.name}). Re-using existing attempt {attempt_key}.")
                self._entry_group_latest_attempt[entry_group_key] = attempt_key # Ensure latest pointer is correct
                return existing_attempt
            else:
                # Status is changing: replacethe object
                self.logger.info(f"Collision with different status. Replacing attempt {attempt_key} object with status {status.name}.")

                previous_key_for_new_obj = existing_attempt.previous_key
                # Create the new attempt object WITH the correct previous_key
                # This previous_key links back to the attempt before the one being replaced/updated.
                new_attempt_obj = ResolutionAttempt(
                     entry_group_key=entry_group_key, query_term=query_term, query_rank=query_rank,
                     data_source_id=data_source_id, status=status,
                     gnverifier_response=gnverifier_response, resolved_classification=resolved_classification,
                     error=error, resolution_strategy_name=resolution_strategy_name,
                     failure_reason=failure_reason,
                     previous_key=previous_key_for_new_obj,
                     scheduled_query_params=scheduled_query_params, metadata=metadata
                )
                # Check key consistency (optional sanity check)
                if new_attempt_obj.key != attempt_key:
                     self.logger.error(f"Key mismatch during replacement! Original={attempt_key}, NewObj={new_attempt_obj.key}")
                     # TODO: Decide how to handle - maybe raise error?

                # Overwrite the entry in the main dictionary with the new object
                self._attempts[attempt_key] = new_attempt_obj
                # Update the latest pointer to this key
                self._entry_group_latest_attempt[entry_group_key] = attempt_key
                self.logger.debug(f"Replaced attempt {attempt_key} for entry group {entry_group_key} "
                                   f"with status {status.name}. Previous now points to: {previous_key_for_new_obj}")
                return new_attempt_obj # Return the new object

        else:
            # No Collision: Create and store new attempt
            previous_key_for_new_obj = previous_key_leading_to_this

            new_attempt = ResolutionAttempt(
                entry_group_key=entry_group_key,
                query_term=query_term,
                query_rank=query_rank,
                data_source_id=data_source_id,
                status=status,
                gnverifier_response=gnverifier_response,
                resolved_classification=resolved_classification,
                error=error,
                resolution_strategy_name=resolution_strategy_name,
                failure_reason=failure_reason,
                previous_key=previous_key_for_new_obj,
                scheduled_query_params=scheduled_query_params,
                metadata=metadata
            )
            # Sanity check key
            if new_attempt.key != attempt_key:
                self.logger.error(f"Key mismatch during creation! Calculated={attempt_key}, ObjectProp={new_attempt.key}")

            self._attempts[attempt_key] = new_attempt
            self._entry_group_latest_attempt[entry_group_key] = attempt_key
            self.logger.debug(f"Created attempt {attempt_key} for entry group {entry_group_key} "
                              f"with status {status.name}. Previous: {previous_key_for_new_obj}") # Log the actual previous key assigned
            return new_attempt

    def get_attempt(self, key: str) -> Optional[ResolutionAttempt]:
        """Get a specific resolution attempt by its key."""
        return self._attempts.get(key)

    def get_latest_attempt(self, entry_group_key: str) -> Optional[ResolutionAttempt]:
        """Get the latest resolution attempt for an entry group."""
        latest_attempt_key = self._entry_group_latest_attempt.get(entry_group_key)
        if latest_attempt_key:
            return self._attempts.get(latest_attempt_key)

        self.logger.debug(f"No attempts found for entry group key: {entry_group_key}")
        return None

    def get_attempt_chain(self, attempt_key: str) -> List[ResolutionAttempt]:
        """Get the full chain of attempts ending with the given attempt key."""
        chain = []
        current_key: Optional[str] = attempt_key

        while current_key is not None:
            attempt = self._attempts.get(current_key)
            if not attempt:
                self.logger.warning(f"Attempt chain broken: Key {current_key} not found.")
                break # Avoid infinite loop if chain is broken

            chain.append(attempt)
            current_key = attempt.previous_key # Follow the chain backwards

        return list(reversed(chain)) # Return in chronological order

    def get_group_attempt_chain(self, entry_group_key: str) -> List[ResolutionAttempt]:
        """Get the full chain of attempts for a specific entry group."""
        latest_attempt_key = self._entry_group_latest_attempt.get(entry_group_key)
        if latest_attempt_key:
            return self.get_attempt_chain(latest_attempt_key)
        return []

    def get_resolution_status(self, entry_group_key: str) -> Optional[ResolutionStatus]:
        """Get the current resolution status for an entry group."""
        attempt = self.get_latest_attempt(entry_group_key)
        return attempt.status if attempt else None

    def get_successful_attempts(self) -> List[ResolutionAttempt]:
        """Get all latest resolution attempts that were successful."""
        successful = []
        for entry_group_key, latest_attempt_key in self._entry_group_latest_attempt.items():
             attempt = self._attempts.get(latest_attempt_key)
             if attempt and attempt.is_successful:
                 successful.append(attempt)
        return successful

    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about the final state of resolution attempts."""
        status_counts = {status: 0 for status in ResolutionStatus}
        total_final_attempts = 0
        retries_made_count = 0 # Count how many chains involved at least one retry

        processed_entry_groups = set()

        for entry_group_key, latest_attempt_key in self._entry_group_latest_attempt.items():
            self.logger.debug(f"Processing entry group {entry_group_key}")
            if entry_group_key in processed_entry_groups: continue # Should not happen with dict keys

            attempt = self._attempts.get(latest_attempt_key)
            if attempt:
                status_counts[attempt.status] = status_counts.get(attempt.status, 0) + 1
                total_final_attempts += 1
                # Check if this chain had retries
                chain = self.get_attempt_chain(latest_attempt_key)
                if any(a.is_retry for a in chain):
                    retries_made_count += 1
            else:
                 self.logger.warning(f"Latest attempt key {latest_attempt_key} for group {entry_group_key} not found in attempts dict.")
            processed_entry_groups.add(entry_group_key)


        return {
            "total_entry_groups_processed": len(self._entry_group_latest_attempt),
            "total_attempts_created": len(self._attempts),
            "entry_groups_with_retries": retries_made_count,
            **{f"final_status_{status.name.lower()}": count for status, count in status_counts.items()}
        }

    def resolve_all_entry_groups(
        self,
        entry_group_map: Dict[str, EntryGroupRef],
        client: GNVerifierClient
    ):
        """
        Orchestrates the entire resolution process for all entry groups.
        Follows the workflow described in PRD Section 2.4.
        """
        self.logger.info("Starting resolution process...")
        if not entry_group_map:
            self.logger.warning("No entry groups provided to resolve.")
            return

        # 1. Initial Query Planning & Execution
        self.logger.info("Planning initial queries...")
        initial_plans: Dict[str, QueryParameters] = plan_initial_queries(entry_group_map)
        if not initial_plans:
             self.logger.warning("Initial query planning yielded no queries.")
             # TODO: Handle cases where all inputs are empty?
             # For now, we might need to manually create EMPTY_INPUT attempts if needed
             # or rely on the classification step to handle attempts created from empty plans.
             # Let's assume plan_initial_queries handles empty inputs appropriately for now.

        self.logger.info(f"Executing {len(initial_plans)} initial queries...")
        try:
            initial_results: Dict[str, Tuple[QueryParameters, Optional[GNVerifierName]]] = execute_queries(initial_plans, client)
        except RuntimeError as e:
             self.logger.critical(f"Fatal error during initial query execution: {e}. Halting.")
             raise # Propagate fatal errors

        self.logger.info("Creating initial resolution attempts...")
        self._create_initial_attempts(initial_results)

        # 2. Resolution Loop
        self.logger.info("Starting resolution loop (classification & retries)...")
        iteration = 0
        max_iterations = 100 # Safety break to prevent infinite loops
        while iteration < max_iterations:
            iteration += 1
            self.logger.info(f"Resolution Loop Iteration: {iteration}")

            # 2a. Classify Pending Attempts
            classified_count = self._classify_pending_attempts(entry_group_map)
            self.logger.info(f"Iteration {iteration}: Classified {classified_count} attempts.")

            # 2b. Collect Retries
            retries_to_schedule: Dict[str, QueryParameters] = self._get_scheduled_retries()
            self.logger.info(f"Iteration {iteration}: Found {len(retries_to_schedule)} attempts scheduled for retry.")

            # 2c. Check Loop Condition
            # Loop continues if there were classifications OR retries scheduled
            # We also need a check for attempts still stuck in PROCESSING
            attempts_still_processing = sum(1 for eg_key, latest_key in self._entry_group_latest_attempt.items()
                                            if self.get_attempt(latest_key).status == ResolutionStatus.PROCESSING)

            if not retries_to_schedule and classified_count == 0 and attempts_still_processing == 0:
                self.logger.info("Resolution loop finished: No more retries scheduled or attempts to classify.")
                break

            if not retries_to_schedule:
                self.logger.info(f"Iteration {iteration}: No retries to execute, continuing classification...")
                # If classification happened but no retries, loop again for potential multi-step classifications
                continue

            # 2d. Execute Retries
            self.logger.info(f"Iteration {iteration}: Executing {len(retries_to_schedule)} retry queries...")
            try:
                 retry_results: Dict[str, Tuple[QueryParameters, Optional[GNVerifierName]]] = execute_queries(retries_to_schedule, client)
            except RuntimeError as e:
                 self.logger.critical(f"Fatal error during retry query execution (Iteration {iteration}): {e}. Halting.")
                 raise # Propagate fatal errors

            # 2e. Apply Retry Results
            self.logger.info(f"Iteration {iteration}: Applying {len(retry_results)} retry results...")
            self._apply_retry_results(retry_results)

        else:
             self.logger.warning(f"Resolution loop reached maximum iterations ({max_iterations}). Exiting.")

        final_stats = self.get_statistics()
        self.logger.info(f"Resolution process complete. Final Stats: {final_stats}")

    def _create_initial_attempts(self, initial_results: Dict[str, Tuple[QueryParameters, Optional[GNVerifierName]]]):
        """Creates the first ResolutionAttempt (status PROCESSING) for each entry group."""
        created_count = 0
        for entry_group_key, (params, response) in initial_results.items():
            # Basic check if the entry group key exists (it should!)
            if entry_group_key not in self._entry_group_latest_attempt:
                self.create_attempt(
                    entry_group_key=entry_group_key,
                    query_term=params.term,
                    query_rank=params.rank,
                    data_source_id=params.source_id,
                    status=ResolutionStatus.PROCESSING, # Initial status
                    gnverifier_response=response,
                    # Other fields default to None/empty
                )
                created_count += 1
            else:
                self.logger.warning(f"Attempt already exists for entry group {entry_group_key} before initial creation? Skipping.")
        self.logger.info(f"Created {created_count} initial attempts.")


    def _classify_pending_attempts(self, entry_group_map: Dict[str, EntryGroupRef]) -> int:
        """
        Iterates through latest attempts in PROCESSING state and applies classification cases.
        Returns the number of attempts that changed state away from PROCESSING.
        """
        self.logger.debug("Starting classification of pending attempts...")
        classified_count = 0
        
        # Get keys of entry groups whose latest attempt is PROCESSING
        # Important: Create a list of keys before iterating, as the dictionary might change during iteration
        keys_to_process = [
            eg_key for eg_key, latest_key in self._entry_group_latest_attempt.items()
            if (attempt := self._attempts.get(latest_key)) and attempt.status == ResolutionStatus.PROCESSING
        ]
        
        total_to_process = len(keys_to_process)
        if total_to_process == 0:
            self.logger.debug("No attempts currently in PROCESSING state.")
            return 0

        self.logger.debug(f"Found {total_to_process} latest attempts in PROCESSING state.")

        with tqdm(total=total_to_process, desc="Classifying attempts", leave=False) as pbar:
            for entry_group_key in keys_to_process:
                pbar.update(1)
                latest_attempt_key = self._entry_group_latest_attempt.get(entry_group_key)
                if not latest_attempt_key:
                    self.logger.warning(f"Latest attempt key missing for group {entry_group_key} during classification.")
                    continue # Should not happen if keys_to_process was built correctly

                current_attempt = self._attempts.get(latest_attempt_key)
                # Double-check status in case it changed mid-loop (e.g., by a previous classification)
                if not current_attempt or current_attempt.status != ResolutionStatus.PROCESSING:
                    continue # Skip if no longer PROCESSING

                entry_group = entry_group_map.get(entry_group_key)
                if not entry_group:
                    self.logger.error(f"Cannot classify attempt {current_attempt.key}: EntryGroup {entry_group_key} not found in map.")
                    # Mark as failed if entry group is missing
                    self.create_attempt(
                         entry_group_key=entry_group_key, query_term=current_attempt.query_term,
                         query_rank=current_attempt.query_rank, data_source_id=current_attempt.data_source_id,
                         status=ResolutionStatus.FAILED, gnverifier_response=current_attempt.gnverifier_response,
                         error="Associated EntryGroupRef not found", failure_reason="Data integrity issue"
                    )
                    classified_count += 1
                    continue

                # Apply cases
                profile_matched = False
                for case_func in CLASSIFICATION_CASES:
                    strategy_name_to_log = getattr(case_func, '__module__', 'unknown_module') # Get module name
                    try:
                        # This call might replace the object in self._attempts via create_attempt
                        newly_created_or_updated_attempt = case_func(current_attempt, entry_group, self)

                        if newly_created_or_updated_attempt is not None:
                            # Use the strategy name from the attempt returned by the case function
                            strategy_name_applied = newly_created_or_updated_attempt.resolution_strategy_name or getattr(case_func, 'STRATEGY_NAME', 'unknown')
                            # Log details about the outcome
                            self.logger.debug(
                                f"Case '{strategy_name_applied}' processed attempt {current_attempt.key}, "
                                f"resulting in attempt {newly_created_or_updated_attempt.key} with status {newly_created_or_updated_attempt.status.name}"
                            )
                            profile_matched = True
                            # Only increment if the original status was PROCESSING
                            if current_attempt.status == ResolutionStatus.PROCESSING:
                                classified_count += 1
                            break # Stop checking cases for this attempt
                    except Exception as e:
                        strategy_name = getattr(case_func, 'STRATEGY_NAME', getattr(case_func, '__name__', 'unknown'))
                        self.logger.error(f"Error in case func '{strategy_name}' for attempt {current_attempt.key}: {e}", exc_info=True)
                        # Create a FAILED attempt if case crashes
                        self.create_attempt(
                             entry_group_key=entry_group_key, query_term=current_attempt.query_term,
                             query_rank=current_attempt.query_rank, data_source_id=current_attempt.data_source_id,
                             status=ResolutionStatus.FAILED, gnverifier_response=current_attempt.gnverifier_response,
                             error=f"Case execution failed: {e}", failure_reason="Case execution failed",
                             resolution_strategy_name=strategy_name
                         )
                        profile_matched = True # Treat crash as a classification
                        classified_count += 1
                        break # Stop checking cases after crash


                # If no case matched after trying all, mark as FAILED (unhandled)
                if not profile_matched:
                    self.logger.warning(f"Attempt {current_attempt.key} (EntryGroup: {entry_group_key}, Term: '{current_attempt.query_term}') "
                                        f"did not match any defined resolution case. Marking as FAILED.")
                    self.create_attempt(
                        entry_group_key=entry_group_key,
                        query_term=current_attempt.query_term,
                        query_rank=current_attempt.query_rank,
                        data_source_id=current_attempt.data_source_id,
                        status=ResolutionStatus.FAILED, # TODO: or maybe a specific UNHANDLED status?
                        gnverifier_response=current_attempt.gnverifier_response,
                        error="No applicable classification case found",
                        failure_reason="Unhandled resolution profile"
                    )
                    classified_count += 1

        self.logger.debug(f"Classification round complete. {classified_count} attempts transitioned from PROCESSING.")
        return classified_count

    def _get_scheduled_retries(self) -> Dict[str, QueryParameters]:
        """Collects all EntryGroupRefs whose latest attempt is RETRY_SCHEDULED."""
        retries: Dict[str, QueryParameters] = {}
        for entry_group_key, latest_attempt_key in self._entry_group_latest_attempt.items():
            attempt = self._attempts.get(latest_attempt_key)
            if attempt and attempt.status == ResolutionStatus.RETRY_SCHEDULED:
                if attempt.scheduled_query_params:
                    retries[entry_group_key] = attempt.scheduled_query_params
                else:
                    self.logger.error(f"Attempt {attempt.key} for group {entry_group_key} has status RETRY_SCHEDULED but no scheduled_query_params!")
        return retries


    def _apply_retry_results(self, retry_results: Dict[str, Tuple[QueryParameters, Optional[GNVerifierName]]]):
        """
        Creates the next ResolutionAttempt (status PROCESSING) for each entry group
        that received a result from the retry query execution.
        """
        applied_count = 0
        for entry_group_key, (params_used, response) in retry_results.items():
            # Find the RETRY_SCHEDULED attempt which should be the current latest
            latest_attempt_key = self._entry_group_latest_attempt.get(entry_group_key)
            if not latest_attempt_key:
                 self.logger.error(f"Cannot apply retry result for group {entry_group_key}: No latest attempt found.")
                 continue
            
            scheduled_attempt = self._attempts.get(latest_attempt_key)
            if not scheduled_attempt or scheduled_attempt.status != ResolutionStatus.RETRY_SCHEDULED:
                 self.logger.error(f"Cannot apply retry result for group {entry_group_key}: Latest attempt {latest_attempt_key} is not RETRY_SCHEDULED (Status: {scheduled_attempt.status.name if scheduled_attempt else 'Not Found'}).")
                 continue

            # Create the new attempt, linking it correctly via previous_key
            # The create_attempt method handles setting the previous_key automatically
            self.create_attempt(
                entry_group_key=entry_group_key,
                query_term=params_used.term, # Use the params actually executed
                query_rank=params_used.rank,
                data_source_id=params_used.source_id,
                status=ResolutionStatus.PROCESSING, # Back to processing for the next classification round
                gnverifier_response=response,
                # scheduled_query_params should be None here, it's set during classification if another retry is needed
            )
            applied_count += 1
        self.logger.info(f"Applied {applied_count} retry results, creating new PROCESSING attempts.")


    # State save/load
    def save_state(self, path: str) -> None:
        """Save the current state to a file."""
        # TODO: Implement serialization (e.g., using pickle or JSON)
        self.logger.warning("save_state is not yet implemented.")
        pass

    @classmethod
    def load_state(cls, path: str) -> "ResolutionAttemptManager":
        """Load state from a file."""
        # TODO: Implement deserialization
        self.logger.warning("load_state is not yet implemented.")
        return cls()

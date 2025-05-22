from datetime import datetime
from typing import Dict, Optional, List, TYPE_CHECKING, Union

from taxonopy.types.data_classes import (
    EntryGroupRef,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import ResultData
from taxonopy.resolution.config import ResolutionStrategyConfig
from taxonopy.constants import TAXONOMIC_RANKS, INVALID_VALUES, KINGDOM_SYNONYMS

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager


class ResolutionStrategy:
    """Base class for resolution strategies."""
    
    def __init__(self, config: Optional[ResolutionStrategyConfig] = None):
        """Initialize the strategy with configuration.
        
        Args:
            config: Optional configuration for the strategy
        """
        self.config = config or ResolutionStrategyConfig()
    
    def can_handle(self, attempt: ResolutionAttempt) -> bool:
        """Determine if this strategy can handle the given resolution attempt.
        
        Args:
            attempt: The resolution attempt to evaluate
            
        Returns:
            True if this strategy can handle the attempt, False otherwise
        """
        raise NotImplementedError("Subclasses must implement can_handle")
    
    def resolve(self, attempt: ResolutionAttempt, 
               attempt_manager: "ResolutionAttemptManager") -> ResolutionAttempt:
        """Apply the resolution strategy and return an updated attempt.
        
        Args:
            attempt: The resolution attempt to resolve
            attempt_manager: The attempt manager for creating new attempts
            
        Returns:
            A new resolution attempt with the resolution result
        """
        raise NotImplementedError("Subclasses must implement resolve")
    
    @staticmethod
    def get_canonical_kingdom(kingdom_name: Optional[str]) -> Optional[str]:
        """
        Returns the canonical kingdom name given a name or its synonym.
        Uses the KINGDOM_SYNONYMS definition from constants.py.
        Handles None, whitespace, and performs case-insensitive matching.
        Returns the canonical name if found, otherwise the original (stripped)
        name if it's valid, or None if input is None/empty/invalid.
        """
        if not kingdom_name:
            return None

        k_stripped = kingdom_name.strip()
        if not k_stripped or k_stripped.lower() in INVALID_VALUES:
            return None

        k_lower = k_stripped.lower()

        # Check if it's already canonical
        for canonical_key in KINGDOM_SYNONYMS:
            if canonical_key.lower() == k_lower:
                return canonical_key # Return the defined canonical spelling

        # Check if it's in the synonyms
        for canonical_key, synonyms_set in KINGDOM_SYNONYMS.items():
            if any(syn.lower() == k_lower for syn in synonyms_set):
                return canonical_key # Return the associated canonical spelling

        # If not found in synonyms or as a key, return the original stripped name
        # (it might be a valid kingdom not explicitly listed, like "Fungi")
        return k_stripped

    def _extract_classification(self, result: ResultData) -> Dict[str, str]:
        """Extract classification information from a result.
        
        This helper method standardizes how classification paths are extracted
        and converted to a structured dictionary format.
        
        Args:
            result: A result from GNVerifier
            
        Returns:
            Dictionary mapping taxonomic ranks to values
        """
        classification = {}
        
        if not result.classification_path or not result.classification_ranks:
            return classification
        
        # Split the paths into lists
        taxa = result.classification_path.split('|')
        ranks = result.classification_ranks.split('|')
        
        # Map ranks to taxa
        # TODO: Handle result cases with repeated ranks ("class" is a common culprit for more phenologically oriented data sources)
        for i, rank in enumerate(ranks):
            if i < len(taxa):
                # Convert 'class' to 'class_' to match TaxonomicEntry fields
                field_name = "class_" if rank == "class" else rank
                if field_name in TAXONOMIC_RANKS:
                    classification[field_name] = taxa[i]
        
        return classification

    def _filter_classification_by_rank(
        self,
        classification: Dict[str, str],
        cutoff_rank: Optional[str]
    ) -> Dict[str, str]:
        """
        Filters a classification dictionary to include only ranks at or above the cutoff_rank.

        Args:
            classification: The full classification dictionary extracted from a result.
            cutoff_rank: The taxonomic rank (e.g., 'family', 'genus') used in the
                         successful query. Ranks at this level and above will be kept.

        Returns:
            A new dictionary containing only the filtered ranks and terms.
        """
        if not cutoff_rank:
            # If no cutoff rank provided (e.g., query was rankless), return the original classification
            return classification

        filtered_classification = {}
        try:
            # Map API rank ('class') back to internal field name ('class_') for indexing
            cutoff_rank_field = 'class_' if cutoff_rank == 'class' else cutoff_rank
            cutoff_index = TAXONOMIC_RANKS.index(cutoff_rank_field)
        except ValueError:
            logger.warning(f"Cutoff rank '{cutoff_rank}' not found in TAXONOMIC_RANKS. Returning full classification.")
            return classification # Return original if rank is invalid

        # Iterate through standard ranks from kingdom up to the cutoff rank (inclusive)
        for i in range(cutoff_index + 1):
            rank_field = TAXONOMIC_RANKS[i]
            if rank_field in classification:
                filtered_classification[rank_field] = classification[rank_field]

        return filtered_classification

    def _get_expected_classification(self, entry_group: EntryGroupRef) -> Dict[str, str]:
        """Extracts the expected classification hierarchy from the EntryGroupRef."""
        expected_classification: Dict[str, str] = {}
        for rank_field in TAXONOMIC_RANKS:
            value = getattr(entry_group, rank_field, None)
            if value:
                term = value.strip()
                # Check if term is valid (non-empty, not in INVALID_VALUES)
                if term and term.lower() not in INVALID_VALUES:
                    expected_classification[rank_field] = term
        return expected_classification

    def _get_parent_rank(self, rank_field: str) -> Optional[str]:
        """Gets the parent rank field name from TAXONOMIC_RANKS."""
        try:
            index = TAXONOMIC_RANKS.index(rank_field)
            if index > 0:
                return TAXONOMIC_RANKS[index - 1]
            return None # Kingdom has no parent in this list
        except ValueError:
            logger.warning(f"Cannot find parent rank for '{rank_field}': Not in TAXONOMIC_RANKS.")
            return None
            
    def _get_rank_of_term(
        self,
        term_to_find: str,
        source: Union[EntryGroupRef, Dict[str, str]]
    ) -> Optional[str]:
        """
        Finds the most specific (lowest) rank associated with a given term
        within an EntryGroupRef or a classification dictionary.

        Args:
            term_to_find: The term to search for (case-sensitive).
            source: Either an EntryGroupRef instance or a classification dict.

        Returns:
            The internal rank field name ('family', 'class_', etc.) or None if not found.
        """
        highest_rank_field = None
        max_index = -1
        term_to_find_stripped = term_to_find.strip() # Ensure consistent comparison

        ranks_to_check = TAXONOMIC_RANKS + ['scientific_name'] # Check standard ranks + scientific_name

        for rank_field in ranks_to_check:
            value = None
            if isinstance(source, EntryGroupRef):
                value = getattr(source, rank_field, None)
            elif isinstance(source, dict):
                value = source.get(rank_field)

            if value and value.strip() == term_to_find_stripped:
                # Found the term at this rank
                try:
                    # Use TAXONOMIC_RANKS for hierarchical comparison index
                    # Map scientific_name/class_ to standard rank names if needed for index lookup,
                    # but return the actual field name.
                    compare_rank = rank_field
                    if rank_field == 'scientific_name': continue # Don't use scientific_name for hierarchy index
                    if rank_field == 'class_': compare_rank = 'class' # Use 'class' for index lookup

                    # Need the index from TAXONOMIC_RANKS to determine 'highest'/'most specific'
                    index = -1
                    try:
                        index = TAXONOMIC_RANKS.index(rank_field)
                    except ValueError:
                         # Handle ranks not in TAXONOMIC_RANKS (like scientific_name)
                         # If only scientific_name matches, it's the 'highest' for this purpose
                         if highest_rank_field is None:
                              highest_rank_field = rank_field # Tentatively assign
                         continue # Skip index comparison for non-standard ranks


                    if index > max_index:
                        max_index = index
                        highest_rank_field = rank_field # Store the actual field name ('class_')
                except ValueError:
                     # Should not happen if rank_field is from TAXONOMIC_RANKS
                     logger.warning(f"Rank field '{rank_field}' unexpectedly not found in TAXONOMIC_RANKS during _get_rank_of_term.")
                     continue

        return highest_rank_field

    def _get_highest_rank_in_classification(self, classification: Dict[str, str]) -> Optional[str]:
        """Finds the most specific (lowest) rank present in a classification dict."""
        highest_rank_field = None
        max_index = -1
        for rank_field in classification.keys():
             try:
                  # Use TAXONOMIC_RANKS to determine hierarchy
                  index = TAXONOMIC_RANKS.index(rank_field)
                  if index > max_index:
                       max_index = index
                       highest_rank_field = rank_field
             except ValueError:
                  continue # Ignore ranks not in the sttdanard list
        return highest_rank_field

    def _get_highest_rank_in_entry_group(self, entry_group: EntryGroupRef) -> Optional[str]:
        """Finds the most specific (lowest) rank field name with valid data in an EntryGroupRef."""
        # Iterate ranks from most specific to least specific
        ranks_to_check = list(reversed(TAXONOMIC_RANKS)) # species -> kingdom
        for rank_field in ranks_to_check:
             value = getattr(entry_group, rank_field, None)
             if value:
                term = value.strip()
                if term and term.lower() not in INVALID_VALUES:
                      # Found the highest standard rank with valid data
                      return rank_field
        # If no standard rank had data, check scientific_name as a fallback non-hierarchical identifier
        value = getattr(entry_group, 'scientific_name', None)
        if value:
             term = value.strip()
             if term and term.lower() not in INVALID_VALUES:
                return 'scientific_name' # Return special indicator if only scientific_name is valid

        return None # No valid rank found
    
    def _get_retry_count(self, attempt: ResolutionAttempt, 
                        attempt_manager: "ResolutionAttemptManager") -> int:
        """Count how many retry attempts preceded this one in the chain.
        
        Args:
            attempt: The current resolution attempt
            attempt_manager: The attempt manager for accessing previous attempts
            
        Returns:
            The number of retry attempts already made
        """

        # TODO: This currently counts attempts linked by previous_key, assuming they were retries.
        # Might need to adjust based on how retries vs. other steps are defined ...
        count = 0

        current_key = attempt.key
        
        while current_key:
            current = attempt_manager.get_attempt(current_key)
            if not current:
                 # This might happen if the chain is broken or key is wrong
                 break

            # Check if it's a retry based on its previous_key
            if current.is_retry: # Assumes is_retry checks previous_key is not None
                 count += 1

            # Move to the previous attempt in the chain
            current_key = current.previous_key # Traverse using previous_key

        # The count should naturally reflect retries, no subtraction needed if logic is correct
        return count

    def _compare_paths_up_to_rank(self, expected_path: Dict[str, str], result_path: Dict[str, str], max_rank_field: Optional[str]) -> bool:
        """Checks if the result_path matches the expected_path up to the specified max_rank field name."""
        if not expected_path or max_rank_field is None or max_rank_field == 'scientific_name':
             # If no input path, no rank to compare up to, or comparing up to scientific_name (not hierarchical) -> cannot confirm path consistency
             return False # Or maybe True if no comparison needed? Let's default to False for safety.
        try:
            max_rank_index = TAXONOMIC_RANKS.index(max_rank_field)
        except ValueError:
             logger.warning(f"Rank field '{max_rank_field}' not found in TAXONOMIC_RANKS during path comparison for fuzzy match.")
             return False

        for i in range(max_rank_index + 1): # Compare up to and including the max_rank_field
            current_rank_field = TAXONOMIC_RANKS[i]
            expected_term = expected_path.get(current_rank_field)
            result_term = result_path.get(current_rank_field)
            # Only compare if the input had a value for this rank
            if expected_term is not None and expected_term != result_term:
                return False # Mismatch found where input provided data
        return True

    def _compare_paths(self, expected_path: Dict[str, str], result_path: Dict[str, str]) -> bool:
        """
        Checks if the result_path contains all rank/term pairs from the expected_path.
        Returns True if all expected ranks/terms are present and match in the result path, False otherwise.
        """
        if not expected_path: # If input has no taxonomy, it can't match specifically
             return False
        for rank, term in expected_path.items():
            if result_path.get(rank) != term:
                return False # Mismatch found
        return True # All expected pairs were found and matched

    def _create_failed_attempt(self, 
                               attempt: ResolutionAttempt,
                               attempt_manager: "ResolutionAttemptManager",
                               reason: str = "Strategy could not resolve",
                               error_msg: Optional[str] = None
                               ) -> ResolutionAttempt:
        """
        Create a failed resolution attempt using the manager.
        Called by strategies when their specific logic fails.
        """
        final_error_string = error_msg or f"Strategy '{self.__class__.__name__}' failed: {reason}"

        # Combine metadata correctly
        previous_metadata = attempt.metadata or {}
        profile_specific_metadata = {} # Failure reason is already a specific field
        # if profiles_checked_log:
        #     profile_specific_metadata['profiles_checked'] = profiles_checked_log

        final_metadata = previous_metadata.copy()
        final_metadata.update(profile_specific_metadata)

        # Use the attempt_manager's create_attempt method with the new signature
        return attempt_manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.FAILED,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=None,
            error=final_error_string,
            resolution_strategy_name=self.__class__.__name__,
            failure_reason=reason,
            metadata=final_metadata 
        )

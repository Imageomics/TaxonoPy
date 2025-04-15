import logging
from typing import Optional, TYPE_CHECKING, Dict
from difflib import SequenceMatcher

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.types.data_classes import (
    EntryGroupRef,
    QueryParameters,
    ResolutionAttempt,
    ResolutionStatus
)
from taxonopy.types.gnverifier import MatchType
from taxonopy.constants import DATA_SOURCE_PRECEDENCE

from .profile_logging import setup_profile_logging
# Set to True to enable debug logging for this profile
_PROFILE_DEBUG_OVERRIDE_ = True
logger = logging.getLogger(__name__)
setup_profile_logging(logger, _PROFILE_DEBUG_OVERRIDE_)

if TYPE_CHECKING:
    from taxonopy.resolution.attempt_manager import ResolutionAttemptManager

STRATEGY_NAME = "SubfamilyToFamilyFallback"

class SubfamilyToFamilyFallbackStrategy(ResolutionStrategy):
    """
    Handles cases where a query with a scientific_name that appears to be 
    a subfamily name (ending in 'inae') results in NoMatch, but the family field
    is populated with a valid term that shares a common prefix.
    
    Example: scientific_name="Diapriinae", family="Diapriidae" -> retry with family term
    """

    def check_and_resolve(
        self,
        attempt: ResolutionAttempt,
        entry_group: EntryGroupRef,
        manager: "ResolutionAttemptManager"
    ) -> Optional[ResolutionAttempt]:
        """
        Checks for scientific_name that looks like a subfamily, and failed with NoMatch,
        when a valid family term exists in the EntryGroupRef.
        """
        # Profile condition checks
        
        # 1. Is the query for a scientific_name?
        if attempt.query_rank != "scientific_name":
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Not a scientific_name query (rank: {attempt.query_rank}).")
            return None

        # 2. Did we get a NoMatch?
        no_match = False
        if not attempt.gnverifier_response:
            # No response = execution error = treat as no match
            no_match = True
        elif (attempt.gnverifier_response.match_type and 
              isinstance(attempt.gnverifier_response.match_type, MatchType) and 
              attempt.gnverifier_response.match_type.root == "NoMatch"):
            # Explicit "NoMatch" type
            no_match = True
        elif not attempt.gnverifier_response.results:
            # Response exists but no results = implicit no match
            no_match = True
            
        if not no_match:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Not a NoMatch result.")
            return None

        # 3. Does the scientific_name look like a subfamily name (ending with 'inae')?
        query_term = attempt.query_term or ""
        if not query_term.lower().endswith('inae'):
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Query term '{query_term}' doesn't end with 'inae'.")
            return None

        # 4. Is there a valid family term?
        family_term = entry_group.family
        if not family_term or family_term.strip() == "":
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: No family term available.")
            return None

        # 5. Do the subfamily and family share a common prefix?
        # Compute similarity ratio
        family_term = family_term.strip()
        similarity_ratio = SequenceMatcher(None, query_term.lower(), family_term.lower()).ratio()
        
        # Check if the first few characters match (common prefix)
        prefix_length = min(5, min(len(query_term), len(family_term)))
        common_prefix = query_term.lower()[:prefix_length] == family_term.lower()[:prefix_length]
        
        if not common_prefix or similarity_ratio < 0.5:
            logger.debug(f"Profile {STRATEGY_NAME} mismatch on attempt {attempt.key}: Subfamily '{query_term}' and family '{family_term}' don't share a sufficient common prefix (similarity: {similarity_ratio:.2f}).")
            return None

        # Profile matched
        logger.debug(f"Attempt {attempt.key} matched profile for {STRATEGY_NAME}. Will retry with family term '{family_term}'.")

        # Get the primary data source ID (could be taken from configuration)
        try:
            primary_source_id = next(iter(DATA_SOURCE_PRECEDENCE.values()))
        except (IndexError, StopIteration):
            logger.error(f"Cannot determine primary source for {STRATEGY_NAME}: DATA_SOURCE_PRECEDENCE is empty.")
            return self._create_failed_attempt(attempt, manager, reason="Config Error", error_msg="Cannot determine primary source ID")

        # Schedule a retry directly with the family term and primary data source
        next_query_params = QueryParameters(
            term=family_term,
            rank="family",
            source_id=primary_source_id
        )
        
        # Create a RETRY_SCHEDULED attempt
        retry_scheduled_attempt = manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            data_source_id=attempt.data_source_id,
            status=ResolutionStatus.RETRY_SCHEDULED,
            gnverifier_response=attempt.gnverifier_response,
            resolution_strategy_name=STRATEGY_NAME,
            scheduled_query_params=next_query_params,
            metadata={
                'reason_for_retry': "Scientific name appears to be subfamily, trying family term instead",
                'subfamily_term': query_term,
                'family_term': family_term,
                'similarity_ratio': f"{similarity_ratio:.2f}"
            }
        )
        
        logger.debug(f"Applied {STRATEGY_NAME}: Created RETRY_SCHEDULED attempt {retry_scheduled_attempt.key} for original {attempt.key}. Next query: {next_query_params}")
        return retry_scheduled_attempt

# Expose for registration
strategy_instance = SubfamilyToFamilyFallbackStrategy()
check_and_resolve = strategy_instance.check_and_resolve

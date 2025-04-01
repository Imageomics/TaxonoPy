"""Strategy for handling exact matches in taxonomic resolution.

This module provides a strategy for resolving taxonomic names that have
an exact match in the GNVerifier response.
"""

from datetime import datetime
from typing import List, Optional

from taxonopy.types.data_classes import ResolutionAttempt, ResolutionStatus
from taxonopy.types.gnverifier import ResultData
from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
from taxonopy.resolution.strategy.base import ResolutionStrategy


class ExactMatchStrategy(ResolutionStrategy):
    """Strategy for handling exact matches.
    
    This strategy handles resolution attempts that have an exact match
    in the GNVerifier response, extracting the classification information
    and creating a resolved attempt.
    """
    
    def can_handle(self, attempt: ResolutionAttempt) -> bool:
        """Check if the attempt contains an exact match.
        
        Args:
            attempt: The resolution attempt to evaluate
            
        Returns:
            True if this strategy can handle the attempt, False otherwise
        """
        if not attempt.gnverifier_response:
            return False
        
        match_type = attempt.gnverifier_response.match_type.root
        return match_type == "Exact" and self._has_valid_results(attempt)
    
    def _has_valid_results(self, attempt: ResolutionAttempt) -> bool:
        """Check if the attempt has valid results.
        
        Args:
            attempt: The resolution attempt to evaluate
            
        Returns:
            True if the attempt has valid results, False otherwise
        """
        if not attempt.gnverifier_response:
            return False
        
        return (attempt.gnverifier_response.results is not None and 
                len(attempt.gnverifier_response.results) > 0)
    
    def resolve(self, attempt: ResolutionAttempt, 
               attempt_manager: ResolutionAttemptManager) -> ResolutionAttempt:
        """Extract classification from the exact match.
        
        Args:
            attempt: The resolution attempt to resolve
            attempt_manager: The attempt manager for creating new attempts
            
        Returns:
            A new resolution attempt with the resolution result
        """
        # Get the best result from the GNVerifier response
        best_result = self._select_best_result(attempt.gnverifier_response.results)
        if not best_result:
            return self._create_failed_attempt(
                attempt, attempt_manager, "No valid results found")
        
        # Extract classification information from the result
        classification = self._extract_classification(best_result)
        
        # Prepare detailed metadata about the resolution
        metadata = {
            "resolution_strategy": "ExactMatch",
            "confidence": "high",
            "decision_factors": [
                {"criteria": "match_type", "value": "Exact"},
                {"criteria": "taxonomic_status", "value": best_result.taxonomic_status},
                {"criteria": "source_quality", "value": best_result.curation},
                {"criteria": "score", "value": best_result.sort_score}
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        # Add information about alternative results if there were any
        if len(attempt.gnverifier_response.results) > 1:
            metadata["alternatives"] = [
                {
                    "name": alt.matched_name,
                    "score": alt.sort_score,
                    "source": alt.data_source_title_short
                }
                for alt in attempt.gnverifier_response.results 
                if alt != best_result
            ]
        
        # Add previous_attempt_id to the metadata
        metadata["previous_attempt_id"] = attempt.attempt_id
        
        # Create a new attempt with the resolved classification
        return attempt_manager.create_attempt(
            query_group_key=attempt.query_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            status=ResolutionStatus.EXACT_MATCH,
            gnverifier_response=attempt.gnverifier_response,
            resolved_classification=classification,
            metadata=metadata
        )
    
    def _select_best_result(self, results: List[ResultData]) -> Optional[ResultData]:
        """Select the best result based on multiple criteria.
        
        This method implements a decision tree for selecting the best result
        from a list of potential matches, prioritizing accepted names and
        high-quality data sources.
        
        Args:
            results: List of results to select from
            
        Returns:
            The best result, or None if no valid results
        """
        if not results:
            return None
        
        # First filter for accepted names
        accepted_results = [r for r in results 
                          if r.taxonomic_status == "Accepted" and not r.is_synonym]
        
        if not accepted_results:
            # Fall back to all results if no accepted names
            accepted_results = results
        
        # If multiple results remain, prioritize by data source quality
        if len(accepted_results) > 1:
            for curation_level in ["Curated", "AutoCurated", "NotCurated"]:
                curated_results = [r for r in accepted_results 
                                 if r.curation == curation_level]
                if curated_results:
                    return max(curated_results, key=lambda r: r.sort_score)
        
        # Return the highest scoring result
        return max(accepted_results, key=lambda r: r.sort_score)
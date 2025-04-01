"""Strategy for handling singular exact matches in taxonomic resolution.

This module provides a strategy for resolving taxonomic names that have
a single exact match in the GNVerifier response.
"""

from datetime import datetime
from typing import List, Optional, Dict

from taxonopy.types.data_classes import ResolutionAttempt, ResolutionStatus
from taxonopy.types.gnverifier import ResultData
from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.constants import TAXONOMIC_RANKS


class SingularExactMatchStrategy(ResolutionStrategy):
    """Strategy for handling singular exact matches.
    
    This strategy handles resolution attempts that have exactly one
    result with an exact match in the GNVerifier response, extracting 
    the classification information and creating a resolved attempt.
    """
    
    def can_handle(self, attempt: ResolutionAttempt) -> bool:
        """Check if the attempt contains a single exact match.
        
        Args:
            attempt: The resolution attempt to evaluate
            
        Returns:
            True if this strategy can handle the attempt, False otherwise
        """
        if not attempt.gnverifier_response:
            return False
        
        # Check for exact match type
        match_type = attempt.gnverifier_response.match_type.root
        if match_type != "Exact":
            return False
        
        # Check for a single valid result
        if (not attempt.gnverifier_response.results or 
            len(attempt.gnverifier_response.results) != 1):
            return False
        
        # Make sure the result has classification data
        result = attempt.gnverifier_response.results[0]
        return (result.classification_path is not None and 
                result.classification_ranks is not None)
    
    def resolve(self, attempt: ResolutionAttempt, 
               attempt_manager: ResolutionAttemptManager) -> ResolutionAttempt:
        """Extract classification from the exact match.
        
        Args:
            attempt: The resolution attempt to resolve
            attempt_manager: The attempt manager for creating new attempts
            
        Returns:
            A new resolution attempt with the resolution result
        """
        # There's only one result
        result = attempt.gnverifier_response.results[0]
        
        # Extract classification information from the result
        classification = self._extract_classification(result)
        
        # Prepare detailed metadata about the resolution
        metadata = {
            "resolution_strategy": "SingularExactMatch",
            "confidence": "high",
            "curation": result.curation,
            "match_type": "Exact",
            "data_source": result.data_source_title_short,
            "current_name": result.current_name,
            "timestamp": datetime.now().isoformat(),
            "previous_attempt_id": attempt.attempt_id  # Store as metadata instead
        }
        
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
    
    def _extract_classification(self, result: ResultData) -> Dict[str, str]:
        """Extract classification information from a result.
        
        This method overrides the base implementation to ensure we only
        extract the standard taxonomic ranks defined in constants.TAXONOMIC_RANKS.
        
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
        
        # Create a mapping of rank to taxon
        rank_to_taxon = {}
        for i, rank in enumerate(ranks):
            if i < len(taxa):
                rank_to_taxon[rank] = taxa[i]
        
        # Extract only the standard taxonomic ranks
        for rank in TAXONOMIC_RANKS:
            # Convert 'class_' to 'class' to match GNVerifier ranks
            gnv_rank = 'class' if rank == 'class_' else rank
            
            # Check if the rank exists in the GNVerifier response
            if gnv_rank in rank_to_taxon:
                classification[rank] = rank_to_taxon[gnv_rank]
        
        return classification

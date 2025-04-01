"""Base class for taxonomic resolution strategies.

This module provides the abstract base class that all resolution strategies
must implement, defining the common interface and helper methods.
"""

from datetime import datetime
from typing import Dict, Optional, List

from taxonopy.types.data_classes import ResolutionAttempt, ResolutionStatus
from taxonopy.types.gnverifier import ResultData
from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
from taxonopy.resolution.config import ResolutionStrategyConfig


class ResolutionStrategy:
    """Base class for resolution strategies.
    
    This abstract class defines the interface that all resolution strategies
    must implement. Each concrete strategy will implement the can_handle and
    resolve methods to provide specific resolution behavior.
    """
    
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
               attempt_manager: ResolutionAttemptManager) -> ResolutionAttempt:
        """Apply the resolution strategy and return an updated attempt.
        
        Args:
            attempt: The resolution attempt to resolve
            attempt_manager: The attempt manager for creating new attempts
            
        Returns:
            A new resolution attempt with the resolution result
        """
        raise NotImplementedError("Subclasses must implement resolve")
    
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
        for i, rank in enumerate(ranks):
            if i < len(taxa):
                # Convert 'class' to 'class_' to match TaxonomicEntry fields
                if rank == "class":
                    rank = "class_"
                classification[rank] = taxa[i]
        
        return classification
    
    def _get_retry_count(self, attempt: ResolutionAttempt, 
                        attempt_manager: ResolutionAttemptManager) -> int:
        """Count how many retry attempts have been made for this query group.
        
        Args:
            attempt: The current resolution attempt
            attempt_manager: The attempt manager for accessing previous attempts
            
        Returns:
            The number of retry attempts already made
        """
        retry_count = 0
        current_id = attempt.attempt_id
        
        while current_id:
            current = attempt_manager.get_attempt(current_id)
            if not current:
                break
            retry_count += 1
            current_id = current.previous_attempt_id
        
        # Subtract 1 because we counted the current attempt
        return max(0, retry_count - 1)
    
    def _create_failed_attempt(self, attempt: ResolutionAttempt,
                              attempt_manager: ResolutionAttemptManager,
                              reason: str = "Strategy could not resolve") -> ResolutionAttempt:
        """Create a failed resolution attempt with detailed diagnostics.
        
        Args:
            attempt: The resolution attempt that failed
            attempt_manager: The attempt manager for creating new attempts
            reason: The reason for the failure
            
        Returns:
            A new resolution attempt with FAILED status
        """
        metadata = {
            "failure_reason": reason,
            "strategy": self.__class__.__name__,
            "timestamp": datetime.now().isoformat(),
            "previous_attempt_id": attempt.attempt_id  # Store attempt ID in metadata
        }
        
        return attempt_manager.create_attempt(
            query_group_key=attempt.query_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            status=ResolutionStatus.FAILED,
            gnverifier_response=attempt.gnverifier_response,
            metadata=metadata
        )

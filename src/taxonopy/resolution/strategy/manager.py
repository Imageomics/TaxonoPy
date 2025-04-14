"""Manager for coordinating taxonomic resolution strategies.

This module provides a manager class that coordinates the application of
resolution strategies to resolution attempts.
"""

from datetime import datetime
from typing import List, Optional

from taxonopy.types.data_classes import ResolutionAttempt, ResolutionStatus
from taxonopy.resolution.attempt_manager import ResolutionAttemptManager
from taxonopy.resolution.config import ResolutionStrategyConfig
from taxonopy.resolution.strategy.base import ResolutionStrategy


class ResolutionStrategyManager:
    """Manager for coordinating multiple resolution strategies.
    
    This class manages the application of resolution strategies to
    resolution attempts, selecting the appropriate strategy based on
    the attempt's characteristics.
    """
    
    def __init__(self, 
                attempt_manager: ResolutionAttemptManager,
                config: Optional[ResolutionStrategyConfig] = None,
                strategies: Optional[List[ResolutionStrategy]] = None):
        """Initialize the resolution manager.
        
        Args:
            attempt_manager: The attempt manager for creating and tracking attempts
            config: Optional configuration for the manager and strategies
            strategies: Optional list of resolution strategies to use
        """
        self.attempt_manager = attempt_manager
        self.config = config or ResolutionStrategyConfig()
        
        # Use provided strategies or create an empty list
        self.strategies = strategies or []
    
    def add_strategy(self, strategy: ResolutionStrategy) -> None:
        """Add a resolution strategy to the manager.
        
        Args:
            strategy: The strategy to add
        """
        self.strategies.append(strategy)
    
    def resolve(self, attempt: ResolutionAttempt) -> ResolutionAttempt:
        """Apply the first applicable strategy to resolve an attempt.
        
        This method tries each strategy in order until one can handle
        the attempt, then applies that strategy to resolve it.
        
        Args:
            attempt: The resolution attempt to resolve
            
        Returns:
            A new resolution attempt with the resolution result
        """
        for strategy in self.strategies:
            if strategy.can_handle(attempt):
                return strategy.resolve(attempt, self.attempt_manager)
        
        # If no strategy can handle the attempt, mark it as failed
        return self._create_failed_attempt(attempt, "No applicable strategy")
    
    def _create_failed_attempt(self, attempt: ResolutionAttempt, 
                              reason: str) -> ResolutionAttempt:
        """Create a failed resolution attempt with detailed diagnostics.
        
        Args:
            attempt: The resolution attempt that failed
            reason: The reason for the failure
            
        Returns:
            A new resolution attempt with FAILED status
        """
        # Create metadata with previous attempt ID
        metadata = {
            "previous_attempt_id": attempt.attempt_id,
            "failure_reason": reason,
            "timestamp": datetime.now().isoformat(),
            "all_strategies_tried": [s.__class__.__name__ for s in self.strategies]
        }
        
        # Create and return the failed attempt
        return self.attempt_manager.create_attempt(
            entry_group_key=attempt.entry_group_key,
            query_term=attempt.query_term,
            query_rank=attempt.query_rank,
            status=ResolutionStatus.FAILED,
            gnverifier_response=attempt.gnverifier_response,
            metadata=metadata
        )

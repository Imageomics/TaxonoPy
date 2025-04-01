"""Resolution management for TaxonoPy.

This module provides a manager for creating, tracking, and retrieving
resolution attempts during the taxonomic resolution process.
"""

from typing import Dict, List, Optional, Set, Tuple, Union
import logging
from datetime import datetime

from taxonopy.types.data_classes import (
    ResolutionStatus,
    ResolutionAttempt,
    QueryGroupRef
)
from taxonopy.types.gnverifier import Name as GNVerifierName


class ResolutionAttemptManager:
    """Manages the creation and tracking of resolution attempts.
    
    This class is responsible for:
    - Generating unique IDs for resolution attempts (UUIDs as strings)
    - Creating and storing resolution attempts
    - Retrieving attempt chains
    - Managing the resolution strategy
    """
    
    def __init__(self):
        """Initialize a new resolution manager."""
        self._attempts: Dict[str, ResolutionAttempt] = {}
        self._group_latest_attempts: Dict[str, str] = {}  # Maps query_group_key → latest attempt key
        self.logger = logging.getLogger(__name__)
    
    @property
    def attempts(self) -> Dict[str, ResolutionAttempt]:
        """Get a dictionary of all resolution attempts."""
        return dict(self._attempts)  # Return a copy to prevent modification
    
    def create_attempt(
            self,
            query_group_key: str,
            query_term: str,
            query_rank: str,
            status: ResolutionStatus,
            gnverifier_response: Optional[GNVerifierName] = None,
            resolved_classification: Optional[Dict[str, str]] = None,
            metadata: Optional[Dict[str, Union[str, int, float, bool]]] = None
        ) -> ResolutionAttempt:
        """
        Create a new resolution attempt with a computed unique key.
        """
        if metadata is None:
            metadata = {}
        # Create the resolution attempt
        attempt = ResolutionAttempt(
            query_group_key=query_group_key,
            query_term=query_term,
            query_rank=query_rank,
            status=status,
            gnverifier_response=gnverifier_response,
            resolved_classification=resolved_classification,
            metadata=metadata
        )
        
        # Store the attempt using its computed key.
        self._attempts[attempt.key] = attempt
        # Link the query group to this attempt
        self._group_latest_attempts[query_group_key] = attempt.key
        
        return attempt
    
    def get_attempt(self, key: str) -> Optional[ResolutionAttempt]:
        """Get a specific resolution attempt by ID.
        
        Args:
            key: The ID of the attempt to retrieve
            
        Returns:
            The resolution attempt, or None if not found
        """
        return self._attempts.get(key)
    
    def get_latest_attempt(self, query_group_key: str) -> Optional[ResolutionAttempt]:
        """Get the latest resolution attempt for a query group.
        
        Args:
            query_group_key: The key of the query group
            
        Returns:
            The latest resolution attempt, or None if no attempts exist
        """
        key = self._group_latest_attempts.get(query_group_key)
        if key:
            return self._attempts.get(key)
        
        # If the key doesn't exist in our records, log a debug message
        self.logger.debug(f"No attempts found for query group key: {query_group_key}")
        return None
    
    def get_attempt_chain(self, key: str) -> List[ResolutionAttempt]:
        """Get the full chain of attempts starting from the given ID.
        
        The chain starts with the specified attempt and follows the
        previous_attempt_key references to reconstruct the full history.
        
        Args:
            key: The ID of the attempt to start from
            
        Returns:
            List of resolution attempts in chronological order (oldest first)
        """
        chain = []
        current_key = key
        
        # Build the chain by following previous_attempt_key references
        while current_key is not None:
            attempt = self._attempts.get(current_key)
            if not attempt:
                break
            
            chain.append(attempt)
            current_key = attempt.previous_key
        
        # Reverse the chain to get chronological order (oldest first)##TODO: wut
        return list(reversed(chain))
    
    def get_group_attempt_chain(self, query_group_key: str) -> List[ResolutionAttempt]:
        """Get the full chain of attempts for a query group.
        
        Args:
            query_group_key: The key of the query group
            
        Returns:
            List of resolution attempts in chronological order (oldest first)
        """
        attempt_key = self._group_latest_attempts.get(query_group_key)
        if attempt_key:
            return self.get_attempt_chain(attempt_key)
        return []
    
    def get_resolution_status(self, query_group_key: str) -> Optional[ResolutionStatus]:
        """Get the current resolution status for a query group.
        
        Args:
            query_group_key: The key of the query group
            
        Returns:
            The status of the latest attempt, or None if no attempts exist
        """
        attempt = self.get_latest_attempt(query_group_key)
        if attempt:
            return attempt.status
        return None
    
    def get_groups_needing_retry(self) -> List[Tuple[str, str]]:
        """Get query groups that need retry attempts.
        
        Returns pairs of (query_group_key, latest_attempt_id) for groups
        whose latest attempt has a status indicating a retry is needed.
        
        Returns:
            List of (query_group_key, latest_attempt_id) tuples
        """
        retry_groups = []
        
        for query_group_key, key in self._group_latest_attempts.items():
            attempt = self._attempts.get(key)
            if attempt and attempt.status in [
                ResolutionStatus.NO_MATCH,
                ResolutionStatus.FAILED,
                ResolutionStatus.PROCESSING  # For interrupted attempts
            ]:
                retry_groups.append((query_group_key, key))
        
        return retry_groups
    
    def get_successful_attempts(self) -> List[ResolutionAttempt]:
        """Get all resolution attempts that were successful.
        
        Returns:
            List of successful resolution attempts
        """
        return [
            attempt for attempt in self._attempts.values()
            if attempt.status in [
                ResolutionStatus.EXACT_MATCH,
                ResolutionStatus.FUZZY_MATCH,
                ResolutionStatus.PARTIAL_MATCH,
                ResolutionStatus.FORCE_ACCEPTED
            ]
        ]
    
    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about the resolution attempts.
        
        Returns:
            Dictionary with statistics about resolution attempts
        """
        status_counts = {status: 0 for status in ResolutionStatus}
        for attempt in self._attempts.values():
            status_counts[attempt.status] = status_counts.get(attempt.status, 0) + 1
        
        retry_count = sum(1 for attempt in self._attempts.values() if attempt.is_retry)
        
        return {
            "total_attempts": len(self._attempts),
            "total_query_groups": len(self._group_latest_attempts),
            "retry_attempts": retry_count,
            **{f"status_{status.name.lower()}": count for status, count in status_counts.items()}
        }
    
    def save_state(self, path: str) -> None:
        """Save the current state to a file.
        
        TODO: would serialize the manager's state to a file
        
        Args:
            path: The path to save the state to
        """
        #TODO: Placeholder 
        pass
    
    @classmethod
    def load_state(cls, path: str) -> "ResolutionManager":
        """Load state from a file.
        
        TODO: would deserialize the manager's state from a file
        
        Args:
            path: The path to load the state from
            
        Returns:
            A new ResolutionManager with the loaded state
        """
        #TODO: Placeholder
        return cls()

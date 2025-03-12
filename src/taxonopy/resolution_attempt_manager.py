"""Resolution management for TaxonoPy.

This module provides a manager for creating, tracking, and retrieving
resolution attempts during the taxonomic resolution process.
"""

import uuid
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
        self._group_latest_attempts: Dict[str, str] = {}  # Maps query_group_key → latest attempt_id
        self.logger = logging.getLogger(__name__)
    
    @property
    def attempts(self) -> Dict[str, ResolutionAttempt]:
        """Get a dictionary of all resolution attempts."""
        return dict(self._attempts)  # Return a copy to prevent modification

    def _generate_attempt_id(self) -> str:
        """Generate a unique ID for a resolution attempt.
        
        Returns:
            A string representation of a UUID4
        """
        return str(uuid.uuid4())
    
    def create_attempt(self,
                      query_group_key: str,
                      query_term: str,
                      query_rank: str,
                      status: ResolutionStatus,
                      gnverifier_response: Optional[GNVerifierName] = None,
                      resolved_classification: Optional[Dict[str, str]] = None,
                      metadata: Optional[Dict[str, Union[str, int, float, bool]]] = None) -> ResolutionAttempt:
        """Create a new resolution attempt.
        
        This method automatically:
        - Generates a unique ID for the attempt
        - Links to the previous attempt for the same query group, if any
        - Stores the attempt for future retrieval
        - Updates the latest attempt for the query group
        
        Args:
            query_group_key: The key of the query group this attempt is for
            query_term: The term used in the query
            query_rank: The taxonomic rank of the query term
            status: The status of the resolution
            gnverifier_response: Optional GNVerifier response
            resolved_classification: Optional resolved classification
            metadata: Optional metadata about the resolution
            
        Returns:
            The created ResolutionAttempt
        """
        # Generate a unique ID for this attempt
        attempt_id = self._generate_attempt_id()
        
        # Get the previous attempt ID for this query group, if any
        previous_attempt_id = self._group_latest_attempts.get(query_group_key)
        
        # Create the metadata dictionary if not provided
        if metadata is None:
            metadata = {}
        
        # Create the resolution attempt
        attempt = ResolutionAttempt(
            attempt_id=attempt_id,
            query_group_key=query_group_key,
            query_term=query_term,
            query_rank=query_rank,
            status=status,
            gnverifier_response=gnverifier_response,
            resolved_classification=resolved_classification,
            metadata=metadata,
            previous_attempt_id=previous_attempt_id
        )
        
        # Store the attempt
        self._attempts[attempt_id] = attempt
        
        # Update the latest attempt for this query group
        self._group_latest_attempts[query_group_key] = attempt_id
        
        return attempt
    
    def get_attempt(self, attempt_id: str) -> Optional[ResolutionAttempt]:
        """Get a specific resolution attempt by ID.
        
        Args:
            attempt_id: The ID of the attempt to retrieve
            
        Returns:
            The resolution attempt, or None if not found
        """
        return self._attempts.get(attempt_id)
    
    def get_latest_attempt(self, query_group_key: str) -> Optional[ResolutionAttempt]:
        """Get the latest resolution attempt for a query group.
        
        Args:
            query_group_key: The key of the query group
            
        Returns:
            The latest resolution attempt, or None if no attempts exist
        """
        attempt_id = self._group_latest_attempts.get(query_group_key)
        if attempt_id:
            return self._attempts.get(attempt_id)
        return None
    
    def get_attempt_chain(self, attempt_id: str) -> List[ResolutionAttempt]:
        """Get the full chain of attempts starting from the given ID.
        
        The chain starts with the specified attempt and follows the
        previous_attempt_id references to reconstruct the full history.
        
        Args:
            attempt_id: The ID of the attempt to start from
            
        Returns:
            List of resolution attempts in chronological order (oldest first)
        """
        chain = []
        current_id = attempt_id
        
        # Build the chain by following previous_attempt_id references
        while current_id is not None:
            attempt = self._attempts.get(current_id)
            if not attempt:
                break
            
            chain.append(attempt)
            current_id = attempt.previous_attempt_id
        
        # Reverse the chain to get chronological order (oldest first)
        return list(reversed(chain))
    
    def get_group_attempt_chain(self, query_group_key: str) -> List[ResolutionAttempt]:
        """Get the full chain of attempts for a query group.
        
        Args:
            query_group_key: The key of the query group
            
        Returns:
            List of resolution attempts in chronological order (oldest first)
        """
        attempt_id = self._group_latest_attempts.get(query_group_key)
        if attempt_id:
            return self.get_attempt_chain(attempt_id)
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
        
        for query_group_key, attempt_id in self._group_latest_attempts.items():
            attempt = self._attempts.get(attempt_id)
            if attempt and attempt.status in [
                ResolutionStatus.NO_MATCH,
                ResolutionStatus.FAILED,
                ResolutionStatus.PROCESSING  # For interrupted attempts
            ]:
                retry_groups.append((query_group_key, attempt_id))
        
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

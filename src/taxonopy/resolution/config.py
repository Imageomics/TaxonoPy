"""Configuration for taxonomic resolution strategies.

This module provides a centralized configuration class for controlling the
behavior of resolution strategies.
"""

from typing import Dict, Any, List


class ResolutionStrategyConfig:
    """Configuration for resolution strategies.
    
    This class centralizes configuration parameters that affect how
    resolution strategies behave. Making these configurable allows
    the resolution behavior to be adjusted without code changes.
    """
    
    def __init__(self):
        # Default configuration values
        self.min_fuzzy_score = 0.8
        self.preferred_data_sources = [11, 172, 1]  # GBIF, OTOL, CoL
        self.max_retry_attempts = 3
        self.synonym_resolution = "accept"  # Options: accept, reject, resolve_to_accepted
        self.taxonomic_ranks = ["kingdom", "phylum", "class_", "order", "family", "genus", "species"]
        
    def update(self, config_dict: Dict[str, Any]) -> None:
        """Update configuration from a dictionary.
        
        Args:
            config_dict: Dictionary of configuration parameters to update
        """
        for key, value in config_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                raise ValueError(f"Unknown configuration parameter: {key}")

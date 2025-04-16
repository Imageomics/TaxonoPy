"""Configuration for taxonomic resolution strategies.

This module provides a centralized configuration class for controlling the
behavior of resolution strategies.
"""

from typing import Dict, Any, List
from taxonopy.constants import TAXONOMIC_RANKS


class ResolutionStrategyConfig:
    """Configuration for resolution strategies.
    
    This class centralizes configuration parameters that affect how
    resolution strategies behave. Making these configurable allows
    the resolution behavior to be adjusted without code changes.
    """
    
    # def __init__(self):
        # Placeholder for configuration parameters if needed

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

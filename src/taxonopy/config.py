"""
Configuration management for TaxonoPy.

This module provides a centralized configuration system with default values
that can be overridden by command-line arguments.
"""

from pathlib import Path
from typing import Dict, Any, Optional, Union
import os

class Config:
    """Centralized configuration for TaxonoPy.
    
    This class defines default values for all configurable parameters and
    provides methods to update them based on command-line arguments.
    """
    
    def __init__(self):
        """Initialize configuration with default values."""
        # Paths
        self.cache_dir = str(Path.home() / ".cache" / "taxonopy")
        
        # GNVerifier settings
        self.gnverifier_image = "gnames/gnverifier:v1.2.3"
        self.data_sources = "11"  # Default to GBIF (11)
        self.all_matches = True
        self.capitalize = True
        self.jobs = 1
        self.fuzzy_uninomial = False
        self.fuzzy_relaxed = False 
        self.species_group = False
        
        # Processing settings
        self.batch_size = 10000
        
        # Cache settings
        self.cache_max_age = 60*60*24*7  # 1 week in seconds
        
        # Output settings
        self.output_format = "parquet"
    
    def update_from_args(self, args: Dict[str, Any]) -> None:
        """Update configuration from command-line arguments.
        
        Args:
            args: Dictionary of argument name to value
        """
        # Update configuration with command-line arguments
        if 'output_dir' in args and args['output_dir'] is not None:
            self.output_dir = args['output_dir']
            
        if 'batch_size' in args and args['batch_size'] is not None:
            self.batch_size = args['batch_size']
            
        if 'gnverifier_image' in args and args['gnverifier_image'] is not None:
            self.gnverifier_image = args['gnverifier_image']
            
        if 'data_sources' in args and args['data_sources'] is not None:
            self.data_sources = args['data_sources']
            
        if 'output_format' in args and args['output_format'] is not None:
            self.output_format = args['output_format']
            
        # Optional boolean flags
        if 'all_matches' in args:
            self.all_matches = args['all_matches']
            
        if 'capitalize' in args:
            self.capitalize = args['capitalize']
            
        if 'fuzzy_uninomial' in args:
            self.fuzzy_uninomial = args['fuzzy_uninomial']
            
        if 'fuzzy_relaxed' in args:
            self.fuzzy_relaxed = args['fuzzy_relaxed']
            
        if 'species_group' in args:
            self.species_group = args['species_group']
    
    def ensure_directories(self) -> None:
        """Create any required directories."""
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        if hasattr(self, 'output_dir'):
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    def get_config_summary(self) -> str:
        """Get a summary of the current configuration.
        
        Returns:
            Formatted string with configuration summary
        """
        config_items = []
        for key, value in vars(self).items():
            if not key.startswith('_'):  # Skip private attributes
                config_items.append(f"{key}: {value}")
        
        return "Current Configuration:\n" + "\n".join(config_items)

# Create a singleton instance
config = Config()

"""Registry for taxonomic resolution strategies.

This module provides a central registry for resolution strategies,
allowing them to be looked up by name and instantiated dynamically.
"""

from typing import Dict, List, Type, Optional

from taxonopy.resolution.strategy.base import ResolutionStrategy
from taxonopy.resolution.config import ResolutionStrategyConfig


class StrategyRegistry:
    """Registry of resolution strategies.
    
    This class provides a central registry for resolution strategies,
    allowing them to be looked up by name and instantiated dynamically.
    """
    
    _strategies: Dict[str, Type[ResolutionStrategy]] = {}
    
    @classmethod
    def register(cls, strategy_name: str, strategy_class: Type[ResolutionStrategy]) -> None:
        """Register a new strategy.
        
        Args:
            strategy_name: The name to register the strategy under
            strategy_class: The strategy class to register
        """
        cls._strategies[strategy_name] = strategy_class
    
    @classmethod
    def get_strategy(cls, strategy_name: str) -> Type[ResolutionStrategy]:
        """Get a strategy class by name.
        
        Args:
            strategy_name: The name of the strategy to get
            
        Returns:
            The strategy class
            
        Raises:
            ValueError: If the strategy is not registered
        """
        if strategy_name not in cls._strategies:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        return cls._strategies[strategy_name]
    
    @classmethod
    def create_strategy(cls, strategy_name: str, 
                      config: Optional[ResolutionStrategyConfig] = None) -> ResolutionStrategy:
        """Create a new instance of a strategy.
        
        Args:
            strategy_name: The name of the strategy to create
            config: Optional configuration for the strategy
            
        Returns:
            A new instance of the strategy
            
        Raises:
            ValueError: If the strategy is not registered
        """
        strategy_class = cls.get_strategy(strategy_name)
        return strategy_class(config)
    
    @classmethod
    def list_strategies(cls) -> List[str]:
        """List all registered strategies.
        
        Returns:
            List of strategy names
        """
        return list(cls._strategies.keys())

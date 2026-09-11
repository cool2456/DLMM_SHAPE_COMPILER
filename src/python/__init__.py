"""
DLMM Compiler - Liquidity distribution optimizer for Meteora DLMM

This module provides tools for constructing, optimizing, and exporting
custom liquidity distributions for deployment on Meteora's Dynamic
Liquidity Market Maker (DLMM) protocol.
"""

from .templates import (
    # Core optimization
    approximate_nnls,
    greedy_select_templates,
    generate_templates,
    
    # Target distribution functions
    create_gaussian_target,
    rectangle,
    curve,
    bid_ask,
    
    # Export/Import
    export_strategy_plan,
    load_strategy_plan,
    
    # Utilities
    create_target_distribution,
)

__version__ = "1.0.0"
__all__ = [
    "approximate_nnls",
    "greedy_select_templates", 
    "generate_templates",
    "create_gaussian_target",
    "rectangle",
    "curve",
    "bid_ask",
    "export_strategy_plan",
    "load_strategy_plan",
    "create_target_distribution",
]

"""
SPL Feature Model for SDD Knowledge System.

This module provides feature model management for the SDD Toolkit knowledge system.
It defines mandatory, optional, and alternative features along with their dependencies
and constraints.

Usage:
    from feature_model import FeatureModel, FeatureResolver

    # Load feature model
    model = FeatureModel("feature_tree.json")

    # Validate the tree
    errors = model.validate_tree()
    if errors:
        print(f"Validation errors: {errors}")

    # Get recommended configuration
    resolver = FeatureResolver(model)
    config = resolver.get_recommended_configuration("research_report")

    # Resolve dependencies
    resolved = resolver.resolve(["context", "templates"])
"""

from .model import FeatureModel
from .resolver import FeatureResolver

__all__ = ["FeatureModel", "FeatureResolver"]
__version__ = "1.0.0"

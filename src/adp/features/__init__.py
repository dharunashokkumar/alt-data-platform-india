"""Gold feature layer: Silver -> point-in-time FeatureRows.

A feature recipe is registered per source. `compute.run` is source-agnostic;
adding features for a new source = one recipe function + @feature_recipe.
"""

from adp.features import posoco_features  # noqa: F401  (registers recipe)

__all__ = ["posoco_features"]

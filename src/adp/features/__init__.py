"""Gold feature layer: Silver -> point-in-time FeatureRows.

A feature recipe is registered per source. `compute.run` is source-agnostic;
adding features for a new source = one recipe function + @feature_recipe.
"""

from adp.features import (  # noqa: F401  (registers recipes)
    gst_features,
    posoco_features,
    railway_features,
)

__all__ = ["posoco_features", "gst_features", "railway_features"]

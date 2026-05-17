"""Data source plugins.

Importing this package imports every concrete source so that its
`@register` decorator runs and the registry is populated. Add a new source
module here and it is discoverable everywhere — no other code changes.
"""

from adp.sources import posoco  # noqa: F401

__all__ = ["posoco"]

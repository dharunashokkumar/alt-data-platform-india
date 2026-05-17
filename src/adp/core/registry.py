"""Data source registry.

Sources self-register on import. The flow/CLI layer never imports a concrete
source — it asks the registry by name. This is what makes adding a source a
zero-touch change for everything downstream.
"""

from __future__ import annotations

from adp.core.base import DataSource

_REGISTRY: dict[str, type[DataSource]] = {}


def register(cls: type[DataSource]) -> type[DataSource]:
    """Class decorator: register a DataSource implementation by its `name`."""
    if not getattr(cls, "name", None):
        raise ValueError(f"{cls.__name__} must set a non-empty `name`")
    _REGISTRY[cls.name] = cls
    return cls


def get_source(name: str) -> DataSource:
    # Import the sources package so its submodules register themselves.
    import adp.sources  # noqa: F401

    if name not in _REGISTRY:
        raise KeyError(
            f"unknown source '{name}'. registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]()


def list_sources() -> list[str]:
    import adp.sources  # noqa: F401

    return sorted(_REGISTRY)

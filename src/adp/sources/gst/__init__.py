"""GST e-way bill source package. Importing it runs the @register decorator."""

from adp.sources.gst import source  # noqa: F401

__all__ = ["source"]

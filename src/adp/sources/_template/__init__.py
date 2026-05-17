"""Copy this directory to add a new data source.

Steps:
  1. cp -r src/adp/sources/_template src/adp/sources/<name>
  2. Fill in discover()/fetch()/parse() in source.py, set `name`.
  3. Add `from adp.sources import <name>` to src/adp/sources/__init__.py.
  4. Add a feature recipe in adp.features (see adp/features/posoco_features.py).
That's the entire integration surface — nothing downstream changes.
"""

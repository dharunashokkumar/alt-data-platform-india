"""Alternative Data Platform for Indian Equities.

Layered, plugin-based architecture:

    adp.core      - shared contracts: config, storage, schemas, PIT, registry
    adp.sources   - pluggable DataSource implementations (posoco is the reference)
    adp.features  - silver -> gold point-in-time feature computation
    adp.signals   - feature -> signal factor models
    adp.backtest  - vectorized, PIT-correct backtester
    adp.api       - FastAPI delivery layer

Every layer talks only through `adp.core` contracts and storage, so any layer
or source can be scaled or swapped without touching the others.
"""

__version__ = "0.1.0"

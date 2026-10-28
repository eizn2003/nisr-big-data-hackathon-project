"""Compatibility layer exposing the NBR anomaly experiment API at the historical path.

This keeps the current model implementation under src/models/nbr_intelligence while
preserving the legacy import path expected by the existing tests and callers.
"""

from src.models.nbr_intelligence.experiment import *  # noqa: F401,F403

from src.models.nbr_intelligence.experiment import __all__ as _MODEL_ALL

__all__ = list(_MODEL_ALL)

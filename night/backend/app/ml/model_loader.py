"""
ML Model Registry — Loads XGBoost + SHAP at startup, reused per-request.
"""

import asyncio
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Holds loaded models — loaded once at startup, reused per-request."""

    def __init__(self):
        self._xgb_model = None
        self._shap_explainer = None
        self._ready: bool = False

    async def load_all(self):
        """Load models from disk at application startup."""
        try:
            import joblib

            loop = asyncio.get_event_loop()
            # Load in thread pool (blocking I/O)
            self._xgb_model = await loop.run_in_executor(
                None, joblib.load, settings.RISK_MODEL_PATH
            )
            self._shap_explainer = await loop.run_in_executor(
                None, joblib.load, settings.SHAP_EXPLAINER_PATH
            )
            self._ready = True
            logger.info("XGBoost model + SHAP explainer loaded successfully")
        except FileNotFoundError:
            logger.warning(
                "ML model files not found — running in HEURISTIC mode. "
                "Train and save models to app/ml/models/ for production."
            )
            self._ready = False
        except Exception as e:
            logger.error(f"Failed to load ML models: {e}", exc_info=True)
            self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    async def cleanup(self):
        self._xgb_model = None
        self._shap_explainer = None
        self._ready = False

    @property
    def model(self):
        return self._xgb_model

    @property
    def explainer(self):
        return self._shap_explainer


model_registry = ModelRegistry()
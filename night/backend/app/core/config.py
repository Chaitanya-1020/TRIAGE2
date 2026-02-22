from pydantic_settings import BaseSettings
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "REPLACE-WITH-SECURE-RANDOM-64-CHAR-STRING"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]
    FRONTEND_URL: str = "http://localhost:3000"

    # Database — async SQLite for dev, asyncpg for production
    DATABASE_URL: str = "sqlite+aiosqlite:///./cdss.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    MAGIC_LINK_EXPIRE_MINUTES: int = 120

    # ML
    RISK_MODEL_PATH: str = "app/ml/models/xgb_risk_model.pkl"
    SHAP_EXPLAINER_PATH: str = "app/ml/models/shap_explainer.pkl"

    # Gemini
    GEMINI_API_KEY: str = "AIzaSyAEVQa8OYHKoPNJkIII6T5lnWzp8oXlGWc"
    GEMINI_MODEL: str = "gemini-1.5-flash"

    # ── Clinical Thresholds (NEWS2-aligned, configurable via env) ─────────
    # CRITICAL thresholds — hard override (life-threatening)
    SPO2_CRITICAL: float = 85.0      # Was 90 — reduced to avoid over-triage
    SBP_CRITICAL: int = 80           # Was 90 — true shock threshold
    RR_CRITICAL: int = 35            # Was 30 — severe distress only
    TEMP_CRITICAL: float = 41.0      # Was 40 — hyperpyrexia only
    TEMP_HYPOTHERMIA: float = 35.0
    SBP_HYPERTENSIVE_CRISIS: int = 180
    GCS_CRITICAL: int = 8
    BG_SEVERE_HYPO: int = 54
    BG_SEVERE_HYPER: int = 400

    # HIGH thresholds — weighted scoring
    SPO2_HIGH: float = 92.0
    SBP_HIGH: int = 100
    HR_HIGH_TACHY: int = 120
    HR_HIGH_BRADY: int = 45
    RR_HIGH: int = 24
    TEMP_HIGH_FEVER: float = 39.0

    # ── Hybrid Engine Weights ─────────────────────────────────────────────
    RULE_ENGINE_WEIGHT: float = 0.6
    ML_ENGINE_WEIGHT: float = 0.4
    CRITICAL_OVERRIDE_THRESHOLD: float = 0.85   # Weighted score to trigger critical
    HIGH_OVERRIDE_THRESHOLD: float = 0.55        # Weighted score to trigger high

    # PHI Encryption
    PHI_ENCRYPTION_KEY: str = "QSr-KD5QVWXVDdZgnFnSKZvCbQydZm9IjZf_9qzDmVk="

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

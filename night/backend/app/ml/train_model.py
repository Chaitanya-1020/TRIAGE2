"""
XGBoost Model Training Script
================================
Run: python -m app.ml.train_model

Training data format:
  CSV with columns matching FEATURE_NAMES + "label" (0=low-risk, 1=high-risk)

Produces:
  app/ml/models/xgb_risk_model.pkl
  app/ml/models/shap_explainer.pkl
"""

import numpy as np
import pandas as pd
import xgboost as xgb
import shap
import joblib
import os
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import (
    roc_auc_score, classification_report,
    confusion_matrix, brier_score_loss
)
from sklearn.calibration import CalibratedClassifierCV

os.makedirs("app/ml/models", exist_ok=True)

# ─── Feature Names (must match risk_predictor.py) ─────────────────────────────

FEATURE_NAMES = [
    "spo2", "systolic_bp", "diastolic_bp", "heart_rate", "respiratory_rate",
    "temperature", "blood_glucose", "age_years", "sex_encoded",
    "is_pregnant", "is_diabetic", "has_heart_disease", "is_immunocompromised",
    "bmi_proxy", "shock_index", "pulse_pressure",
    "has_chest_pain", "has_altered_consciousness", "has_breathing_difficulty",
    "has_severe_headache", "has_bleeding", "red_flag_count"
]


def generate_synthetic_data(n_samples: int = 5000) -> pd.DataFrame:
    """
    Generate clinically-plausible synthetic training data.
    Replace with real PHC patient outcome data in production.

    Labels: 1 = required urgent intervention/referral within 24h
            0 = managed safely at PHC
    """
    np.random.seed(42)
    df = pd.DataFrame()

    # Normal range baseline
    df["spo2"] = np.random.normal(97, 3, n_samples).clip(70, 100)
    df["systolic_bp"] = np.random.normal(120, 20, n_samples).clip(60, 220)
    df["diastolic_bp"] = (df["systolic_bp"] * 0.65 + np.random.normal(0, 8, n_samples)).clip(40, 140)
    df["heart_rate"] = np.random.normal(82, 18, n_samples).clip(30, 200)
    df["respiratory_rate"] = np.random.normal(16, 4, n_samples).clip(6, 50)
    df["temperature"] = np.random.normal(37.0, 0.8, n_samples).clip(33, 42)
    df["blood_glucose"] = np.random.lognormal(4.6, 0.4, n_samples).clip(40, 600)
    df["age_years"] = np.random.exponential(35, n_samples).clip(0, 100)
    df["sex_encoded"] = np.random.randint(0, 2, n_samples).astype(float)
    df["is_pregnant"] = np.random.binomial(1, 0.08, n_samples).astype(float)
    df["is_diabetic"] = np.random.binomial(1, 0.15, n_samples).astype(float)
    df["has_heart_disease"] = np.random.binomial(1, 0.12, n_samples).astype(float)
    df["is_immunocompromised"] = np.random.binomial(1, 0.05, n_samples).astype(float)
    df["bmi_proxy"] = np.random.normal(1.0, 0.25, n_samples).clip(0.3, 2.0)
    df["shock_index"] = df["heart_rate"] / df["systolic_bp"].clip(lower=1)
    df["pulse_pressure"] = df["systolic_bp"] - df["diastolic_bp"]
    df["has_chest_pain"] = np.random.binomial(1, 0.12, n_samples).astype(float)
    df["has_altered_consciousness"] = np.random.binomial(1, 0.06, n_samples).astype(float)
    df["has_breathing_difficulty"] = np.random.binomial(1, 0.15, n_samples).astype(float)
    df["has_severe_headache"] = np.random.binomial(1, 0.10, n_samples).astype(float)
    df["has_bleeding"] = np.random.binomial(1, 0.07, n_samples).astype(float)
    df["red_flag_count"] = (
        df["has_chest_pain"] + df["has_altered_consciousness"] +
        df["has_breathing_difficulty"] + df["has_severe_headache"] + df["has_bleeding"]
    )

    # Label generation (based on clinical risk factors)
    risk = (
        (97 - df["spo2"].clip(upper=97)) * 0.04 +
        ((90 - df["systolic_bp"]).clip(lower=0)) * 0.015 +
        (df["shock_index"].clip(lower=0.5) - 0.5) * 0.3 +
        ((df["respiratory_rate"] - 20).clip(lower=0)) * 0.02 +
        ((df["temperature"] - 38).clip(lower=0)) * 0.08 +
        df["has_chest_pain"] * 0.3 +
        df["has_altered_consciousness"] * 0.4 +
        df["has_breathing_difficulty"] * 0.25 +
        df["has_bleeding"] * 0.2 +
        df["is_immunocompromised"] * 0.2 +
        df["is_pregnant"] * 0.15 +
        df["is_diabetic"] * 0.1 +
        df["has_heart_disease"] * 0.15 +
        np.random.normal(0, 0.1, n_samples)  # noise
    )

    df["label"] = (risk > 0.5).astype(int)
    print(f"Training data: {n_samples} samples, {df['label'].mean():.1%} high-risk")
    return df


def train():
    print("═══ CDSS XGBoost Training ═══")

    df = generate_synthetic_data(5000)

    X = df[FEATURE_NAMES].values
    y = df["label"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=42
    )

    # ── XGBoost Model ────────────────────────────────────────────────────────

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=y_train.sum() / (len(y_train) - y_train.sum()),  # Handle imbalance
        eval_metric="auc",
        use_label_encoder=False,
        random_state=42,
        n_jobs=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        early_stopping_rounds=20,
        verbose=False,
    )

    # ── Probability Calibration ───────────────────────────────────────────────

    calibrated = CalibratedClassifierCV(model, method="isotonic", cv=5)
    calibrated.fit(X_train, y_train)

    # ── Evaluation ───────────────────────────────────────────────────────────

    y_prob = calibrated.predict_proba(X_test)[:, 1]
    y_pred = (y_prob > 0.5).astype(int)

    auc = roc_auc_score(y_test, y_prob)
    brier = brier_score_loss(y_test, y_prob)
    print(f"\nAUC-ROC: {auc:.4f}")
    print(f"Brier Score: {brier:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["Low Risk", "High Risk"]))

    # Clinical safety check: sensitivity must be HIGH for medical use
    cm = confusion_matrix(y_test, y_pred)
    sensitivity = cm[1, 1] / (cm[1, 0] + cm[1, 1])
    print(f"Sensitivity (recall for high-risk): {sensitivity:.3f}")
    if sensitivity < 0.85:
        print("⚠️  WARNING: Sensitivity < 0.85 — review model before clinical use!")

    # ── SHAP Explainer ───────────────────────────────────────────────────────

    print("\nBuilding SHAP TreeExplainer...")
    # Use underlying XGBoost model for SHAP (not calibrated wrapper)
    shap_explainer = shap.TreeExplainer(model)

    # ── Save ──────────────────────────────────────────────────────────────────

    joblib.dump(calibrated, "app/ml/models/xgb_risk_model.pkl", compress=3)
    joblib.dump(shap_explainer, "app/ml/models/shap_explainer.pkl", compress=3)
    print("\n✅ Models saved to app/ml/models/")
    print("   xgb_risk_model.pkl")
    print("   shap_explainer.pkl")


if __name__ == "__main__":
    train()

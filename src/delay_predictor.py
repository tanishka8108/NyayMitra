
import pandas as pd
import joblib
import shap
import xgboost as xgb
from pathlib import Path

MODELS_DIR = Path(__file__).parent.parent / "models"

model_type = joblib.load(MODELS_DIR / "model_type.pkl")

if model_type == "xgboost":
    model = xgb.XGBRegressor()
    model.load_model(str(MODELS_DIR / "delay_next_hearing_model.json"))
else:
    model = joblib.load(MODELS_DIR / "delay_next_hearing_model.pkl")

feature_columns = joblib.load(MODELS_DIR / "feature_columns.pkl")
case_type_pace_lookup = joblib.load(MODELS_DIR / "case_type_pace_lookup.pkl")
court_pace_lookup = joblib.load(MODELS_DIR / "court_pace_lookup.pkl")
overall_mean_pace = joblib.load(MODELS_DIR / "overall_mean_pace.pkl")
resid_std = joblib.load(MODELS_DIR / "resid_std.pkl")

explainer = shap.TreeExplainer(model)


def get_confidence_range(prediction, std=resid_std):
    lower = max(0, prediction - 1.28 * std)
    upper = prediction + 1.28 * std
    width = upper - lower
    if width < 20:
        label = "high"
    elif width < 45:
        label = "medium"
    else:
        label = "low"
    return round(lower), round(upper), label

def build_feature_row(case_type, court, district, state):
    row = {col: 0 for col in feature_columns}
    row["case_type_historical_pace"] = case_type_pace_lookup.get(case_type, overall_mean_pace)
    row["court_historical_pace"] = court_pace_lookup.get(court, overall_mean_pace)

    for col in [f"case_type_{case_type}", f"court_name_{court}",
                f"district_{district}", f"state_{state}"]:
        if col in row:
            row[col] = 1

    return pd.DataFrame([row])[feature_columns]


def explain_prediction(X_row, top_n=3):
    row_2d = X_row.values.reshape(1, -1)
    shap_vals = explainer.shap_values(row_2d)
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[0]
    shap_vals = shap_vals[0] if shap_vals.ndim > 1 else shap_vals

    contributions = list(zip(feature_columns, shap_vals))
    contributions.sort(key=lambda x: abs(x[1]), reverse=True)
    top = contributions[:top_n]
    explanation = []
    for feat, val in top:
        direction = "increased" if val > 0 else "decreased"
        clean_name = feat.replace("_", " ")
        explanation.append({
            "feature": feat,
            "contribution_days": round(float(val), 1),
            "text": f"{clean_name} {direction} the estimate by about {abs(round(val))} days"
        })
    return explanation


def predict_delay(case_type, court, district, state):
    X_new = build_feature_row(case_type, court, district, state)
    prediction = model.predict(X_new)[0]
    lower, upper, confidence = get_confidence_range(prediction)
    explanation = explain_prediction(X_new.iloc[0])

    return {
        "predicted_delay_days": round(float(prediction)),
        "predicted_delay_lower": lower,
        "predicted_delay_upper": upper,
        "confidence_score": round(1 - (upper - lower) / 100, 2),
        "confidence_label": confidence,
        "explanation": explanation,
        "model_version": f"v1_{model_type}",
    }


# =====================================================================
# Days-to-Disposal companion model (same "Delay Prediction" action card).
# Trained by src/train_disposal_model.py. All artifacts carry a
# "_disposal" suffix, so nothing above is affected. If the model was
# never trained (insufficient disposed cases), DISPOSAL stays None and
# predict_disposal() returns None -> API sends null.
# =====================================================================

def _load_disposal_bundle():
    """Load the disposal model + lookups defensively; None if absent/broken."""
    try:
        disposal_model_type = joblib.load(MODELS_DIR / "model_type_disposal.pkl")
        if disposal_model_type == "xgboost":
            disposal_model = xgb.XGBRegressor()
            disposal_model.load_model(str(MODELS_DIR / "delay_disposal_model.json"))
        else:
            disposal_model = joblib.load(MODELS_DIR / "delay_disposal_model.pkl")

        bundle = {
            "model_type": disposal_model_type,
            "model": disposal_model,
            "feature_columns": joblib.load(MODELS_DIR / "feature_columns_disposal.pkl"),
            "case_type_pace_lookup": joblib.load(MODELS_DIR / "case_type_pace_lookup_disposal.pkl"),
            "court_pace_lookup": joblib.load(MODELS_DIR / "court_pace_lookup_disposal.pkl"),
            "overall_mean_pace": joblib.load(MODELS_DIR / "overall_mean_pace_disposal.pkl"),
            "resid_std": joblib.load(MODELS_DIR / "resid_std_disposal.pkl"),
        }
        try:
            bundle["numeric_defaults"] = joblib.load(MODELS_DIR / "numeric_defaults_disposal.pkl")
        except Exception:
            bundle["numeric_defaults"] = {}
        return bundle
    except Exception as e:
        print(f"Disposal model not available (training skipped or incomplete): {e}")
        return None


DISPOSAL = _load_disposal_bundle()
disposal_explainer = shap.TreeExplainer(DISPOSAL["model"]) if DISPOSAL else None


def get_disposal_confidence_range(prediction, std=None):
    if std is None:
        std = DISPOSAL["resid_std"]
    lower = max(0, prediction - 1.28 * std)
    upper = prediction + 1.28 * std
    width = upper - lower
    if width < 20:
        label = "high"
    elif width < 45:
        label = "medium"
    else:
        label = "low"
    return round(lower), round(upper), label


def build_disposal_feature_row(case_type, court_name, district, state):
    """Raw case details -> feature row matching the disposal model's columns."""
    disposal_feature_columns = DISPOSAL["feature_columns"]
    row = {col: 0 for col in disposal_feature_columns}

    row["case_type_historical_pace"] = DISPOSAL["case_type_pace_lookup"].get(
        case_type, DISPOSAL["overall_mean_pace"]
    )
    row["court_historical_pace"] = DISPOSAL["court_pace_lookup"].get(
        court_name, DISPOSAL["overall_mean_pace"]
    )

    # numeric features (total_hearings / average_hearing_gap_days) default to
    # their training medians — the serving signature only receives categories.
    for col, default in DISPOSAL["numeric_defaults"].items():
        if col in row:
            row[col] = default

    for col in [f"case_type_{case_type}", f"court_name_{court_name}",
                f"district_{district}", f"state_{state}"]:
        if col in row:
            row[col] = 1

    return pd.DataFrame([row])[disposal_feature_columns]


def explain_disposal_prediction(X_row, top_n=3):
    row_2d = X_row.values.reshape(1, -1)
    shap_vals = disposal_explainer.shap_values(row_2d)
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[0]
    shap_vals = shap_vals[0] if shap_vals.ndim > 1 else shap_vals

    contributions = list(zip(DISPOSAL["feature_columns"], shap_vals))
    contributions.sort(key=lambda x: abs(x[1]), reverse=True)
    top = contributions[:top_n]
    explanation = []
    for feat, val in top:
        direction = "increased" if val > 0 else "decreased"
        clean_name = feat.replace("_", " ")
        explanation.append({
            "feature": feat,
            "contribution_days": round(float(val), 1),
            "text": f"{clean_name} {direction} the estimate by about {abs(round(val))} days"
        })
    return explanation


def predict_disposal(case_type, court_name, district, state):
    """
    Days-to-Disposal prediction. Returns None when the disposal model was
    not trained (fewer than 25 usable disposed cases) so the API can
    report predicted_disposal_days as null without affecting predict_delay().
    """
    if DISPOSAL is None:
        return None

    X_new = build_disposal_feature_row(case_type, court_name, district, state)
    prediction = DISPOSAL["model"].predict(X_new)[0]
    lower, upper, confidence = get_disposal_confidence_range(prediction)
    explanation = explain_disposal_prediction(X_new.iloc[0])

    return {
        "predicted_disposal_days": round(float(prediction)),
        "predicted_disposal_lower": lower,
        "predicted_disposal_upper": upper,
        "confidence_score": round(1 - (upper - lower) / 100, 2),
        "confidence_label": confidence,
        "explanation": explanation,
        "model_version": f"v1_disposal_{DISPOSAL['model_type']}",
    }


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

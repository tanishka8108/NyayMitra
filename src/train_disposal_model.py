#!/usr/bin/env python
"""
src/train_disposal_model.py

Pipeline (mirrors the next-hearing model end-to-end):
  1. Load + normalize every JSON/JSONL file under data/raw/ and
     data/disposedata/Maharashtra with the notebook's
     normalize_raw_scrape / normalize_ml_ready logic.
  2. Keep only target_available == True (disposed) cases.
     Target = case["disposal_duration_days"] when the source provides it,
     else (disposal_date - filing_date).days.
  3. LEAKAGE GUARD: filing_date / disposal_date are used ONLY to derive the
     target column, then dropped from the feature matrix before training.
  4. Fewer than 25 usable disposed cases -> print a clear warning, report
     descriptive stats (mean/median/min/max/std) and STOP (no training).
  5. Features: one-hot case_type/court_name/district/state +
     case_type_historical_pace + court_historical_pace (computed exactly the
     way the next-hearing model does) + total_hearings/number_of_hearings +
     average_hearing_gap_days when present.
  6. 80/20 split. The TRAINING target is winsorized at its 95th
     percentile — the cap is computed from the training split ONLY
     (never the full dataset) to avoid leakage. RandomForest and XGBoost
     are both trained on the capped target but scored against the
     UNCAPPED test targets, so metrics stay comparable with the
     uncapped baseline; an uncapped control run is trained in the same
     pass for that comparison. The lower-MAE winsorized model is kept.
     Raw days_to_disposal / disposal_duration_days values are never
     modified — only the model's training target is capped, and the
     uncapped values are kept separately in
     models/target_report_disposal.pkl for reporting/documentation.
  7. SHAP explainability sample in the same top-3 format as
     src/delay_predictor.py.
  8. Everything is saved to models/ with a "_disposal" suffix so the
     next-hearing model's artifacts are never overwritten.

Memory-friendly: BLAS/XGBoost/RF threads capped at 2 and files are streamed
one at a time, so peak RAM stays small.

Run:  python src/train_disposal_model.py
"""

import json
import sys
from pathlib import Path

# --- keep RAM / CPU footprint small (set before numpy/xgboost thread pools start) ---
import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

import numpy as np
import pandas as pd
import joblib
import shap
import xgboost as xgb
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = ROOT / "data" / "raw"
DISPOSAL_DATA_DIR = ROOT / "data" / "disposedata" / "Maharashtra"
MODELS_DIR = ROOT / "models"

MIN_USABLE_CASES = 25
RANDOM_STATE = 42

CATEGORICAL_COLS = ["case_type", "court_name", "district", "state"]
NUMERIC_CANDIDATES = ["number_of_hearings", "total_hearings", "average_hearing_gap_days"]

# Columns that must NEVER enter the feature matrix (target leakage).
LEAKAGE_COLS = [
    "filing_date", "registration_date", "first_hearing_date", "next_hearing_date",
    "disposal_date", "disposal_duration_days", "days_to_disposal",
]

ARTIFACT_NAMES = [
    "delay_disposal_model.pkl",
    "delay_disposal_model.json",
    "model_type_disposal.pkl",
    "feature_columns_disposal.pkl",
    "case_type_pace_lookup_disposal.pkl",
    "court_pace_lookup_disposal.pkl",
    "overall_mean_pace_disposal.pkl",
    "resid_std_disposal.pkl",
    "numeric_defaults_disposal.pkl",
    "target_cap_disposal.pkl",
    "target_report_disposal.pkl",
    "disposal_model_status.pkl",
]


def log(msg=""):
    print(msg, flush=True)


# =====================================================================
# Normalization logic — copied from notebooks/04_model_building.ipynb
# (load_any_file / detect_schema / normalize_ml_ready /
#  normalize_raw_scrape), with the one change mandated for this model:
#  prefer case["disposal_duration_days"] as days_to_disposal.
# =====================================================================

def load_any_file(filepath):
    """Handles plain JSON (list, dict with 'cases', or single dict) and JSONL."""
    records = []
    text = filepath.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(text)
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict) and "cases" in data:
            records = data["cases"]
        else:
            records = [data]
    except json.JSONDecodeError:
        for line in text.splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def detect_schema(record):
    if "case_id" in record and "target_available" in record:
        return "ml_ready"
    elif "normalized_case" in record:
        return "raw_normalized_wrapped"
    elif "case" in record and "case_timeline" in record:
        return "raw_normalized_flat"
    return "unknown"


def normalize_ml_ready(record):
    """Already flat — no changes needed."""
    return record


def _extract_container(record, schema_type):
    if schema_type == "raw_normalized_wrapped":
        return record.get("normalized_case", {})
    return record  # raw_normalized_flat


def normalize_raw_scrape(record, schema_type):
    """
    Flattens either raw-normalized variant into the ML-ready shape.

    Target for THIS model (differs from the notebook only here):
      1. Prefer case["disposal_duration_days"] when the source provides it.
      2. Fall back to (disposal_date - filing_date).days if it is missing.
    """
    container = _extract_container(record, schema_type)
    case = container.get("case", {})
    timeline = container.get("case_timeline", [])
    acts = container.get("acts_and_sections", [])

    case_status = case.get("case_status", "") or ""
    ddur = case.get("disposal_duration_days")
    nature = case.get("nature_of_disposal")
    is_disposed = ("dispos" in case_status.lower()) or (ddur is not None) or bool(nature)

    disposal_date = case.get("disposal_date")
    if is_disposed and not disposal_date and timeline:
        # notebook fallback: first timeline entry marks the disposal hearing
        disposal_date = timeline[0].get("hearing_date") or timeline[0].get("business_on_date")

    filing_date = case.get("filing_date")

    days_to_disposal = None
    if is_disposed:
        if ddur is not None:
            # PREFERRED: source provides the duration directly
            try:
                days_to_disposal = int(ddur)
            except (TypeError, ValueError):
                days_to_disposal = None
        elif disposal_date and filing_date:
            # FALLBACK: derive from dates (used once, then both dates are dropped)
            try:
                days_to_disposal = (
                    pd.to_datetime(disposal_date, errors="coerce")
                    - pd.to_datetime(filing_date, errors="coerce")
                ).days
            except Exception:
                days_to_disposal = None
            if days_to_disposal is not None and np.isnan(days_to_disposal):
                days_to_disposal = None

    case_id = record.get("case_id") or case.get("cnr_number")

    return {
        "case_id": case_id,
        "case_type": case.get("case_type"),
        "court_id": case.get("court_id"),
        "court_id_source": f"FROM_{schema_type.upper()}",
        "court_name": case.get("court_name"),
        "court_type": None,
        "district": case.get("court_district"),
        "state": case.get("court_state"),
        "filing_date": filing_date,
        "registration_date": case.get("registration_date"),
        "first_hearing_date": case.get("first_hearing_date"),
        "next_hearing_date": case.get("next_hearing_date"),
        "current_status": case.get("current_case_stage"),
        "disposal_date": disposal_date,
        "days_to_disposal": days_to_disposal,
        "target_available": bool(is_disposed and days_to_disposal is not None),
        "number_of_hearings": case.get("number_of_hearings"),
        "total_hearings": case.get("total_hearings"),
        "average_hearing_gap_days": case.get("average_hearing_gap_days"),
        "judge_position": case.get("presiding_judge"),
        "data_source": schema_type.upper(),
        "source_record_identifier": (
            record.get("source", {}).get("source_record_identifier") or case_id
        ),
    }


# =====================================================================
# Artifact helpers
# =====================================================================

def clear_stale_disposal_artifacts():
    """Guarantee no stale disposal model can serve predictions after a skip."""
    removed = []
    for name in ARTIFACT_NAMES:
        p = MODELS_DIR / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return removed


def descriptive_stats_and_stop(disposed):
    values = disposed["days_to_disposal"].astype(float)
    log("=" * 70)
    log("!!  WARNING: INSUFFICIENT TRAINING DATA")
    log(f"!!  Only {len(values)} usable disposed cases were found, but at least")
    log(f"!!  {MIN_USABLE_CASES} are required to train a reliable model.")
    log("!!  TRAINING SKIPPED — results would not be reliable.")
    log("=" * 70)
    log()
    log("Descriptive statistics for days_to_disposal (no model trained):")
    log(f"  count : {int(values.count())}")
    log(f"  mean  : {values.mean():.2f} days")
    log(f"  median: {values.median():.2f} days")
    log(f"  min   : {values.min():.2f} days")
    log(f"  max   : {values.max():.2f} days")
    log(f"  std   : {values.std():.2f} days")
    log()
    removed = clear_stale_disposal_artifacts()
    if removed:
        log(f"Removed stale disposal artifacts so the API returns null: {removed}")
    joblib.dump(
        {
            "trained": False,
            "reason": f"fewer than {MIN_USABLE_CASES} usable disposed cases",
            "usable_cases": int(len(values)),
        },
        MODELS_DIR / "disposal_model_status.pkl",
    )
    log("Saved models/disposal_model_status.pkl (trained=False).")
    log("API behaviour: /predict-delay will return predicted_disposal_days = null.")


# =====================================================================
# Main pipeline
# =====================================================================

def main():
    log("=" * 70)
    log("NyayMitra — Days-to-Disposal model training")
    log("=" * 70)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # STEP 1 — load + normalize every file (notebook logic)
    # ------------------------------------------------------------------
    log()
    log("[1/8] Loading and normalizing files (normalize_raw_scrape / normalize_ml_ready)")
    log(f"  data dir A: {RAW_DATA_DIR}")
    log(f"  data dir B: {DISPOSAL_DATA_DIR}")

    all_files = []
    for d in (RAW_DATA_DIR, DISPOSAL_DATA_DIR):
        if d.exists():
            all_files.extend(sorted(d.rglob("*.json")))
            all_files.extend(sorted(d.rglob("*.jsonl")))
        else:
            log(f"  WARNING: missing data dir: {d}")

    all_normalized = []
    unknown_records = []
    schema_counts = {"ml_ready": 0, "raw_normalized_wrapped": 0, "raw_normalized_flat": 0, "unknown": 0}
    files_by_dir = {}

    for filepath in all_files:
        rel = filepath.relative_to(ROOT)
        top_dir = str(rel.parent).split("\\")[0] + "/" + str(rel.parent).split("\\")[1] if len(rel.parent.parts) > 1 else str(rel.parent)
        files_by_dir.setdefault(top_dir, {"files": 0, "records": 0})
        files_by_dir[top_dir]["files"] += 1
        try:
            records = load_any_file(filepath)
        except Exception as e:
            log(f"  SKIP unreadable file {rel}: {e}")
            continue
        files_by_dir[top_dir]["records"] += len(records)
        for r in records:
            if not isinstance(r, dict):
                continue
            schema = detect_schema(r)
            schema_counts[schema] += 1
            if schema == "ml_ready":
                all_normalized.append(normalize_ml_ready(r))
            elif schema in ("raw_normalized_wrapped", "raw_normalized_flat"):
                all_normalized.append(normalize_raw_scrape(r, schema))
            else:
                unknown_records.append((str(rel), r))

    log()
    log("  Files scanned per source:")
    for d, c in files_by_dir.items():
        log(f"    {d:<45} {c['files']:>4} files, {c['records']:>4} records")
    log(f"  Total files scanned : {len(all_files)}")
    log(f"  Total records read  : {sum(schema_counts.values())}")
    log("  Schema detection:")
    log(f"    ml_ready               : {schema_counts['ml_ready']}")
    log(f"    raw_normalized_wrapped : {schema_counts['raw_normalized_wrapped']}")
    log(f"    raw_normalized_flat    : {schema_counts['raw_normalized_flat']}")
    log(f"    unknown (skipped, same as notebook): {schema_counts['unknown']}")
    if unknown_records:
        unknown_files = sorted({f for f, _ in unknown_records})
        log(f"  Unrecognized-schema files ({len(unknown_files)}):")
        for f in unknown_files:
            log(f"    - {f}")

    # ------------------------------------------------------------------
    # Combine + dedupe (notebook cell 4)
    # ------------------------------------------------------------------
    log()
    log("[2/8] Combining into one table")
    df = pd.json_normalize(all_normalized, sep="_")
    before = len(df)
    if "case_id" in df.columns:
        df = df.drop_duplicates(subset="case_id", keep="first")
    after = len(df)
    log(f"  {before} rows -> removed {before - after} duplicate case_ids -> {after} unique cases")

    # Safety pass: derive any missing target from dates (only for disposed rows)
    if "days_to_disposal" not in df.columns:
        df["days_to_disposal"] = np.nan
    df["days_to_disposal"] = pd.to_numeric(df["days_to_disposal"], errors="coerce")
    pending_dates = (
        df["days_to_disposal"].isna()
        & df.get("target_available", pd.Series(False, index=df.index)).fillna(False).astype(bool)
        & df.get("filing_date", pd.Series(pd.NaT, index=df.index)).notna()
        & df.get("disposal_date", pd.Series(pd.NaT, index=df.index)).notna()
    )
    if pending_dates.any():
        df.loc[pending_dates, "days_to_disposal"] = (
            pd.to_datetime(df.loc[pending_dates, "disposal_date"], errors="coerce")
            - pd.to_datetime(df.loc[pending_dates, "filing_date"], errors="coerce")
        ).dt.days
        log(f"  Derived missing targets from (disposal_date - filing_date) for {int(pending_dates.sum())} cases")

    # ------------------------------------------------------------------
    # STEP 2 — disposed cases only
    # ------------------------------------------------------------------
    log()
    log("[3/8] Filtering to disposed cases (target_available == True)")
    ta = df.get("target_available", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    n_pending = int((~ta).sum())
    disposed = df[ta].copy()
    log(f"  Disposed cases (target_available == True): {len(disposed)}")
    log(f"  Pending cases (no disposal target)       : {n_pending}")

    n_missing_target = int(disposed["days_to_disposal"].isna().sum())
    disposed = disposed[disposed["days_to_disposal"].notna()]
    disposed["days_to_disposal"] = disposed["days_to_disposal"].astype(float)
    n_negative = int((disposed["days_to_disposal"] < 0).sum())
    if n_negative:
        log(f"  Dropped {n_negative} rows with negative days (data errors)")
        disposed = disposed[disposed["days_to_disposal"] >= 0]
    if n_missing_target:
        log(f"  Dropped {n_missing_target} disposed rows with no computable target")

    usable = len(disposed)
    log()
    log(f"  ==> USABLE DISPOSED CASES: {usable} <==")

    if usable:
        v = disposed["days_to_disposal"]
        log()
        log("  days_to_disposal overview (always reported):")
        log(f"    mean={v.mean():.2f}  median={v.median():.2f}  min={v.min():.2f}  "
            f"max={v.max():.2f}  std={v.std():.2f}")

    # ------------------------------------------------------------------
    # STEP 4 — minimum-sample gate
    # ------------------------------------------------------------------
    if usable < MIN_USABLE_CASES:
        log()
        descriptive_stats_and_stop(disposed)
        return

    # ------------------------------------------------------------------
    # STEP 5 — feature engineering
    # ------------------------------------------------------------------
    log()
    log("[4/8] Leakage guard — dropping date columns before training")
    present_cats = [c for c in CATEGORICAL_COLS if c in disposed.columns]
    present_numeric = [
        c for c in NUMERIC_CANDIDATES
        if c in disposed.columns and disposed[c].notna().any()
    ]
    log(f"  Categorical features (one-hot): {present_cats}")
    log(f"  Numeric features              : {present_numeric}")

    # Explicit column selection: filing_date / disposal_date are used ONLY to
    # compute the target above and are NOT carried into the feature frame.
    keep_cols = present_cats + present_numeric + ["days_to_disposal"]
    if "case_id" in disposed.columns:
        keep_cols.append("case_id")
    model_df = disposed[keep_cols].copy()
    leaked = [c for c in LEAKAGE_COLS if c in model_df.columns and c != "days_to_disposal"]
    assert not leaked, f"LEAKAGE: date columns present in feature frame: {leaked}"
    log("  Confirmed: filing_date, disposal_date, disposal_duration_days are NOT features.")

    log()
    log("[5/8] Feature engineering")
    for c in present_cats:
        model_df[c] = model_df[c].fillna("Unknown").astype(str)
    numeric_defaults = {}
    for c in present_numeric:
        model_df[c] = pd.to_numeric(model_df[c], errors="coerce")
        med = float(model_df[c].median())
        n_fill = int(model_df[c].isna().sum())
        if n_fill:
            model_df[c] = model_df[c].fillna(med)
        numeric_defaults[c] = med
        log(f"  {c}: filled {n_fill} missing with training median {med:.2f}")

    # Historical pace features — computed EXACTLY like the next-hearing model
    # (groupby mean of the target, notebook cell 9)
    model_df["case_type_historical_pace"] = model_df.groupby("case_type")["days_to_disposal"].transform("mean")
    model_df["court_historical_pace"] = model_df.groupby("court_name")["days_to_disposal"].transform("mean")
    log(f"  case_type_historical_pace coverage: {model_df['case_type_historical_pace'].notna().sum()}/{len(model_df)}")
    log(f"  court_historical_pace coverage    : {model_df['court_historical_pace'].notna().sum()}/{len(model_df)}")

    model_df_encoded = pd.get_dummies(model_df, columns=present_cats, drop_first=True)
    log(f"  Encoded feature matrix shape: {model_df_encoded.shape}")

    # ------------------------------------------------------------------
    # STEP 6 — split, winsorize the TRAINING target, train both models
    # ------------------------------------------------------------------
    log()
    log("[6/8] Train/test split (80/20), target winsorization, model training")
    drop_cols = [c for c in ["case_id", "days_to_disposal"] if c in model_df_encoded.columns]
    X = model_df_encoded.drop(columns=drop_cols)
    y = model_df_encoded["days_to_disposal"]  # UNCAPPED raw target, never modified

    leaked_in_X = [c for c in LEAKAGE_COLS if c in X.columns]
    assert not leaked_in_X, f"LEAKAGE: {leaked_in_X} found in final feature matrix X"
    log(f"  X shape: {X.shape}   y shape: {y.shape}")
    log(f"  Final feature columns ({len(X.columns)}): {X.columns.tolist()}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_STATE
    )
    log(f"  Training rows: {X_train.shape[0]}   Test rows: {X_test.shape[0]}")
    log("  NOTE: y_test stays UNCAPPED for scoring/reporting; only the training")
    log("        target is winsorized. Raw stored data is never modified.")

    def _new_rf():
        return RandomForestRegressor(n_estimators=200, random_state=RANDOM_STATE, n_jobs=2)

    def _new_xgb():
        return xgb.XGBRegressor(
            n_estimators=300,
            max_depth=5,
            learning_rate=0.08,
            random_state=RANDOM_STATE,
            objective="reg:squarederror",
            n_jobs=2,
        )

    def _fit_score(estimator, fit_target):
        """Fit on the given target, score against the UNCAPPED y_test."""
        estimator.fit(X_train, fit_target)
        preds = estimator.predict(X_test)
        mae = mean_absolute_error(y_test, preds)
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))
        return estimator, preds, mae, rmse

    # --- 6a: UNCAPPED control run (reporting only — never saved) ------------
    log()
    log("  [a] Uncapped baseline control run (same seed/split, reporting only):")
    prev_status = None
    status_path = MODELS_DIR / "disposal_model_status.pkl"
    if status_path.exists():
        try:
            prev_status = joblib.load(status_path)
        except Exception:
            prev_status = None
    if prev_status and prev_status.get("trained") and "xgb_mae" in prev_status:
        log(f"      previously stored run : RF MAE {prev_status['rf_mae']:.2f} | "
            f"XGB MAE {prev_status['xgb_mae']:.2f}")

    rf_base_obj, rf_base_preds, rf_base_mae, rf_base_rmse = _fit_score(_new_rf(), y_train)
    xgb_base_obj, xgb_base_preds, xgb_base_mae, xgb_base_rmse = _fit_score(_new_xgb(), y_train)
    log(f"      Random Forest : MAE {rf_base_mae:.2f} days | RMSE {rf_base_rmse:.2f} days")
    log(f"      XGBoost       : MAE {xgb_base_mae:.2f} days | RMSE {xgb_base_rmse:.2f} days")
    del rf_base_obj, xgb_base_obj, rf_base_preds, xgb_base_preds  # free RAM

    # --- 6b: winsorize the TRAINING target at its 95th percentile ----------
    TARGET_PERCENTILE = 95
    target_cap = float(y_train.quantile(TARGET_PERCENTILE / 100.0))  # TRAIN split only
    y_train_capped = y_train.clip(upper=target_cap)
    n_capped = int((y_train > target_cap).sum())
    log()
    log(f"  [b] Winsorizing TRAINING target at the {TARGET_PERCENTILE}th percentile "
        f"(computed from the training split only — no leakage):")
    log(f"      cap value = {target_cap:.2f} days")
    log(f"      training rows capped: {n_capped}/{len(y_train)}")
    log(f"      train target uncapped : mean={y_train.mean():.2f}  median={y_train.median():.2f}  "
        f"min={y_train.min():.2f}  max={y_train.max():.2f}  std={y_train.std():.2f}")
    log(f"      train target capped   : mean={y_train_capped.mean():.2f}  median={y_train_capped.median():.2f}  "
        f"min={y_train_capped.min():.2f}  max={y_train_capped.max():.2f}  std={y_train_capped.std():.2f}")
    n_test_above = int((y_test > target_cap).sum())
    log(f"      test target left UNCAPPED (max={y_test.max():.2f}); rows above cap: "
        f"{n_test_above}/{len(y_test)}")

    # --- 6c: train both models on the CAPPED target ------------------------
    log()
    log("  [c] Winsorized training (fit on capped target, scored on uncapped y_test):")
    rf_model, rf_preds, rf_mae, rf_rmse = _fit_score(_new_rf(), y_train_capped)
    xgb_model, xgb_preds, xgb_mae, xgb_rmse = _fit_score(_new_xgb(), y_train_capped)
    log(f"      Random Forest : MAE {rf_mae:.2f} days | RMSE {rf_rmse:.2f} days")
    log(f"      XGBoost       : MAE {xgb_mae:.2f} days | RMSE {xgb_rmse:.2f} days")

    # --- 6d: winsorized vs uncapped baseline -------------------------------
    log()
    log("  [d] Comparison vs uncapped baseline (same split, same seed, uncapped y_test):")
    log(f"      {'model':<16}{'MAE base':>12}{'MAE capped':>13}{'RMSE base':>13}{'RMSE capped':>14}")
    log(f"      {'Random Forest':<16}{rf_base_mae:>12.2f}{rf_mae:>13.2f}{rf_base_rmse:>13.2f}{rf_rmse:>14.2f}")
    log(f"      {'XGBoost':<16}{xgb_base_mae:>12.2f}{xgb_mae:>13.2f}{xgb_base_rmse:>13.2f}{xgb_rmse:>14.2f}")

    # Deploy the lower-MAE model among the WINSORIZED candidates
    if xgb_mae <= rf_mae:
        final_model, final_model_name = xgb_model, "xgboost"
        final_mae, final_rmse = xgb_mae, xgb_rmse
        log(f"      Winner: XGBoost (MAE {xgb_mae:.2f} vs RF {rf_mae:.2f}) — winsorized target")
    else:
        final_model, final_model_name = rf_model, "random_forest"
        final_mae, final_rmse = rf_mae, rf_rmse
        log(f"      Winner: Random Forest (MAE {rf_mae:.2f} vs XGBoost {xgb_mae:.2f}) — winsorized target")

    final_preds = final_model.predict(X_test)
    residuals = y_test.values - final_preds  # residuals vs UNCAPPED truth
    resid_std = float(residuals.std())
    log(f"      Residual std dev (confidence width): {resid_std:.2f} days")

    # ------------------------------------------------------------------
    # STEP 7 — SHAP explainability (same top-3 format as delay_predictor)
    # ------------------------------------------------------------------
    log()
    log("[7/8] SHAP explainability (top-3 sample, same format as delay_predictor.py)")
    explainer = shap.TreeExplainer(final_model)
    row_2d = X_test.iloc[[0]].values
    shap_vals = explainer.shap_values(row_2d)
    if isinstance(shap_vals, list):
        shap_vals = shap_vals[0]
    shap_vals = shap_vals[0] if getattr(shap_vals, "ndim", 1) > 1 else shap_vals

    contributions = list(zip(X.columns.tolist(), shap_vals))
    contributions.sort(key=lambda x: abs(x[1]), reverse=True)
    for feat, val in contributions[:3]:
        direction = "increased" if val > 0 else "decreased"
        clean_name = feat.replace("_", " ")
        log(f"  - {clean_name} {direction} the estimate by about {abs(round(val))} days")

    # ------------------------------------------------------------------
    # STEP 8 — save artifacts with "_disposal" suffix
    # ------------------------------------------------------------------
    log()
    log("[8/8] Saving model + lookup artifacts to models/ (with _disposal suffix)")
    if final_model_name == "xgboost":
        final_model.save_model(str(MODELS_DIR / "delay_disposal_model.json"))
        log("  saved delay_disposal_model.json")
    else:
        joblib.dump(final_model, MODELS_DIR / "delay_disposal_model.pkl")
        log("  saved delay_disposal_model.pkl")

    feature_columns = X.columns.tolist()
    case_type_pace_lookup = model_df.groupby("case_type")["days_to_disposal"].mean().to_dict()
    court_pace_lookup = model_df.groupby("court_name")["days_to_disposal"].mean().to_dict()
    overall_mean_pace = float(model_df["days_to_disposal"].mean())

    joblib.dump(final_model_name, MODELS_DIR / "model_type_disposal.pkl")
    joblib.dump(feature_columns, MODELS_DIR / "feature_columns_disposal.pkl")
    joblib.dump(case_type_pace_lookup, MODELS_DIR / "case_type_pace_lookup_disposal.pkl")
    joblib.dump(court_pace_lookup, MODELS_DIR / "court_pace_lookup_disposal.pkl")
    joblib.dump(overall_mean_pace, MODELS_DIR / "overall_mean_pace_disposal.pkl")
    joblib.dump(resid_std, MODELS_DIR / "resid_std_disposal.pkl")
    joblib.dump(numeric_defaults, MODELS_DIR / "numeric_defaults_disposal.pkl")

    # Winsorization bookkeeping: the cap scalar + a full report that keeps the
    # UNCAPPED days_to_disposal values available for reporting/documentation
    # (raw stored data was never modified — only the training target was capped).
    joblib.dump(target_cap, MODELS_DIR / "target_cap_disposal.pkl")

    raw_target_stats = {
        "count": int(y.count()),
        "mean": float(y.mean()),
        "median": float(y.median()),
        "min": float(y.min()),
        "max": float(y.max()),
        "std": float(y.std()),
    }
    capped_train_stats = {
        "count": int(y_train_capped.count()),
        "mean": float(y_train_capped.mean()),
        "median": float(y_train_capped.median()),
        "min": float(y_train_capped.min()),
        "max": float(y_train_capped.max()),
        "std": float(y_train_capped.std()),
    }
    joblib.dump(
        {
            "note": (
                "UNCAPPED days_to_disposal kept for reporting/documentation. "
                "Only the model's training target was winsorized at the "
                f"{TARGET_PERCENTILE}th percentile of the training split; "
                "raw source data was not modified."
            ),
            "target_cap_days": target_cap,
            "target_cap_percentile": TARGET_PERCENTILE,
            "target_cap_computed_from": f"training split only (80/20, random_state={RANDOM_STATE})",
            "training_rows_capped": n_capped,
            "test_rows_above_cap": n_test_above,
            "uncapped_values": [float(v) for v in y.tolist()],
            "uncapped_stats": raw_target_stats,
            "capped_train_stats": capped_train_stats,
            "metrics_vs_uncapped_test": {
                "baseline_random_forest": {"mae": float(rf_base_mae), "rmse": float(rf_base_rmse)},
                "baseline_xgboost": {"mae": float(xgb_base_mae), "rmse": float(xgb_base_rmse)},
                "winsorized_random_forest": {"mae": float(rf_mae), "rmse": float(rf_rmse)},
                "winsorized_xgboost": {"mae": float(xgb_mae), "rmse": float(xgb_rmse)},
            },
        },
        MODELS_DIR / "target_report_disposal.pkl",
    )

    joblib.dump(
        {
            "trained": True,
            "model_type": final_model_name,
            "usable_cases": int(usable),
            "train_rows": int(X_train.shape[0]),
            "test_rows": int(X_test.shape[0]),
            "target_winsorized": True,
            "target_cap_percentile": TARGET_PERCENTILE,
            "target_cap_days": float(target_cap),
            "target_cap_computed_from": "training split only",
            "train_rows_capped": n_capped,
            "raw_target_stats": raw_target_stats,  # uncapped — documentation only
            "rf_mae": float(rf_mae),               # winsorized models (deployment)
            "rf_rmse": float(rf_rmse),
            "xgb_mae": float(xgb_mae),
            "xgb_rmse": float(xgb_rmse),
            "baseline_rf_mae": float(rf_base_mae),  # uncapped control run
            "baseline_rf_rmse": float(rf_base_rmse),
            "baseline_xgb_mae": float(xgb_base_mae),
            "baseline_xgb_rmse": float(xgb_base_rmse),
            "resid_std": resid_std,
        },
        MODELS_DIR / "disposal_model_status.pkl",
    )
    log("  saved model_type_disposal.pkl, feature_columns_disposal.pkl,")
    log("       case_type_pace_lookup_disposal.pkl, court_pace_lookup_disposal.pkl,")
    log("       overall_mean_pace_disposal.pkl, resid_std_disposal.pkl,")
    log("       numeric_defaults_disposal.pkl, disposal_model_status.pkl,")
    log("       target_cap_disposal.pkl, target_report_disposal.pkl")
    log("       (target_report_disposal.pkl holds the UNCAPPED days_to_disposal")
    log("        values + stats for reporting/documentation)")

    # Sanity: next-hearing artifacts untouched
    untouched = [
        n for n in [
            "delay_next_hearing_model.pkl", "model_type.pkl", "feature_columns.pkl",
            "case_type_pace_lookup.pkl", "court_pace_lookup.pkl",
            "overall_mean_pace.pkl", "resid_std.pkl",
        ] if (MODELS_DIR / n).exists()
    ]
    log(f"  next-hearing model files left untouched: {untouched}")

    log()
    log("=" * 70)
    log(f"TRAINING COMPLETED — disposal model trained on {usable} disposed cases.")
    log(f"  Target winsorized at p{TARGET_PERCENTILE}(training split) = {target_cap:.2f} days "
        f"({n_capped}/{len(y_train)} training rows capped)")
    log(f"  Winner: {final_model_name} | MAE {final_mae:.2f} days | RMSE {final_rmse:.2f} days")
    log(f"  Uncapped baseline (this run, same split): RF MAE {rf_base_mae:.2f} | "
        f"XGB MAE {xgb_base_mae:.2f}")
    log("  Uncapped raw values preserved in models/target_report_disposal.pkl")
    log("  API: /predict-delay will now return predicted_disposal_days (real value).")
    log("=" * 70)


if __name__ == "__main__":
    sys.exit(main())

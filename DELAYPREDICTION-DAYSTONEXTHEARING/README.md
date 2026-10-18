# Delay Prediction — Days to Next Hearing

ML model that predicts the number of days until the next hearing for court cases.

## Contents

| Path | Description |
|------|-------------|
| `notebooks/04_model_building.ipynb` | Model building & training notebook |
| `models/delay_next_hearing_model.pkl` | Trained primary model |
| `models/feature_columns.pkl` | Feature column order used at inference |
| `models/model_type.pkl` | Model type metadata |
| `models/court_pace_lookup.pkl` | Per-court pace lookup table |
| `models/case_type_pace_lookup.pkl` | Per-case-type pace lookup table |
| `models/overall_mean_pace.pkl` | Overall mean pace fallback |
| `models/resid_std.pkl` | Residual standard deviation (prediction intervals) |
| `src/delay_predictor.py` | Inference loader / prediction helper |
| `src/api.py` | API exposing the predictor |
| `requirements.txt` | Python dependencies |

## Usage

```bash
pip install -r requirements.txt
python src/api.py
```

## Model artifacts

All `.pkl` files must be kept together — `delay_predictor.py` loads them as a set.

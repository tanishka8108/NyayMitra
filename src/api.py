
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from delay_predictor import predict_delay, predict_disposal

# "Tell Us What Happened" ML layer (intent / category / facts / missing info).
# Imported defensively so a failure in that feature can never take down the
# existing /predict-delay endpoint. Importing it also loads the JSON data and
# the cached embedding matrices; warm_up() below finishes the job by loading
# the sentence-transformers encoder, so no model is loaded on a request.
try:
    from incident_pipeline import process_user_input, warm_up
except Exception as _tuwah_error:  # pragma: no cover - defensive
    process_user_input = None
    warm_up = None
    print(f"Situation-understanding module unavailable: {_tuwah_error}")


def _load_situation_models() -> None:
    """API startup hook: pre-load the intent + incident models and embeddings.

    Runs once when uvicorn starts the app, never during a request, so the
    first /understand-situation call responds immediately. Any failure here
    is logged only - /predict-delay must keep working, and
    /understand-situation still works (just slower) or returns 503.
    """
    if warm_up is None:
        print("Situation-understanding module unavailable: endpoint returns 503.")
        return
    try:
        print(f"Situation-understanding models loaded at startup: {warm_up()}")
    except Exception as _warmup_error:  # pragma: no cover - defensive
        print(f"Could not pre-load situation-understanding models: {_warmup_error}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _load_situation_models()
    yield


app = FastAPI(title="NyayMitra Delay Prediction Service", lifespan=lifespan)

# Browsers refuse a cross-origin call unless the API says which origin
# may make it, so the Vite dev server needs this to reach either endpoint.
#
# Exact origins only - never "*". The list must match the origin the
# frontend is actually served from (Vite, port 5173; see README). Adding
# "*" would let any website on the internet read these predictions using
# the visitor's own network, so it is deliberately not used here.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

class CaseInput(BaseModel):
    case_type: str
    court: str
    district: str
    state: str


@app.post("/predict-delay")
@limiter.limit("30/minute")
def predict_delay_endpoint(request: Request, case: CaseInput):
    try:
        result = predict_delay(case.case_type, case.court, case.district, case.state)
    except Exception as e:
        print(f"Internal error: {e}")
        return JSONResponse(status_code=500, content={"error": "Could not generate a prediction for this case."})

    # Both models feed the same "Delay Prediction" action card, so return both
    # predictions in one response.
    result["predicted_next_hearing_days"] = result.get("predicted_delay_days")

    try:
        disposal = predict_disposal(case.case_type, case.court, case.district, case.state)
    except Exception as e:
        # A disposal-model failure must never take down the next-hearing prediction.
        print(f"Disposal prediction error: {e}")
        disposal = None

    if disposal is None:
        # Model not trained (fewer than 25 usable disposed cases).
        result["predicted_disposal_days"] = None
        result["disposal_model_status"] = "not_trained"
    else:
        result["predicted_disposal_days"] = disposal["predicted_disposal_days"]
        result["disposal_model_status"] = "trained"
        result["disposal_explanation"] = disposal["explanation"]
        result["disposal_confidence_label"] = disposal["confidence_label"]
        result["disposal_model_version"] = disposal["model_version"]

    return result


@app.get("/health")
def health():
    return {"status": "ok"}


# =====================================================================
# "Tell Us What Happened" - intent / incident understanding endpoint.
# Kept separate from /predict-delay: this is the ML layer that turns free
# text into structured JSON (intent, incident_category, facts, missing
# information) for the NLP / legal-explanation layer.
# =====================================================================

class SituationInput(BaseModel):
    text: str


@app.post("/understand-situation")
@limiter.limit("30/minute")
def understand_situation_endpoint(request: Request, payload: SituationInput):
    if process_user_input is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Situation understanding is not available right now."},
        )

    try:
        return process_user_input(payload.text)
    except ValueError as e:
        # Empty / non-usable input -> client error, not a crash.
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        print(f"Internal error in /understand-situation: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Could not understand this input."},
        )

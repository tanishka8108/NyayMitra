
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from delay_predictor import predict_delay

app = FastAPI(title="NyayMitra Delay Prediction Service")

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
        return result
    except Exception as e:
        print(f"Internal error: {e}")
        return JSONResponse(status_code=500, content={"error": "Could not generate a prediction for this case."})


@app.get("/health")
def health():
    return {"status": "ok"}

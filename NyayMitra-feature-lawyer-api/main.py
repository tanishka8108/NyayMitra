import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from auth.routes import router as auth_router
from cases.routes import router as cases_router
from cases.saved_routes import router as saved_cases_router
from chat.routes import router as chat_router
from lawyer.routes import router as lawyer_router
from lawyer.admin_routes import router as admin_router
from lawyer.practice_area_routes import practice_area_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("nyaymitra.api")

app = FastAPI(
    title="NyayMitra API",
    description="Backend API for the NyayMitra application",
    version="1.0.0",
)


# =========================================================
# CORS
# =========================================================

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# ROUTERS
# =========================================================

# Authentication (users, sessions, roles) — SQLite-backed; the schema
# in database/auth_schema.sql is applied lazily on first use.
app.include_router(auth_router)

app.include_router(lawyer_router)

# ADMIN-only lawyer verification (Phase 2). The Admin Dashboard UI
# is a teammate's; this is the API contract it talks to.
app.include_router(admin_router)

app.include_router(practice_area_router)
app.include_router(cases_router)

# Server-side My Cases (save / list / remove by CNR) — SQLite-backed
# like auth and chat. The browser's own saved rows in
# frontend/src/api/caseApi.ts are left untouched; see
# cases/saved_routes.py for why both exist.
app.include_router(saved_cases_router)

# USER ↔ LAWYER chat (Phase 3) — SQLite-backed conversations/messages,
# guarded by the same session/verification rules as everything else.
app.include_router(chat_router)


# =========================================================
# ERROR HANDLING
#
# An unexpected failure must not hand a caller a Python stack
# trace: it can expose file paths, configuration and query
# text. The traceback is logged server-side (that is where it
# is useful) and the client gets a short, stable message.
# =========================================================

@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):  # noqa: ANN001
    logger.exception(
        "unhandled error on %s %s: %r",
        request.method,
        request.url.path,
        exc,
    )

    # This handler runs in Starlette's ServerErrorMiddleware, which
    # sits OUTSIDE CORSMiddleware — a 500 it returns would carry no
    # Access-Control-Allow-Origin header, the browser would refuse to
    # hand it to the frontend, and every unexpected failure would
    # surface as a bare "Failed to fetch" instead of the real error.
    # Attach the same CORS decision the middleware would have made
    # for allowed origins. Successful and HTTPException responses
    # already get their headers from CORSMiddleware.
    headers = {}
    origin = request.headers.get("origin")
    if origin in ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"

    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "Something went wrong on the server. Please try again."
            )
        },
        headers=headers,
    )


# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {
        "message": "NyayMitra API is running"
    }

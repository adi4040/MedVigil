from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.api.v1.audit import router as audit_router
from app.api.v1.health import router as health_router
from app.core.config import settings

DEMO_HTML_PATH = Path(__file__).resolve().parent / "static" / "demo.html"



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions (e.g., connect DB pool)
    yield
    # Shutdown actions (e.g., close connections)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(health_router, prefix=settings.API_V1_PREFIX, tags=["Health"])
app.include_router(audit_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}. Visit /docs for API documentation or /demo for interactive audit streaming."
    }


@app.get(
    "/demo",
    response_class=HTMLResponse,
    summary="Interactive Streaming Clinical Audit Demo",
    tags=["Demo"],
)
def demo_page():
    if not DEMO_HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Demo page not found.")
    return HTMLResponse(content=DEMO_HTML_PATH.read_text(encoding="utf-8"))

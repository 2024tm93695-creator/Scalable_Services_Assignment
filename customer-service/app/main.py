"""Customer Service - FastAPI Application"""
import time, json, re, logging, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response
from app.db import engine, Base
from app.routers import customers, kyc
from app.metrics import REQUEST_COUNT, REQUEST_DURATION

# ── JSON logger with PII masking ───────────────────────────────────────────
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_RE = re.compile(r"\b\d{10}\b")

def mask(text: str) -> str:
    text = EMAIL_RE.sub(lambda m: m.group()[:2] + "****" + m.group()[m.group().index("@"):], text)
    text = PHONE_RE.sub(lambda m: m.group()[:2] + "****" + m.group()[-4:], text)
    return text

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "service": "customer-svc",
            "correlationId": getattr(record, "correlation_id", "-"),
            "path": getattr(record, "path", "-"),
            "latency_ms": getattr(record, "latency_ms", 0),
            "message": mask(record.getMessage()),
        })

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.basicConfig(handlers=[handler], level=logging.INFO)
logger = logging.getLogger("customer-svc")

# ── App lifecycle ──────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title="Customer Service",
    version="1.0.0",
    description=(
        "Manages customer profiles and KYC (Know Your Customer) lifecycle.\n\n"
        "**Events published (RabbitMQ `banking.events` exchange)**\n"
        "- `banking.KYCStatusUpdated` — emitted whenever a customer's KYC state changes\n\n"
        "**Consumed by:** account-svc, notification-svc"
    ),
    contact={"name": "Banking Platform Team"},
    openapi_tags=[
        {"name": "Customers", "description": "Create, read, update, and delete customer records."},
        {"name": "KYC",       "description": "Manage KYC state transitions (PENDING → VERIFIED | REJECTED)."},
    ],
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(customers.router, prefix="/api/v1")
app.include_router(kyc.router, prefix="/api/v1")

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_COUNT.labels("customer-svc", request.method, request.url.path, response.status_code).inc()
    REQUEST_DURATION.labels("customer-svc", request.method, request.url.path).observe(duration)
    logger.info("Request handled", extra={
        "path": request.url.path,
        "latency_ms": round(duration * 1000),
        "correlation_id": correlation_id,
    })
    response.headers["X-Correlation-ID"] = correlation_id
    return response

@app.get("/api/v1/health")
async def health():
    return {"status": "healthy", "service": "customer-svc", "version": "1.0.0"}

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Customer Service

Manages customer profiles and KYC (Know Your Customer) lifecycle for the Banking Microservices Platform. It is the authoritative source of truth for customer identity — all other services resolve customer details by calling this service's REST API or by consuming its RabbitMQ events.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Tech Stack](#tech-stack)
3. [Project Structure](#project-structure)
4. [Prerequisites](#prerequisites)
5. [Getting Started](#getting-started)
   - [Option A — Docker Compose (recommended)](#option-a--docker-compose-recommended)
   - [Option B — Minikube](#option-b--minikube)
   - [Option C — Local (no Docker)](#option-c--local-no-docker)
6. [Environment Variables](#environment-variables)
7. [Database Schema](#database-schema)
8. [API Reference](#api-reference)
   - [Health Check](#health-check)
   - [Create Customer](#1-create-customer)
   - [Get Customer by ID](#2-get-customer-by-id)
   - [List Customers](#3-list-customers)
   - [Update Customer](#4-update-customer)
   - [Delete Customer](#5-delete-customer)
   - [Get KYC Status](#6-get-kyc-status)
   - [Update KYC Status](#7-update-kyc-status)
9. [Events Published](#events-published)
10. [Resilience](#resilience)
11. [Observability](#observability)
12. [Docker](#docker)
13. [Kubernetes](#kubernetes)
14. [Testing](#testing)
15. [Design Decisions](#design-decisions)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     Banking Microservices Platform              │
│                                                                 │
│  ┌──────────────┐   REST    ┌──────────────┐                   │
│  │  account-svc │──────────►│              │                   │
│  └──────────────┘           │  customer-   │                   │
│                             │    svc       │◄─── This service  │
│  ┌──────────────┐   REST    │  :8001       │                   │
│  │ notification │──────────►│              │                   │
│  │    -svc      │           └──────┬───────┘                   │
│  └──────────────┘                  │                           │
│         ▲                          │ KYCStatusUpdated           │
│         │         RabbitMQ         ▼                           │
│         └──────────────────── banking.events                   │
│                                (topic exchange)                │
│                                                                 │
│  customer-svc ──► customer-db (PostgreSQL :5432)               │
└─────────────────────────────────────────────────────────────────┘
```

**Responsibilities**
- Register and manage customer profiles (name, email, phone)
- Track KYC status: `PENDING` → `VERIFIED` or `REJECTED`
- Publish `KYCStatusUpdated` events to RabbitMQ when KYC state changes
- Expose REST endpoints consumed by `account-svc` and `notification-svc`

**What this service does NOT do**
- Manage bank accounts or balances (→ `account-svc`)
- Process transactions or transfers (→ `transaction-svc`)
- Send email/SMS notifications (→ `notification-svc`)

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Framework | FastAPI | 0.111.0 |
| ASGI Server | Uvicorn | 0.29.0 |
| ORM | SQLAlchemy (async) | 2.0.30 |
| DB Driver | asyncpg | 0.29.0 |
| Database | PostgreSQL | 15 |
| Validation | Pydantic v2 | 2.7.1 |
| Message Broker | aio-pika (RabbitMQ) | 9.4.1 |
| Metrics | prometheus-client | 0.20.0 |
| Retry Logic | tenacity | 8.3.0 |
| HTTP Client | httpx | 0.27.0 |
| Runtime | Python | 3.11 |

---

## Project Structure

```
customer-service/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, middleware, logging, lifespan
│   ├── metrics.py       # All Prometheus metric definitions
│   ├── models.py        # SQLAlchemy ORM — Customer table
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── db.py            # Async engine, session factory
│   └── routers/
│       ├── __init__.py
│       ├── customers.py # CRUD endpoints
│       └── kyc.py       # KYC endpoints + RabbitMQ publisher
├── Dockerfile
├── requirements.txt
├── api-tests.http       # VS Code REST Client test file
├── test-customer-service.sh  # Shell test script (bash)
└── README.md
```

---

## Prerequisites

| Tool | Minimum version | Purpose |
|---|---|---|
| Docker Desktop | 24+ | Run via Docker Compose |
| Docker Compose | v2 | Orchestrate all services |
| Python | 3.11 | Local development |
| kubectl | 1.28+ | Kubernetes deployment |
| minikube | 1.32+ | Local Kubernetes cluster |
| VS Code + REST Client extension | — | Run `api-tests.http` |

---

## Getting Started

### Option A — Docker Compose (recommended)

This is the fastest way to run the full stack locally with seed data pre-loaded.

**1. Copy environment file and fill in passwords**

```bash
cd banking_project
cp .env.example .env
```

Edit `.env` and set real values for all `*_PASS` variables — these have no defaults and the service will fail to start without them.

**2. Start dependencies and customer service**

```bash
docker compose up -d customer-db rabbitmq customer-svc
```

Or start the full platform:

```bash
docker compose up -d
```

**3. Wait for health checks to pass (~15 seconds)**

```bash
docker compose ps
```

All three containers should show `healthy` or `running`:

```
NAME                          STATUS
banking_project-customer-db   Up (healthy)
banking_project-rabbitmq      Up (healthy)
banking_project-customer-svc  Up (healthy)
```

**4. Verify the service is up**

```bash
curl http://localhost:8001/api/v1/health
```

Expected response:

```json
{"status": "healthy", "service": "customer-svc", "version": "1.0.0"}
```

**5. Open the interactive API docs**

Navigate to `http://localhost:8001/docs` in your browser.

---

### Option B — Minikube

**1. Start Minikube and apply manifests**

```bash
minikube start
kubectl apply -f k8s/customer-service/deployment.yaml
```

**2. Wait for pods to be ready**

```bash
kubectl get pods -n banking -w
```

**3. Get the NodePort URL**

```bash
minikube service customer-svc -n banking --url
# Example output: http://127.0.0.1:61339
```

**4. Run the test script against Minikube**

```bash
bash customer-service/test-customer-service.sh http://127.0.0.1:61339
```

---

### Option C — Local (no Docker)

Use this when iterating quickly on code without rebuilding containers.

**1. Create and activate a virtual environment**

```bash
cd customer-service
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\Activate.ps1       # Windows PowerShell
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Set environment variables**

```bash
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost/customer_db"
export RABBITMQ_URL="amqp://guest:guest@localhost:5672/"
```

PostgreSQL and RabbitMQ must be running locally (or in Docker).

**4. Start the service with hot-reload**

```bash
uvicorn app.main:app --port 8001 --reload
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://postgres:postgres@localhost/customer_db` | Full async DSN for customer-db |
| `RABBITMQ_URL` | Yes | `amqp://guest:guest@localhost:5672/` | RabbitMQ connection string |
| `LOG_LEVEL` | No | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

> **Note:** In Docker Compose, `DATABASE_URL` and `RABBITMQ_URL` are constructed from individual `CUSTOMER_DB_USER`, `CUSTOMER_DB_PASS`, `RABBIT_USER`, and `RABBIT_PASS` variables defined in `.env`. Passwords have no fallback defaults — the service will not start without them.

---

## Database Schema

The service owns a single table in `customer_db`.

```sql
CREATE TABLE customers (
    customer_id  SERIAL          PRIMARY KEY,
    name         VARCHAR(100)    NOT NULL,
    email        VARCHAR(150)    UNIQUE NOT NULL,
    phone        VARCHAR(15)     NOT NULL,
    kyc_status   VARCHAR(20)     NOT NULL DEFAULT 'PENDING'
                 CONSTRAINT chk_kyc_status
                 CHECK (kyc_status IN ('PENDING', 'VERIFIED', 'REJECTED')),
    created_at   TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX idx_customers_email ON customers(email);
CREATE INDEX idx_customers_kyc   ON customers(kyc_status);
```

**Constraints**

| Constraint | Type | Detail |
|---|---|---|
| `customer_id` | PRIMARY KEY | Auto-incremented |
| `email` | UNIQUE | Enforced at DB level and app level (409 response) |
| `name`, `email`, `phone` | NOT NULL | Required fields |
| `kyc_status` | CHECK | Only `PENDING`, `VERIFIED`, `REJECTED` allowed |

**Seed data**

60 realistic customer records are auto-loaded on first container start from `seeds/seed_customers.sql`. Records include a mix of all three KYC statuses.

---

## API Reference

Base URL: `http://localhost:8001/api/v1`

Interactive docs: `http://localhost:8001/docs`

Raw OpenAPI spec: `http://localhost:8001/openapi.json`

---

### Health Check

```
GET /api/v1/health
```

**Response `200`**

```json
{
  "status": "healthy",
  "service": "customer-svc",
  "version": "1.0.0"
}
```

---

### 1. Create Customer

```
POST /api/v1/customers
```

**Request body**

```json
{
  "name": "Priya Sharma",
  "email": "priya.sharma@example.com",
  "phone": "9876543210",
  "kyc_status": "PENDING"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `name` | string | Yes | 1–100 characters |
| `email` | string | Yes | Valid email format, unique |
| `phone` | string | Yes | 10–15 characters |
| `kyc_status` | enum | No | `PENDING` (default), `VERIFIED`, `REJECTED` |

**Response `201 Created`**

```json
{
  "customer_id": 61,
  "name": "Priya Sharma",
  "email": "priya.sharma@example.com",
  "phone": "9876543210",
  "kyc_status": "PENDING",
  "created_at": "2026-05-02T10:15:30.123456+00:00"
}
```

**Error responses**

| Code | Condition |
|---|---|
| `409 Conflict` | Email already registered |
| `422 Unprocessable Entity` | Invalid email format or phone length |

---

### 2. Get Customer by ID

```
GET /api/v1/customers/{customer_id}
```

**Response `200`**

```json
{
  "customer_id": 1,
  "name": "Vivaan Khan",
  "email": "vi****@inbox.com",
  "phone": "92****3015",
  "kyc_status": "VERIFIED",
  "created_at": "2022-09-12T10:02:36+00:00"
}
```

| Code | Condition |
|---|---|
| `404 Not Found` | No customer with that ID |

---

### 3. List Customers

```
GET /api/v1/customers
```

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `page` | integer | `1` | Page number (1-based) |
| `size` | integer | `20` | Records per page (max 100) |
| `kyc_status` | enum | — | Filter: `PENDING`, `VERIFIED`, or `REJECTED` |

**Examples**

```bash
# Page 1, 10 per page
GET /api/v1/customers?page=1&size=10

# All PENDING customers
GET /api/v1/customers?kyc_status=PENDING
```

**Response `200`**

```json
[
  {
    "customer_id": 1,
    "name": "Vivaan Khan",
    "email": "vi****@inbox.com",
    "phone": "92****3015",
    "kyc_status": "VERIFIED",
    "created_at": "2022-09-12T10:02:36+00:00"
  },
  ...
]
```

---

### 4. Update Customer

```
PUT /api/v1/customers/{customer_id}
```

Partial update — only fields present in the body are changed. Omitted fields are left unchanged.

**Request body**

```json
{
  "name": "Priya Sharma Reddy",
  "phone": "9000000001"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `name` | string | No | 1–100 characters |
| `email` | string | No | Valid email format |
| `phone` | string | No | 10–15 characters |

**Response `200`** — updated customer object

| Code | Condition |
|---|---|
| `404 Not Found` | No customer with that ID |

---

### 5. Delete Customer

```
DELETE /api/v1/customers/{customer_id}
```

**Response `204 No Content`** — empty body

| Code | Condition |
|---|---|
| `404 Not Found` | No customer with that ID |

---

### 6. Get KYC Status

```
GET /api/v1/customers/{customer_id}/kyc
```

**Response `200`**

```json
{
  "customer_id": 6,
  "kyc_status": "PENDING",
  "updated_at": "2023-07-25T07:33:42+00:00"
}
```

| Code | Condition |
|---|---|
| `404 Not Found` | No customer with that ID |

---

### 7. Update KYC Status

```
PATCH /api/v1/customers/{customer_id}/kyc
```

Transitions the KYC state. Publishes a `KYCStatusUpdated` event to RabbitMQ on success.

**Request body**

```json
{
  "kyc_status": "VERIFIED"
}
```

Valid values: `PENDING`, `VERIFIED`, `REJECTED`

**Response `200`**

```json
{
  "customer_id": 6,
  "kyc_status": "VERIFIED",
  "updated_at": "2026-05-02T10:20:00.000000+00:00"
}
```

| Code | Condition |
|---|---|
| `404 Not Found` | No customer with that ID |
| `422 Unprocessable Entity` | Invalid `kyc_status` value |

---

## Events Published

The service publishes to the `banking.events` RabbitMQ topic exchange.

### `banking.KYCStatusUpdated`

Routing key: `banking.KYCStatusUpdated`

Published whenever a customer's KYC status changes via `PATCH /customers/{id}/kyc`.

**Payload**

```json
{
  "customer_id": 6,
  "old_status": "PENDING",
  "new_status": "VERIFIED"
}
```

**Consumers**

| Service | Action on receipt |
|---|---|
| `notification-svc` | Sends email/SMS alert to the customer |

**Delivery guarantees**

- Messages are marked `PERSISTENT` — they survive a RabbitMQ restart
- The exchange is `durable` — it survives a RabbitMQ restart
- If publishing fails, the service retries up to 3 times with exponential backoff (1s → 2s → 4s) before logging an error and continuing — the DB commit is **not** rolled back

---

## Resilience

### RabbitMQ publish retry

```
Attempt 1  ──(fail)──►  wait 1s
Attempt 2  ──(fail)──►  wait 2s
Attempt 3  ──(fail)──►  log ERROR, continue
```

Implemented with `tenacity` in `routers/kyc.py`:
- `stop_after_attempt(3)` — maximum 3 total tries
- `wait_exponential(min=1, max=8)` — 1s, 2s, 4s (capped at 8s)
- `timeout=5` seconds on broker connection
- Each retry attempt is logged at `WARNING` level with structured JSON
- After all retries are exhausted, an `ERROR` is logged and the HTTP response is still returned successfully (KYC update is committed to DB)

### Database connection pool

Configured in `db.py`:
- `pool_size=10` — up to 10 persistent connections
- `max_overflow=20` — up to 20 additional overflow connections under load

---

## Observability

### Prometheus metrics

Scraped at `http://localhost:8001/metrics`. Prometheus is configured to scrape every 15 seconds via `prometheus.yml`.

**HTTP metrics (all endpoints)**

| Metric | Type | Labels |
|---|---|---|
| `http_requests_total` | Counter | `service`, `method`, `endpoint`, `status_code` |
| `http_request_duration_seconds` | Histogram | `service`, `method`, `endpoint` |

Histogram buckets: `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5` seconds.

**Business metrics**

| Metric | Type | Labels | Incremented when |
|---|---|---|---|
| `customer_registrations_total` | Counter | `service` | `POST /customers` succeeds (201) |
| `duplicate_email_rejections_total` | Counter | `service` | `POST /customers` returns 409 |
| `kyc_status_changes_total` | Counter | `service`, `new_status` | `PATCH /customers/{id}/kyc` succeeds |

**Useful PromQL queries**

```promql
# Requests per second
rate(http_requests_total{service="customer-svc"}[1m])

# Error rate (%)
100 * sum(rate(http_requests_total{service="customer-svc", status_code=~"[45].."}[1m]))
    / sum(rate(http_requests_total{service="customer-svc"}[1m]))

# p99 response latency
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket{service="customer-svc"}[5m])) by (le)
)

# KYC approvals per minute
rate(kyc_status_changes_total{service="customer-svc", new_status="VERIFIED"}[1m]) * 60
```

### Grafana dashboard

A pre-built dashboard is automatically provisioned at startup (no manual import needed).

Access at `http://localhost:3000` (credentials: `admin` / value of `GRAFANA_PASS` in `.env`, default `admin`).

**Panels**

| Panel | Type | What it shows |
|---|---|---|
| Requests per Second | Time series | Rate by method and endpoint |
| Error Rate (%) | Time series | 4xx/5xx as % of total traffic |
| Response Latency (p50/p90/p99) | Time series | Latency percentiles over 5m window |
| Customer Registrations (rate/min) | Time series | New signups per minute |
| KYC Status Changes | Time series | Transitions by target state |
| Duplicate Email Rejections | Time series | Rejected duplicates per minute |
| Total Customers Registered | Stat | Cumulative counter |
| KYC → VERIFIED (total) | Stat | Cumulative verified |
| KYC → REJECTED (total) | Stat | Cumulative rejected |
| Duplicate Email Rejections (total) | Stat | Cumulative duplicates |

### Structured JSON logging

Every request produces one JSON log line:

```json
{
  "timestamp": "2026-05-02 10:15:30,123",
  "level": "INFO",
  "service": "customer-svc",
  "correlationId": "a3f7c2e1-84b0-4d9a-b321-1c2e3f4a5b6c",
  "path": "/api/v1/customers",
  "latency_ms": 12,
  "message": "Request handled"
}
```

**Correlation ID**

The service reads `X-Correlation-ID` from the incoming request header. If not present, a new UUID is generated. The ID is included in the log line and echoed back in the response header so callers can trace a request end-to-end across services.

**PII masking**

Email addresses and 10-digit phone numbers are automatically masked before writing to logs:

| Input | Logged as |
|---|---|
| `priya.sharma@example.com` | `pr****@example.com` |
| `9876543210` | `98****3210` |

---

## Docker

### Dockerfile highlights

The Dockerfile uses a **two-stage build** to keep the final image small and secure.

```
Stage 1 (builder)      Stage 2 (runtime)
──────────────────     ──────────────────────────────
python:3.11-slim       python:3.11-slim
pip install deps   ──► copy site-packages only
                       create non-root appuser
                       EXPOSE 8001
                       HEALTHCHECK → /api/v1/health
                       CMD uvicorn
```

**Security practices**
- No `pip`, build tools, or caches in the final image
- Runs as `appuser` (non-root) — no root access inside the container
- `HEALTHCHECK` allows Docker and docker-compose to detect and replace unhealthy containers

**Build and run manually**

```bash
cd customer-service

# Build
docker build -t banking/customer-svc:1.0.0 .

# Run (requires customer-db and rabbitmq to be reachable)
docker run -p 8001:8001 \
  -e DATABASE_URL="postgresql+asyncpg://cust_user:pass@host/customer_db" \
  -e RABBITMQ_URL="amqp://rabbit:pass@host:5672/" \
  banking/customer-svc:1.0.0
```

### docker-compose service definition

```yaml
customer-svc:
  build: ./customer-service
  ports:
    - "8001:8001"
  environment:
    DATABASE_URL: postgresql+asyncpg://${CUSTOMER_DB_USER:-cust_user}:${CUSTOMER_DB_PASS}@customer-db/customer_db
    RABBITMQ_URL: amqp://${RABBIT_USER:-rabbit}:${RABBIT_PASS}@rabbitmq:5672/
    LOG_LEVEL:    INFO
  depends_on:
    customer-db: { condition: service_healthy }
    rabbitmq:    { condition: service_healthy }
  restart: unless-stopped
```

The service only starts after both `customer-db` and `rabbitmq` pass their health checks — no race conditions on startup.

---

## Kubernetes

Manifests are in `k8s/customer-service/deployment.yaml`. All resources are deployed to the `banking` namespace.

**Resources defined**

| Kind | Name | Purpose |
|---|---|---|
| `Deployment` | `customer-svc` | 2 replicas of the API pod |
| `Service` | `customer-svc` | NodePort 30001 — external access |
| `ConfigMap` | `customer-svc-config` | `LOG_LEVEL`, `RABBITMQ_URL` |
| `Secret` | `customer-svc-secret` | `DATABASE_URL`, `DB_PASSWORD`, `SECRET_KEY` |
| `StatefulSet` | `customer-db` | Postgres 15 with stable identity |
| `PersistentVolumeClaim` | `customer-db-storage` | 5Gi database storage |
| `Service` (headless) | `customer-db-svc` | Stable DNS for the StatefulSet |

**Deploy to Minikube**

```bash
minikube start

# Create namespace
kubectl create namespace banking

# Apply all resources
kubectl apply -f k8s/customer-service/deployment.yaml

# Watch pods come up
kubectl get pods -n banking -w

# Check services
kubectl get svc -n banking

# View logs
kubectl logs -n banking deployment/customer-svc --tail=50 -f

# Get access URL
minikube service customer-svc -n banking --url
```

**Readiness vs liveness probes**

| Probe | Path | Initial delay | Period | Purpose |
|---|---|---|---|---|
| Readiness | `/api/v1/health` | 10s | 5s | Remove from load balancer if unhealthy |
| Liveness | `/api/v1/health` | 30s | 15s | Restart container if stuck |

**Resource limits**

| | CPU | Memory |
|---|---|---|
| Request | 100m | 128Mi |
| Limit | 500m | 512Mi |

---

## Testing

### Option 1 — VS Code REST Client

Open `api-tests.http` in VS Code. Click **Send Request** above any request block. The file covers all 20 test cases including happy paths and edge cases.

Requires the **REST Client** extension (`humao.rest-client`) to be installed.

### Option 2 — Shell test script

Runs all CRUD and KYC flows using `curl` and reports pass/fail counts.

```bash
# Against Docker Compose
bash customer-service/test-customer-service.sh

# Against Minikube
bash customer-service/test-customer-service.sh http://127.0.0.1:61339

# Against local uvicorn
bash customer-service/test-customer-service.sh http://localhost:8001
```

Expected output:

```
── 1. HEALTH CHECK ──────────────────────────────
  PASS  service is healthy

── 2. CREATE CUSTOMERS ──────────────────────────
  PASS  customer created with name
  PASS  kyc_status defaults to PENDING
  PASS  second customer created
  PASS  duplicate email returns 409
  PASS  invalid email returns 422
  PASS  short phone returns 422
...
── RESULTS ──────────────────────────────────────
  Total : 24
  Passed: 24
  Failed: 0

All tests passed!
```

### Option 3 — Direct curl

```bash
# Health
curl http://localhost:8001/api/v1/health

# Create customer
curl -X POST http://localhost:8001/api/v1/customers \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: my-trace-id-001" \
  -d '{"name":"Priya Sharma","email":"priya@example.com","phone":"9876543210"}'

# List with filter
curl "http://localhost:8001/api/v1/customers?kyc_status=PENDING&page=1&size=5"

# Approve KYC
curl -X PATCH http://localhost:8001/api/v1/customers/6/kyc \
  -H "Content-Type: application/json" \
  -d '{"kyc_status":"VERIFIED"}'

# Prometheus metrics
curl http://localhost:8001/metrics
```

---

## Design Decisions

**Database per service**
Customer-service owns `customer_db` exclusively. No other service connects to it directly. `account-svc` stores a local copy of `customer_name` in its own DB (read-optimized projection) to avoid cross-service DB queries at read time.

**Async throughout**
SQLAlchemy is used in full async mode (`create_async_engine`, `AsyncSession`) paired with `asyncpg`. This means the service handles concurrent requests without blocking threads on I/O, which is important for a database-heavy service.

**KYC validation at schema level**
`kyc_status` uses `Literal["PENDING","VERIFIED","REJECTED"]` in Pydantic. This means invalid values are rejected by the framework before reaching any business logic, and the valid options appear as a dropdown in the Swagger UI — no custom validation code needed.

**Non-blocking event publishing**
The DB commit happens before publishing to RabbitMQ. If the broker is temporarily unavailable, the KYC update is not rolled back — it retries publishing up to 3 times and logs an error if all retries fail. This is an intentional trade-off: customer data consistency takes priority over event delivery guarantees. In production, an outbox pattern or dead-letter queue would close this gap.

**PII masking in logs**
Emails and phone numbers are masked at the formatter level — the mask is applied to every log message regardless of where it originates. This prevents accidental PII leakage into log aggregation systems (ELK, Loki, CloudWatch).

**Correlation ID propagation**
If the caller sends an `X-Correlation-ID` header, it is threaded through all log lines for that request and echoed back in the response header. Downstream services should forward this header when calling customer-svc so that a single user-facing operation can be traced across service boundaries.

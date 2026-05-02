# Banking Microservices Platform

A cloud-native banking backend built with microservices architecture. Each service owns its domain independently — separate database, separate deployment, separate scaling — and communicates through REST APIs and RabbitMQ events.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Services at a Glance](#services-at-a-glance)
3. [End-to-End Workflow](#end-to-end-workflow)
4. [Tech Stack](#tech-stack)
5. [Repository Structure](#repository-structure)
6. [Prerequisites](#prerequisites)
7. [Quick Start](#quick-start)
8. [Environment Variables](#environment-variables)
9. [Port Reference](#port-reference)
10. [Database Schemas](#database-schemas)
11. [Event Bus](#event-bus)
12. [Monitoring and Observability](#monitoring-and-observability)
13. [Kubernetes Deployment](#kubernetes-deployment)
14. [Implementation Status](#implementation-status)
15. [Service READMEs](#service-readmes)

---

## Architecture Overview

```
                        ┌─────────────────────────────────────────────────┐
                        │             Banking Microservices Platform       │
                        │                                                  │
   Client / Postman ───►│  ┌──────────────┐      ┌──────────────────┐    │
                        │  │ customer-svc │      │   account-svc    │    │
                        │  │   :8001      │◄─────│     :8002        │    │
                        │  │              │      │                  │    │
                        │  │ customer-db  │      │   account-db     │    │
                        │  │ (postgres)   │      │   (postgres)     │    │
                        │  └──────┬───────┘      └────────▲─────────┘    │
                        │         │                        │              │
                        │         │  KYCStatusUpdated      │ validate     │
                        │         │                        │ balance      │
                        │         ▼                        │              │
                        │  ┌──────────────────────────┐    │              │
                        │  │   RabbitMQ :5672         │    │              │
                        │  │   banking.events (topic) │    │              │
                        │  └──────────┬───────────────┘    │              │
                        │             │                     │              │
                        │   TransactionCreated             │              │
                        │   KYCStatusUpdated               │              │
                        │             │                     │              │
                        │             ▼                     │              │
                        │  ┌──────────────────┐   ┌────────┴───────┐     │
                        │  │ notification-svc │   │transaction-svc │     │
                        │  │     :8004        │   │     :8003      │     │
                        │  │                  │   │                │     │
                        │  │ notification-db  │   │ transaction-db │     │
                        │  │   (postgres)     │   │   (postgres)   │     │
                        │  └──────────────────┘   └────────────────┘     │
                        │                                                  │
                        │  ┌───────────────┐   ┌──────────────────────┐  │
                        │  │  Prometheus   │   │       Grafana        │  │
                        │  │    :9090      │──►│        :3000         │  │
                        │  └───────────────┘   └──────────────────────┘  │
                        └─────────────────────────────────────────────────┘
```

### Core design principles

| Principle | How it is applied |
|---|---|
| **Database per Service** | Each service has its own isolated PostgreSQL instance — no shared tables, no cross-DB joins |
| **Loose Coupling** | Services communicate via REST calls or RabbitMQ events — no shared code or shared DB |
| **Single Responsibility** | Each service owns exactly one domain (customer identity, accounts, transactions, notifications) |
| **Design for failure** | Retries with exponential backoff, health probes, graceful degradation when broker is unavailable |
| **Observable by default** | Prometheus metrics, structured JSON logs with PII masking, Grafana dashboards provisioned at startup |

---

## Services at a Glance

| Service | Port | Database | Responsibility | Build Status |
|---|---|---|---|---|
| `customer-svc` | 8001 | `customer_db` | Customer profiles, KYC lifecycle | ✅ Complete |
| `account-svc` | 8002 | `account_db` | Bank accounts, balance management | 🚧 Planned |
| `transaction-svc` | 8003 | `transaction_db` | Transfers, payments, idempotency | 🚧 Planned |
| `notification-svc` | 8004 | `notification_db` | Email/SMS alerts via RabbitMQ events | 🚧 Planned |

**Supporting infrastructure**

| Service | Port | Purpose |
|---|---|---|
| RabbitMQ | 5672 / 15672 | Async event bus between services |
| Prometheus | 9090 | Metrics collection and storage |
| Grafana | 3000 | Dashboards and alerting |

---

## End-to-End Workflow

The canonical banking workflow once all services are built:

```
1. Customer Registration
   POST /api/v1/customers  ──►  customer-svc  ──►  customer-db

2. KYC Approval
   PATCH /api/v1/customers/{id}/kyc  ──►  customer-svc
       └──►  publishes KYCStatusUpdated  ──►  RabbitMQ
                 └──►  notification-svc  ──►  sends email to customer

3. Account Opening
   POST /api/v1/accounts  ──►  account-svc
       └──►  GET /api/v1/customers/{id}  ──►  customer-svc  (validate KYC = VERIFIED)
       └──►  account-db

4. Fund Transfer
   POST /api/v1/transfer  ──►  transaction-svc
       └──►  GET /api/v1/accounts/{id}  ──►  account-svc  (validate ACTIVE, check balance)
       └──►  PATCH /api/v1/accounts/{id}/lock  ──►  account-svc  (lock funds)
       └──►  record DEBIT + CREDIT entries  ──►  transaction-db
       └──►  PATCH /api/v1/accounts/{id}/release  ──►  account-svc  (release lock)
       └──►  publishes TransactionCreated  ──►  RabbitMQ
                 └──►  notification-svc  ──►  sends SMS/email confirmation

5. Notification Delivery
   notification-svc  ──►  consumes events  ──►  sends via SMTP/SMS
       └──►  logs result  ──►  notification-db (notifications_log)
```

**Business rules enforced across services**

| Rule | Enforced by |
|---|---|
| Customer must have KYC = VERIFIED to open an account | `account-svc` calls `customer-svc` |
| Account must be ACTIVE (not FROZEN or CLOSED) for transactions | `transaction-svc` calls `account-svc` |
| Daily transfer limit: ₹2,00,000 per account | `transaction-svc` (env var `DAILY_TRANSFER_LIMIT`) |
| Idempotent transfers — duplicate requests return cached response | `transaction-svc` via `idempotency_keys` table |
| Single currency — INR unless forex explicitly enabled | `transaction-svc` |

---

## Tech Stack

### Application

| Technology | Version | Used for |
|---|---|---|
| Python | 3.11 | All microservices |
| FastAPI | 0.111.0 | REST API framework |
| Uvicorn | 0.29.0 | ASGI server |
| SQLAlchemy (async) | 2.0.30 | ORM and DB queries |
| asyncpg | 0.29.0 | Async PostgreSQL driver |
| Pydantic v2 | 2.7.1 | Request/response validation |
| aio-pika | 9.4.1 | Async RabbitMQ client |
| tenacity | 8.3.0 | Retry with exponential backoff |
| prometheus-client | 0.20.0 | Metrics instrumentation |
| httpx | 0.27.0 | Async HTTP client for inter-service calls |

### Infrastructure

| Technology | Version | Used for |
|---|---|---|
| PostgreSQL | 15 | Per-service relational database |
| RabbitMQ | 3.12 | Async event bus |
| Prometheus | latest | Metrics scraping and storage |
| Grafana | latest | Dashboards (auto-provisioned) |
| Docker | 24+ | Containerisation |
| Docker Compose | v2 | Local orchestration |
| Kubernetes / Minikube | 1.28+ / 1.32+ | Production-like deployment |

---

## Repository Structure

```
banking_project/
├── .env.example                    # Template — copy to .env and fill passwords
├── docker-compose.yml              # Full stack: all services + DBs + observability
├── prometheus.yml                  # Prometheus scrape config (all 4 services)
│
├── customer-service/               # ✅ Fully implemented
│   ├── app/
│   │   ├── main.py                 # FastAPI app, middleware, logging
│   │   ├── metrics.py              # Prometheus metric definitions
│   │   ├── models.py               # SQLAlchemy ORM — customers table
│   │   ├── schemas.py              # Pydantic request/response schemas
│   │   ├── db.py                   # Async engine and session factory
│   │   └── routers/
│   │       ├── customers.py        # CRUD endpoints
│   │       └── kyc.py              # KYC endpoints + RabbitMQ publisher
│   ├── Dockerfile                  # Multi-stage, non-root, HEALTHCHECK
│   ├── requirements.txt
│   ├── api-tests.http              # VS Code REST Client test file
│   ├── test-customer-service.sh    # Automated shell test script
│   └── README.md                   # Detailed service documentation
│
├── account-service/                # 🚧 Planned
├── transaction-service/            # 🚧 Planned
├── notification-service/           # 🚧 Planned
│
├── k8s/
│   └── customer-service/
│       └── deployment.yaml         # Deployment, Service, ConfigMap, Secret, PVC
│
├── seeds/
│   ├── seed_customers.sql          # 60 customer records (auto-loaded)
│   ├── seed_accounts.sql           # 88 account records (auto-loaded)
│   ├── seed_transactions.sql       # 300 transaction records + idempotency table
│   └── seed_notifications.sql      # notifications_log schema (empty, runtime-filled)
│
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── prometheus.yaml     # Auto-wires Prometheus as default datasource
    │   └── dashboards/
    │       └── provider.yaml       # Tells Grafana where to find dashboard JSON
    └── dashboards/
        └── customer-svc.json       # 10-panel customer service dashboard
```

---

## Prerequisites

| Tool | Minimum version | Install |
|---|---|---|
| Docker Desktop | 24+ | https://docs.docker.com/get-docker/ |
| Docker Compose | v2 | Bundled with Docker Desktop |
| Git | any | https://git-scm.com/ |
| kubectl | 1.28+ | https://kubernetes.io/docs/tasks/tools/ |
| minikube | 1.32+ | https://minikube.sigs.k8s.io/docs/start/ |
| VS Code + REST Client | any | Extension ID: `humao.rest-client` |

---

## Quick Start

### 1. Clone and configure

```bash
git clone <repository-url>
cd banking_project

cp .env.example .env
```

Open `.env` and set real passwords for all `*_PASS` variables. **Passwords have no defaults** — the services will not start without them.

### 2. Start the full stack

```bash
docker compose up -d
```

This starts: 4 PostgreSQL databases, RabbitMQ, customer-svc, Prometheus, and Grafana. Seed data is automatically loaded into all databases on first boot.

### 3. Verify everything is up

```bash
docker compose ps
```

Expected output — all services `Up (healthy)` or `Up`:

```
NAME                           STATUS           PORTS
banking_project-customer-db    Up (healthy)     5432/tcp
banking_project-rabbitmq       Up (healthy)     0.0.0.0:5672->5672/tcp
banking_project-customer-svc   Up (healthy)     0.0.0.0:8001->8001/tcp
banking_project-prometheus      Up               0.0.0.0:9090->9090/tcp
banking_project-grafana         Up               0.0.0.0:3000->3000/tcp
```

### 4. Verify the customer service

```bash
curl http://localhost:8001/api/v1/health
```

```json
{"status": "healthy", "service": "customer-svc", "version": "1.0.0"}
```

### 5. Open the tools

| Tool | URL | Credentials |
|---|---|---|
| Customer API docs (Swagger) | http://localhost:8001/docs | — |
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | `admin` / value of `GRAFANA_PASS` in `.env` |
| RabbitMQ Management | http://localhost:15672 | value of `RABBIT_USER` / `RABBIT_PASS` in `.env` |

### 6. Run the automated tests

```bash
bash customer-service/test-customer-service.sh
```

---

## Environment Variables

Copy `.env.example` to `.env` before starting. Variables marked **Required** have no fallback defaults and will cause startup failure if missing.

### Database credentials

| Variable | Required | Example value | Used by |
|---|---|---|---|
| `CUSTOMER_DB_USER` | No | `cust_user` | `customer-svc`, `customer-db` |
| `CUSTOMER_DB_PASS` | **Yes** | `your-secure-pass` | `customer-svc`, `customer-db` |
| `ACCOUNT_DB_USER` | No | `acct_user` | `account-svc`, `account-db` |
| `ACCOUNT_DB_PASS` | **Yes** | `your-secure-pass` | `account-svc`, `account-db` |
| `TXN_DB_USER` | No | `txn_user` | `transaction-svc`, `transaction-db` |
| `TXN_DB_PASS` | **Yes** | `your-secure-pass` | `transaction-svc`, `transaction-db` |
| `NOTIF_DB_USER` | No | `notif_user` | `notification-svc`, `notification-db` |
| `NOTIF_DB_PASS` | **Yes** | `your-secure-pass` | `notification-svc`, `notification-db` |

### Message broker

| Variable | Required | Example value | Used by |
|---|---|---|---|
| `RABBIT_USER` | No | `rabbit` | All services + RabbitMQ |
| `RABBIT_PASS` | **Yes** | `your-secure-pass` | All services + RabbitMQ |

### Notification service (SMTP)

| Variable | Required | Example value | Used by |
|---|---|---|---|
| `SMTP_HOST` | No | `smtp.gmail.com` | `notification-svc` |
| `SMTP_PORT` | No | `587` | `notification-svc` |
| `SMTP_USER` | No | `you@gmail.com` | `notification-svc` |
| `SMTP_PASS` | No | `your-app-password` | `notification-svc` |

### Security and observability

| Variable | Required | Example value | Used by |
|---|---|---|---|
| `SECRET_KEY` | **Yes** | `random-256-bit-string` | All services (JWT signing) |
| `GRAFANA_PASS` | No | `admin` | Grafana admin login |

---

## Port Reference

| Service | Host port | Container port | Protocol |
|---|---|---|---|
| `customer-svc` | 8001 | 8001 | HTTP |
| `account-svc` | 8002 | 8002 | HTTP |
| `transaction-svc` | 8003 | 8003 | HTTP |
| `notification-svc` | 8004 | 8004 | HTTP |
| RabbitMQ (AMQP) | 5672 | 5672 | AMQP |
| RabbitMQ (Management UI) | 15672 | 15672 | HTTP |
| Prometheus | 9090 | 9090 | HTTP |
| Grafana | 3000 | 3000 | HTTP |

---

## Database Schemas

Each service owns a completely isolated PostgreSQL instance. No service ever connects to another service's database.

### customer-db — `customers`

```sql
customers (
    customer_id  SERIAL PRIMARY KEY,
    name         VARCHAR(100)  NOT NULL,
    email        VARCHAR(150)  UNIQUE NOT NULL,
    phone        VARCHAR(15)   NOT NULL,
    kyc_status   VARCHAR(20)   NOT NULL DEFAULT 'PENDING'
                 CHECK (kyc_status IN ('PENDING','VERIFIED','REJECTED')),
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT now()
)
```

Seed: **60 customers** with mixed KYC statuses.

---

### account-db — `accounts`

```sql
accounts (
    account_id      SERIAL PRIMARY KEY,
    customer_id     INTEGER          NOT NULL,
    customer_name   VARCHAR(100)     NOT NULL,   -- read-optimised projection from customer-svc
    account_number  VARCHAR(20)      UNIQUE NOT NULL,
    account_type    VARCHAR(20)      NOT NULL
                    CHECK (account_type IN ('SAVINGS','CURRENT','SALARY','NRE')),
    balance         NUMERIC(15,2)    NOT NULL DEFAULT 0.00 CHECK (balance >= 0),
    currency        CHAR(3)          NOT NULL DEFAULT 'INR',
    status          VARCHAR(20)      NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','FROZEN','CLOSED')),
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ      NOT NULL DEFAULT now()
)
```

`customer_name` is a denormalised copy — `account-svc` stores it locally so it never needs to call `customer-svc` at read time.

Seed: **88 accounts** across 60 customers. Multiple account types, some FROZEN/CLOSED.

---

### transaction-db — `transactions` + `idempotency_keys`

```sql
transactions (
    txn_id          SERIAL PRIMARY KEY,
    account_id      INTEGER          NOT NULL,
    amount          NUMERIC(15,2)    NOT NULL CHECK (amount > 0),
    txn_type        VARCHAR(20)      NOT NULL
                    CHECK (txn_type IN ('DEPOSIT','WITHDRAWAL','TRANSFER_IN','TRANSFER_OUT','PAYMENT')),
    counterparty    VARCHAR(200),
    reference       VARCHAR(50)      NOT NULL,
    idempotency_key VARCHAR(100),
    status          VARCHAR(20)      NOT NULL DEFAULT 'COMPLETED',
    created_at      TIMESTAMPTZ      NOT NULL DEFAULT now()
)

idempotency_keys (
    idempotency_key VARCHAR(100)  PRIMARY KEY,
    response_body   JSONB         NOT NULL,   -- full HTTP response cached
    status_code     INTEGER       NOT NULL,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ   NOT NULL    -- TTL-based expiry window
)
```

The `idempotency_keys` table prevents duplicate transfer processing — if the same key is submitted within the TTL window, the cached response is returned without reprocessing.

Seed: **300 transactions** across 88 accounts spanning 2022–2026.

---

### notification-db — `notifications_log`

```sql
notifications_log (
    notification_id  SERIAL PRIMARY KEY,
    customer_id      INTEGER        NOT NULL,
    customer_email   VARCHAR(150)   NOT NULL,
    customer_phone   VARCHAR(15)    NOT NULL,
    event_type       VARCHAR(50)    NOT NULL,
    channel          VARCHAR(10)    NOT NULL CHECK (channel IN ('EMAIL','SMS')),
    status           VARCHAR(20)    NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING','SENT','FAILED','SKIPPED')),
    payload          JSONB          NOT NULL DEFAULT '{}',
    retry_count      SMALLINT       NOT NULL DEFAULT 0,
    sent_at          TIMESTAMPTZ,
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT now()
)
```

Populated at runtime by `notification-svc` as it consumes events. Empty on startup.

---

## Event Bus

All asynchronous communication uses RabbitMQ.

**Exchange:** `banking.events`
**Type:** Topic (durable, survives broker restart)
**Message delivery:** PERSISTENT (survives broker restart)

### Events

| Routing key | Published by | Consumed by | Payload |
|---|---|---|---|
| `banking.KYCStatusUpdated` | `customer-svc` | `notification-svc` | `{customer_id, old_status, new_status}` |
| `banking.TransactionCreated` | `transaction-svc` | `notification-svc` | `{txn_id, account_id, amount, txn_type}` |

### Resilience

Publishers use **retry with exponential backoff** (via `tenacity`):
- Up to 3 attempts
- Backoff: 1s → 2s → 4s (capped at 8s)
- 5-second connection timeout
- If all retries fail: error is logged, DB commit is retained, HTTP response is still returned
- Each retry is logged at `WARNING` level with a structured JSON entry

### RabbitMQ Management UI

Access at `http://localhost:15672` — login with `RABBIT_USER` / `RABBIT_PASS` from `.env`.

Use it to inspect exchanges, queues, and message rates in real time.

---

## Monitoring and Observability

### Prometheus

Access at `http://localhost:9090`

Scrapes all four services every 15 seconds from `/metrics`.

**Metrics exposed by customer-svc** (template for all services)

| Metric | Type | Description |
|---|---|---|
| `http_requests_total` | Counter | Request count by method, endpoint, status code |
| `http_request_duration_seconds` | Histogram | Response duration (p50, p90, p99 via `histogram_quantile`) |
| `customer_registrations_total` | Counter | Successful new customer registrations |
| `kyc_status_changes_total` | Counter | KYC transitions by target status |
| `duplicate_email_rejections_total` | Counter | 409 conflicts on POST /customers |

**Key PromQL queries**

```promql
# Requests per second across all services
sum(rate(http_requests_total[1m])) by (service)

# Error rate per service
100 * sum(rate(http_requests_total{status_code=~"[45].."}[1m])) by (service)
   / sum(rate(http_requests_total[1m])) by (service)

# p99 latency per service
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (service, le)
)
```

### Grafana

Access at `http://localhost:3000`

Credentials: `admin` / value of `GRAFANA_PASS` in `.env` (default: `admin`)

The Prometheus datasource and all dashboards are **auto-provisioned on startup** — no manual imports needed.

**Customer Service Dashboard** (10 panels)

| Panel | Type |
|---|---|
| Requests per Second | Time series |
| Error Rate (%) | Time series |
| Response Latency p50 / p90 / p99 | Time series |
| Customer Registrations rate/min | Time series |
| KYC Status Changes by target state | Time series |
| Duplicate Email Rejections rate/min | Time series |
| Total Customers Registered | Stat |
| KYC → VERIFIED total | Stat |
| KYC → REJECTED total | Stat |
| Duplicate Rejections total | Stat |

### Structured JSON Logging

Every service emits one JSON log line per request:

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

**Correlation ID:** Pass `X-Correlation-ID: <uuid>` in any request. The value is threaded through all log lines for that request and echoed back in the response header — enabling end-to-end tracing across services.

**PII masking:** Email addresses and phone numbers are automatically masked before writing to logs:

```
priya.sharma@example.com  →  pr****@example.com
9876543210                →  98****3210
```

---

## Kubernetes Deployment

Manifests are in the `k8s/` directory, all deployed to the `banking` namespace.

### Deploy customer service to Minikube

```bash
# Start cluster
minikube start

# Create namespace
kubectl create namespace banking

# Deploy all resources
kubectl apply -f k8s/customer-service/deployment.yaml

# Watch pods
kubectl get pods -n banking -w

# Get NodePort URL
minikube service customer-svc -n banking --url
```

### Verify

```bash
# Pod status
kubectl get pods -n banking

# Services
kubectl get svc -n banking

# Logs (live)
kubectl logs -n banking deployment/customer-svc -f

# Test via NodePort (replace IP with minikube ip output)
curl http://$(minikube ip):30001/api/v1/health
```

### Kubernetes resources (customer-svc)

| Kind | Name | Detail |
|---|---|---|
| `Deployment` | `customer-svc` | 2 replicas, readiness + liveness probes |
| `Service` | `customer-svc` | NodePort 30001 |
| `ConfigMap` | `customer-svc-config` | `LOG_LEVEL`, `RABBITMQ_URL` |
| `Secret` | `customer-svc-secret` | `DATABASE_URL`, `DB_PASSWORD`, `SECRET_KEY` |
| `StatefulSet` | `customer-db` | PostgreSQL 15, stable DNS |
| `PersistentVolumeClaim` | `customer-db-storage` | 5Gi, ReadWriteOnce |
| `Service` (headless) | `customer-db-svc` | Stable DNS for StatefulSet |

### Resource limits (all service pods)

| | CPU | Memory | Ephemeral storage |
|---|---|---|---|
| Request | 100m | 128Mi | 64Mi |
| Limit | 500m | 512Mi | 256Mi |

---

## Implementation Status

### ✅ customer-svc — Complete

- [x] FastAPI app with async SQLAlchemy
- [x] Full CRUD: create, read, update, delete customers
- [x] KYC lifecycle management (PENDING → VERIFIED / REJECTED)
- [x] Input validation: email format, phone length, KYC enum
- [x] DB constraints: UNIQUE email, NOT NULL, CHECK kyc_status
- [x] RabbitMQ event publishing with retry + exponential backoff
- [x] Prometheus metrics (RED + 3 business metrics)
- [x] Structured JSON logging with PII masking
- [x] Correlation ID from request header, forwarded in response
- [x] Multi-stage Dockerfile with non-root user and HEALTHCHECK
- [x] docker-compose with service_healthy dependency checks
- [x] Kubernetes manifests (Deployment, Service, ConfigMap, Secret, StatefulSet, PVC)
- [x] Grafana dashboard auto-provisioned (10 panels)
- [x] OpenAPI spec with summaries, descriptions, error schemas
- [x] Seed data (60 customers, auto-loaded)
- [x] Test script (`test-customer-service.sh`) and REST Client file (`api-tests.http`)

### 🚧 account-svc — Planned

- [ ] FastAPI service
- [ ] Endpoints: create account, get account, list accounts, freeze/unfreeze
- [ ] Balance management: credit, debit, lock/unlock funds
- [ ] Validate customer KYC status via `customer-svc` REST call
- [ ] Kubernetes manifests
- [ ] Prometheus metrics + Grafana dashboard

### 🚧 transaction-svc — Planned

- [ ] FastAPI service
- [ ] `POST /transfer` — validates balance, records debit + credit
- [ ] Idempotency handling using `idempotency_keys` table
- [ ] Daily transfer limit enforcement (env var `DAILY_TRANSFER_LIMIT=200000`)
- [ ] Block transfers on FROZEN accounts
- [ ] Publish `TransactionCreated` event to RabbitMQ
- [ ] Kubernetes manifests
- [ ] Prometheus metrics + Grafana dashboard

### 🚧 notification-svc — Planned

- [ ] FastAPI service
- [ ] RabbitMQ consumer for `KYCStatusUpdated` and `TransactionCreated`
- [ ] Email delivery via SMTP
- [ ] SMS delivery integration
- [ ] Retry logic for failed notifications
- [ ] Log all notifications to `notifications_log`
- [ ] Kubernetes manifests
- [ ] Prometheus metrics + Grafana dashboard

---

## Service READMEs

Detailed documentation for each service is in its own directory:

| Service | README |
|---|---|
| customer-svc | [customer-service/README.md](customer-service/README.md) |
| account-svc | Planned |
| transaction-svc | Planned |
| notification-svc | Planned |

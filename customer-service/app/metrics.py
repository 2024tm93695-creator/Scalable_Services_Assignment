"""Prometheus metrics for Customer Service"""
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "endpoint", "status_code"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

# ── Business metrics ───────────────────────────────────────────────────────
CUSTOMER_REGISTRATIONS = Counter(
    "customer_registrations_total",
    "New customers successfully registered",
    ["service"],
)
DUPLICATE_EMAIL_REJECTIONS = Counter(
    "duplicate_email_rejections_total",
    "Registration attempts rejected due to duplicate email",
    ["service"],
)
KYC_CHANGES = Counter(
    "kyc_status_changes_total",
    "KYC status transitions by target state",
    ["service", "new_status"],
)

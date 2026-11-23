"""Prometheus metrics for recommendation, cache, inference and dependency health."""
from prometheus_client import Counter, Histogram

RECOMMENDATION_CACHE_EVENTS = Counter(
    "cinerank_recommendation_cache_events_total",
    "Recommendation cache lookups and writes by layer and result",
    ("layer", "result"),
)
RECOMMENDATION_DURATION = Histogram(
    "cinerank_recommendation_duration_seconds",
    "Recommendation request duration by outcome",
    ("outcome",),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
RECOMMENDATION_ITEM_COUNT = Histogram(
    "cinerank_recommendation_items",
    "Number of personalized items returned in a computed recommendation page",
    buckets=(1, 5, 10, 20, 50),
)
RECOMMENDATION_INFERENCE_DURATION = Histogram(
    "cinerank_inference_duration_seconds",
    "Model inference duration by operation",
    ("operation",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
REDIS_OPERATION_ERRORS = Counter(
    "cinerank_redis_operation_errors_total",
    "Redis operation failures by operation",
    ("operation",),
)
DATABASE_OPERATION_ERRORS = Counter(
    "cinerank_database_operation_errors_total",
    "Database operation failures by operation",
    ("operation",),
)

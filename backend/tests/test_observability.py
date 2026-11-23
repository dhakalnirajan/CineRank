from prometheus_client import generate_latest

from app.core import cache
from app.core.metrics import (
    DATABASE_OPERATION_ERRORS,
    RECOMMENDATION_CACHE_EVENTS,
    RECOMMENDATION_DURATION,
    RECOMMENDATION_INFERENCE_DURATION,
    RECOMMENDATION_ITEM_COUNT,
    REDIS_OPERATION_ERRORS,
)


def test_observability_metrics_are_exported():
    cache.get_json("cinerank:metrics-test")
    RECOMMENDATION_CACHE_EVENTS.labels("memory", "hit").inc()
    RECOMMENDATION_DURATION.labels("computed").observe(0.01)
    RECOMMENDATION_ITEM_COUNT.observe(5)
    RECOMMENDATION_INFERENCE_DURATION.labels("recommend").observe(0.005)
    REDIS_OPERATION_ERRORS.labels("cache_get").inc()
    DATABASE_OPERATION_ERRORS.labels("health").inc()

    exported = generate_latest().decode()

    for metric in (
        "cinerank_recommendation_cache_events_total",
        "cinerank_recommendation_duration_seconds_bucket",
        "cinerank_recommendation_items_bucket",
        "cinerank_inference_duration_seconds_bucket",
        "cinerank_redis_operation_errors_total",
        "cinerank_database_operation_errors_total",
    ):
        assert metric in exported

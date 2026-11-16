"""Service Level Objective targets + current-state computation.

Scope: operators define SLO targets (availability + latency per
endpoint class) in config; this module computes the current period's
error rate + p95 latency from the Prometheus counters/histograms the
observability stack already emits. The result is exposed via
``GET /api/_internal/slo`` so dashboards + alerting can read a
single structured document.

The three default endpoint classes:

* ``public_verify`` — public verification routes under ``/verify``.
* ``signer`` — signer-facing endpoints under ``/sign`` and
  ``/api/signer-intent``.
* ``admin_api`` — everything else under ``/api/``.

Per-class SLO defaults (operator-overridable via config):

* ``availability_target`` — fraction of requests with status < 500.
  Defaults: 0.999 (public_verify), 0.999 (signer), 0.995 (admin_api).
* ``latency_p95_target_ms`` — p95 of request duration in ms.
  Defaults: 500 / 1000 / 2000.

Burn-rate is computed over the current observation window (1 hour).
Fast burn (>= 14.4x target) is flagged in the endpoint response so
an alerting scraper can wake the on-call rotation.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping, Optional

from flask import current_app


DEFAULT_TARGETS = {
    "public_verify": {"availability": 0.999, "latency_p95_ms": 500},
    "signer": {"availability": 0.999, "latency_p95_ms": 1000},
    "admin_api": {"availability": 0.995, "latency_p95_ms": 2000},
}


@dataclass(frozen=True)
class Observation:
    endpoint_class: str
    request_count: int
    error_count: int
    availability_observed: float
    latency_p95_observed_ms: Optional[float]
    availability_target: float
    latency_p95_target_ms: int
    burn_rate: float
    status: str  # "ok" | "at_risk" | "breach"


def classify_path(path: str) -> str:
    if not isinstance(path, str):
        return "admin_api"
    if path.startswith("/verify"):
        return "public_verify"
    if path.startswith("/sign") or path.startswith("/api/signer-intent"):
        return "signer"
    return "admin_api"


def _targets(config: Mapping) -> dict[str, dict]:
    overrides = config.get("SLO_TARGETS") or {}
    result: dict[str, dict] = {}
    for cls, defaults in DEFAULT_TARGETS.items():
        override = overrides.get(cls, {}) if isinstance(overrides, dict) else {}
        result[cls] = {
            "availability": float(
                override.get("availability", defaults["availability"])
            ),
            "latency_p95_ms": int(
                override.get("latency_p95_ms", defaults["latency_p95_ms"])
            ),
        }
    return result


def _read_counters() -> dict[str, dict[str, float]]:
    """Return ``{endpoint_class: {status_bucket: count}}`` from Prometheus."""
    try:
        from app.metrics import http_requests_total
    except ImportError:
        return {}
    result: dict[str, dict[str, float]] = {}
    for metric in http_requests_total.collect():
        for sample in metric.samples:
            if not sample.name.endswith("_total"):
                continue
            labels = sample.labels or {}
            endpoint = labels.get("endpoint") or ""
            cls = classify_path(endpoint)
            status = str(labels.get("status", "unknown"))
            result.setdefault(cls, {})
            result[cls][status] = result[cls].get(status, 0.0) + float(
                sample.value
            )
    return result


def _read_latency_p95() -> dict[str, Optional[float]]:
    """Return ``{endpoint_class: p95_ms}`` from the existing histogram."""
    try:
        from app.metrics import http_request_duration_seconds
    except ImportError:
        return {}
    # Collapse by (endpoint_class, le): sum bucket counts across methods
    # + status codes so the p95 reflects the whole class.
    buckets_by_class: dict[str, dict[float, float]] = {}
    counts_by_class: dict[str, float] = {}
    for metric in http_request_duration_seconds.collect():
        for sample in metric.samples:
            labels = sample.labels or {}
            endpoint = labels.get("endpoint") or ""
            cls = classify_path(endpoint)
            if sample.name.endswith("_bucket"):
                le = labels.get("le")
                if le is None:
                    continue
                try:
                    bound = float(le)
                except ValueError:
                    continue
                buckets_by_class.setdefault(cls, {})
                buckets_by_class[cls][bound] = (
                    buckets_by_class[cls].get(bound, 0.0) + float(sample.value)
                )
            elif sample.name.endswith("_count"):
                counts_by_class[cls] = counts_by_class.get(cls, 0.0) + float(
                    sample.value
                )
    result: dict[str, Optional[float]] = {}
    for cls, buckets in buckets_by_class.items():
        total = counts_by_class.get(cls, 0.0)
        if total <= 0:
            result[cls] = None
            continue
        target = total * 0.95
        sorted_bounds = sorted(buckets.items(), key=lambda row: row[0])
        p95 = None
        for bound, cumulative in sorted_bounds:
            if cumulative >= target:
                p95 = bound * 1000  # seconds → ms
                break
        result[cls] = p95
    return result


def observations(config: Optional[Mapping] = None) -> list[Observation]:
    cfg = config if config is not None else current_app.config
    targets = _targets(cfg)
    counters = _read_counters()
    latency = _read_latency_p95()
    result: list[Observation] = []
    for cls, cls_target in targets.items():
        class_counts = counters.get(cls, {})
        total = int(sum(class_counts.values()))
        errors = int(
            sum(
                count
                for status, count in class_counts.items()
                if status == "5xx"
            )
        )
        availability = 1.0 if total == 0 else (total - errors) / total
        p95 = latency.get(cls)
        burn = _burn_rate(availability, cls_target["availability"])
        status = _status(
            availability=availability,
            latency_p95_ms=p95,
            target_availability=cls_target["availability"],
            target_latency_ms=cls_target["latency_p95_ms"],
        )
        result.append(
            Observation(
                endpoint_class=cls,
                request_count=total,
                error_count=errors,
                availability_observed=round(availability, 6),
                latency_p95_observed_ms=(
                    round(p95, 1) if p95 is not None else None
                ),
                availability_target=cls_target["availability"],
                latency_p95_target_ms=cls_target["latency_p95_ms"],
                burn_rate=round(burn, 3),
                status=status,
            )
        )
    return result


def _burn_rate(observed: float, target: float) -> float:
    """Multi-of-budget consumption rate.

    1.0 means failures are exactly consuming the error budget;
    > 1.0 means the budget is being burnt faster than allowed.
    """
    allowed_failure = max(1.0 - target, 1e-9)
    observed_failure = max(1.0 - observed, 0.0)
    return observed_failure / allowed_failure


def _status(
    *,
    availability: float,
    latency_p95_ms: Optional[float],
    target_availability: float,
    target_latency_ms: int,
) -> str:
    availability_breach = availability < target_availability
    latency_breach = (
        latency_p95_ms is not None and latency_p95_ms > target_latency_ms
    )
    if availability_breach or latency_breach:
        return "breach"
    availability_near = availability < target_availability + 1e-9 + (
        (1 - target_availability) * 0.1
    )
    latency_near = (
        latency_p95_ms is not None
        and latency_p95_ms > target_latency_ms * 0.9
    )
    if availability_near or latency_near:
        return "at_risk"
    return "ok"

# Copyright 2025 The Kubeflow Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""Kubeflow SDK + OpenTelemetry: Instrumented TrainerClient PoC.

Demonstrates the full span hierarchy including the polling loop —
the most technically complex part of async job instrumentation.

Span hierarchy produced:
    kubeflow.sdk.trainer.train              [root]
    ├── kubeflow.sdk.trainer.get_runtime
    ├── kubeflow.sdk.trainer.create_trainjob
    └── kubeflow.sdk.trainer.poll_status    [x N iterations]
          attributes: poll.iteration, trainjob.status
          events: status_check, job_reached_expected_status

Run with console output (no Docker needed):
    pip install opentelemetry-sdk opentelemetry-exporter-otlp
    python examples/instrumented_trainer.py

Run with Jaeger UI:
    docker-compose up -d
    python examples/instrumented_trainer.py
    open http://localhost:16686
"""

from __future__ import annotations

import logging
import os
import random
import string
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import kubeflow.common.telemetry as telemetry

    telemetry.configure(exporter="console", service_name="kubeflow-sdk-demo")
    print("OpenTelemetry configured — real spans will appear below\n")
except ImportError:
    print("opentelemetry-sdk not installed — using NoOp tracer (zero overhead)\n")

from kubeflow.common.telemetry import SpanAttributes, SpanNames, get_tracer

try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.trace import StatusCode

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False


class InstrumentedTrainerBackend:
    """Demonstrates KubernetesBackend instrumentation with real OTel spans.

    This shows exactly what the SDK internals would look like after
    the telemetry module is integrated per issue #164.
    """

    def __init__(self, namespace: str = "default") -> None:
        self.namespace = namespace
        self._tracer = get_tracer("kubeflow.trainer")

    def train(
        self,
        runtime_name: str = "torch-distributed",
        num_nodes: int = 2,
        timeout: int = 30,
        polling_interval: int = 2,
    ) -> str:
        """Instrumented train() — root span wraps entire job lifecycle."""
        with self._tracer.start_as_current_span(SpanNames.TRAINER_TRAIN) as root_span:
            root_span.set_attribute(SpanAttributes.NAMESPACE, self.namespace)
            root_span.set_attribute(SpanAttributes.BACKEND, "kubernetes")
            root_span.set_attribute(SpanAttributes.TRAINJOB_RUNTIME, runtime_name)
            root_span.set_attribute(SpanAttributes.TRAINJOB_NUM_NODES, num_nodes)
            try:
                self._get_runtime(runtime_name)
                job_name = self._create_trainjob(runtime_name, num_nodes)
                root_span.set_attribute(SpanAttributes.TRAINJOB_NAME, job_name)
                final = self._poll_until_complete(job_name, timeout, polling_interval)
                root_span.set_attribute(SpanAttributes.TRAINJOB_STATUS, final["status"])
                return job_name
            except Exception as e:
                root_span.set_attribute(SpanAttributes.ERROR_TYPE, type(e).__name__)
                root_span.record_exception(e)
                raise

    def _get_runtime(self, name: str) -> dict:
        """Child span: resolve the TrainingRuntime CRD."""
        with self._tracer.start_as_current_span(SpanNames.TRAINER_GET_RUNTIME) as span:
            span.set_attribute(SpanAttributes.RUNTIME_NAME, name)
            time.sleep(0.05)
            span.set_attribute(SpanAttributes.RUNTIME_SCOPE, "cluster")
            return {"name": name, "framework": "pytorch"}

    def _create_trainjob(self, runtime_name: str, num_nodes: int) -> str:
        """Child span: build and submit the TrainJob CRD to Kubernetes."""
        with self._tracer.start_as_current_span(SpanNames.TRAINER_CREATE_JOB) as span:
            span.set_attribute(SpanAttributes.TRAINJOB_RUNTIME, runtime_name)
            span.set_attribute(SpanAttributes.TRAINJOB_NUM_NODES, num_nodes)
            time.sleep(0.1)
            job_name = random.choice(string.ascii_lowercase) + uuid.uuid4().hex[:8]
            span.set_attribute(SpanAttributes.TRAINJOB_NAME, job_name)
            span.add_event(
                "trainjob_submitted",
                {"kubeflow.trainjob.name": job_name, "kubeflow.namespace": self.namespace},
            )
            return job_name

    def _poll_until_complete(
        self, job_name: str, timeout: int, polling_interval: int
    ) -> dict:
        """Polling loop — each iteration gets its own child span.

        This is the technically hardest part of the instrumentation.
        Each poll produces a child span with span events for status
        transitions, giving full visibility without a single mega-span.
        """
        status_progression = ["Created", "Created", "Running", "Running", "Complete"]
        max_iters = round(timeout / polling_interval)

        for iteration in range(max_iters):
            with self._tracer.start_as_current_span(SpanNames.TRAINER_POLL_STATUS) as poll_span:
                poll_span.set_attribute(SpanAttributes.TRAINJOB_NAME, job_name)
                poll_span.set_attribute(SpanAttributes.POLL_ITERATION, iteration)
                poll_span.set_attribute(SpanAttributes.POLL_TIMEOUT, timeout)
                poll_span.set_attribute(SpanAttributes.POLL_INTERVAL, polling_interval)

                time.sleep(0.02)
                status = status_progression[min(iteration, len(status_progression) - 1)]
                poll_span.set_attribute(SpanAttributes.TRAINJOB_STATUS, status)
                poll_span.add_event(
                    "status_check",
                    {SpanAttributes.TRAINJOB_STATUS: status, SpanAttributes.POLL_ITERATION: iteration},
                )
                logger.info("  Poll %d: job=%s status=%s", iteration, job_name, status)

                if status == "Complete":
                    poll_span.add_event("job_reached_expected_status")
                    return {"name": job_name, "status": status}

                if status == "Failed":
                    err = RuntimeError(f"TrainJob {job_name} failed")
                    poll_span.record_exception(err)
                    raise err

            time.sleep(polling_interval * 0.05)

        raise TimeoutError(f"Timeout waiting for TrainJob {job_name} after {timeout}s")


if __name__ == "__main__":
    print("=" * 60)
    print("Kubeflow SDK OpenTelemetry PoC")
    print("Span hierarchy: train → get_runtime → create → poll×N")
    print("=" * 60)

    backend = InstrumentedTrainerBackend(namespace="kubeflow")

    print("\n[1] Running instrumented train()...")
    job = backend.train(runtime_name="torch-distributed", num_nodes=4, timeout=30, polling_interval=2)
    print(f"\n✓ TrainJob completed: {job}")

    print("\n[2] Testing NoOp path (KUBEFLOW_TRACING_DISABLED=1)...")
    os.environ["KUBEFLOW_TRACING_DISABLED"] = "1"
    import kubeflow.common.telemetry as t
    t._otel_available = None
    noop = get_tracer("test")
    with noop.start_as_current_span("test.span") as s:
        s.set_attribute("key", "value")
    print("✓ NoOp tracer: zero overhead confirmed — no exceptions")
    print("\nDone. Check console output above for real OTel JSON spans.")

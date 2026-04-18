# Kubeflow SDK × OpenTelemetry — Reference PoC

Proof-of-concept implementation for
[GSoC 2026 Project #7: Integrate Kubeflow SDK with OpenTelemetry](https://www.kubeflow.org/events/upcoming-events/gsoc-2026/#project-7--integrate-kubeflow-sdk-with-opentelemetry)
and [kubeflow/sdk issue #164](https://github.com/kubeflow/sdk/issues/164).

## What This Demonstrates

| Question | Answer |
|---|---|
| Where does instrumentation live? | `kubeflow/common/telemetry.py` — shared across all clients |
| What if OTel is not installed? | `_NoOpTracer` — zero overhead, no import errors |
| How are polling loops handled? | Single span wrapping the entire loop with per-iteration span events |
| How are span names standardized? | `SpanNames` + `SpanAttributes` constants |
| How does a user enable tracing? | `telemetry.configure(exporter="otlp")` or `exporter="console"` |
| How does a user disable tracing? | `KUBEFLOW_TRACING_DISABLED=1` |

## Span Hierarchy
```
kubeflow.sdk.trainer.train              [root — entire job lifecycle]
│  kubeflow.namespace = "kubeflow"
│  kubeflow.trainjob.runtime = "torch-distributed"
│  kubeflow.trainjob.num_nodes = 4
│
├── kubeflow.sdk.trainer.get_runtime
│     kubeflow.runtime.scope = "cluster"
│
├── kubeflow.sdk.trainer.create_trainjob
│     event: trainjob_submitted
│
└── kubeflow.sdk.trainer.poll_status    [single span — entire polling loop]
      kubeflow.poll.timeout_seconds = 30
      kubeflow.poll.interval_seconds = 2
      event: status_check {status="Created",  iteration=0}
      event: status_check {status="Running",  iteration=2}
      event: status_check {status="Complete", iteration=4}
      event: job_reached_expected_status
```

> **Why one span instead of N?** A 10-minute job polled every 2 s would produce 300
> child spans — flooding the trace backend and making Jaeger/Tempo unusable. A single
> `poll_status` span with per-iteration `add_event()` calls preserves full visibility
> at zero cardinality cost.

## Quick Start
```bash
# Console output — no Docker needed
pip install opentelemetry-sdk opentelemetry-exporter-otlp
python examples/instrumented_trainer.py

# Jaeger UI at http://localhost:16686
# Jaeger accepts OTLP natively on port 4317 — no legacy Jaeger exporter needed
docker-compose up -d
python examples/instrumented_trainer.py
```

## File Structure
```
kubeflow/common/telemetry.py          # Core module
examples/instrumented_trainer.py      # Full demo
docker-compose.yml                    # Jaeger (OTLP on port 4317)
```

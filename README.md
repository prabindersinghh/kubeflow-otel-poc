# Kubeflow SDK × OpenTelemetry — Reference PoC

Proof-of-concept implementation for
[GSoC 2026 Project #7: Integrate Kubeflow SDK with OpenTelemetry](https://www.kubeflow.org/events/upcoming-events/gsoc-2026/#project-7--integrate-kubeflow-sdk-with-opentelemetry)
and [kubeflow/sdk issue #164](https://github.com/kubeflow/sdk/issues/164).

## What This Demonstrates

| Question | Answer |
|---|---|
| Where does instrumentation live? | `kubeflow/common/telemetry.py` — shared across all clients |
| What if OTel is not installed? | `_NoOpTracer` — zero overhead, no import errors |
| How are polling loops handled? | Per-iteration child spans + span events |
| How are span names standardized? | `SpanNames` + `SpanAttributes` constants |
| How does a user enable tracing? | `telemetry.configure(exporter="jaeger")` |
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
├── kubeflow.sdk.trainer.poll_status    [iteration 0]
│     kubeflow.trainjob.status = "Created"
│     event: status_check
│
├── kubeflow.sdk.trainer.poll_status    [iteration 2]
│     kubeflow.trainjob.status = "Running"
│     event: status_check
│
└── kubeflow.sdk.trainer.poll_status    [iteration 4]
      kubeflow.trainjob.status = "Complete"
      events: status_check, job_reached_expected_status
```

## Quick Start
```bash
# Console output — no Docker needed
pip install opentelemetry-sdk opentelemetry-exporter-otlp
python examples/instrumented_trainer.py

# Jaeger UI at http://localhost:16686
docker-compose up -d
python examples/instrumented_trainer.py
```

## File Structure
```
kubeflow/common/telemetry.py          # Core module
examples/instrumented_trainer.py      # Full demo
docker-compose.yml                    # Jaeger setup
```

# Kubeflow SDK × OpenTelemetry — Reference PoC

![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-instrumented-blueviolet?logo=opentelemetry)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![GSoC 2026](https://img.shields.io/badge/GSoC-2026-orange?logo=google)

Reference implementation for native OpenTelemetry instrumentation in the Kubeflow Python SDK — built as part of GSoC 2026 Project #7.

---

## Overview

This repository demonstrates a production-ready approach to integrating OpenTelemetry tracing into the Kubeflow Python SDK, addressing [kubeflow/sdk issue #164](https://github.com/kubeflow/sdk/issues/164). The design is zero-overhead when OTel is absent, uses a single shared instrumentation layer across all SDK clients, and handles the full async job lifecycle including polling loops.

---

## What This Demonstrates

| Design Question | Decision |
|---|---|
| Where does instrumentation live? | `kubeflow/common/telemetry.py` — shared across all SDK clients |
| What if OTel is not installed? | `_NoOpTracer` singleton — zero overhead, no import errors |
| How are polling loops handled? | Single span wrapping the entire loop with per-iteration span events |
| How are span names standardized? | `SpanNames` + `SpanAttributes` constants — no raw strings anywhere |
| How does a user enable tracing? | `telemetry.configure(exporter="otlp")` or `exporter="console"` |
| How does a user disable tracing? | `KUBEFLOW_TRACING_DISABLED=1` env var |

---

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

> **Why one span instead of N?**
> A 10-minute job polled every 2 s would produce 300 child spans — flooding the trace
> backend and making Jaeger/Tempo unusable. A single `poll_status` span with
> per-iteration `add_event()` calls preserves full visibility at zero cardinality cost.

---

## Quick Start

**Console output — no Docker needed**
```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp
python examples/instrumented_trainer.py
```

**With Jaeger UI** — Jaeger accepts OTLP natively on port 4317, no legacy exporter needed
```bash
docker-compose up -d
python examples/instrumented_trainer.py
# Open http://localhost:16686
```

---

## File Structure

```
kubeflow/common/telemetry.py          # Core instrumentation module — get_tracer(), configure(), SpanNames, SpanAttributes, _NoOpTracer
examples/instrumented_trainer.py      # End-to-end demo simulating the full KubernetesBackend.train() lifecycle
docker-compose.yml                    # Jaeger all-in-one with OTLP receiver on port 4317
```

---

## Related

| Resource | Link |
|---|---|
| kubeflow/sdk Issue #164 — OTel integration tracking | [github.com/kubeflow/sdk/issues/164](https://github.com/kubeflow/sdk/issues/164) |
| PR #401 — Telemetry module (open for review) | [github.com/kubeflow/sdk/pull/401](https://github.com/kubeflow/sdk/pull/401) |
| PR #402 — Polling interval validation fix (merged) | [github.com/kubeflow/sdk/pull/402](https://github.com/kubeflow/sdk/pull/402) |

---

## License

[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)

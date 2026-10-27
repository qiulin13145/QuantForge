# Backend protocol

The configuration identifies each backend as an argument array. QuantForge sends one JSON object to stdin and expects one JSON object on stdout. `{config_dir}` in an argument expands to the directory containing the configuration file. Each backend runs as a separate process with the configured timeout.

## Proposer

Requests contain `phase`, `context`, `prompt`, and `json_schema`. The `proposal` phase returns:

```json
{
  "source": "def run(x):\n    return x + 1\n",
  "explanations": [{"id": "focal", "claim": "..."}, {"id": "alternative", "claim": "..."}],
  "conditions": [
    {"id": "primary", "kind": "primary", "cost": 1, "predictions": {"focal": "gain", "alternative": "gain"}},
    {"id": "control", "kind": "control", "cost": 1, "source": "def run(x):\n    return x\n", "predictions": {"focal": "loss", "alternative": "gain"}}
  ]
}
```

The first explanation is the focal one. Every condition predicts one category per explanation. A control supplies complete executable source. Condition costs are positive integer evaluator-call units; the minimum-cost compiler validates that the chosen conditions separate all explanation pairs before any candidate evaluation.

The `response` phase receives the verdict, required response, candidate source and measured results. It returns `source` and a `next_residual` with `id`, `question`, `scope`, and `probe_input`. The scope is a top-level synchronous function in the submitted Python source. A probe input is passed as the function's sole argument, or as `{"args": [...], "kwargs": {...}}` for multiple arguments.

## Evaluator

An evaluator receives `source`, `parent_source`, `parent_score`, `condition`, `contract`, and `phase`. The parent score is null during initial baseline evaluation. It returns:

```json
{"success": true, "safe": true, "score": 0.1, "outcome": "gain", "signature": true}
```

`score` is finite and is compared according to `direction` in the configuration. `outcome` must use the same categorical vocabulary as the proposal's predictions. `signature` says whether the target mechanism's signal was observed. The evaluator is responsible for enforcing the frozen task contract and measuring each condition on the same basis.

For `phase: "probe"`, `condition` also includes the verdict, required response, tested candidate source, primary condition, and execution trace summary. The evaluator must return `response_valid: true` only when the successor satisfies its task-specific response check. For `phase: "measurement"`, it measures the changed program and returns the normal result fields.

QuantForge invokes candidate Python in subprocesses. Run candidate code under an isolation mechanism appropriate for the environment; a Python subprocess alone has the caller's permissions.

## Recovery

State is written atomically after each completed backend call. Completed calls are tied to their request hashes and are not replayed when `step` is resumed. A call interrupted while executing is charged to the budget and recorded as in flight. After checking the external process, use `quantforge recover WORKSPACE` and rerun `step`; a new call consumes another budget unit.

Use `quantforge retry WORKSPACE KEY` to retry a recorded failed call, or `quantforge abort WORKSPACE` to abandon the pending round. Already spent calls remain charged. These commands operate on the local run, not on the repository.

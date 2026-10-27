# Design your own algorithm

QuantForge separates the search loop from the problem being solved. To use it on a new task, define an initial Python program, a task-specific evaluator, and a configuration describing the objective and the first open question.

## Start from a working example

The [bin-packing example](../examples/binpacking/) searches for a heuristic that places integer items into as few fixed-capacity bins as possible. Its initial program uses next-fit; its evaluator checks that every item is packed exactly once, no bin exceeds capacity, and the score is the mean number of bins on fixed instances.

```bash
cp -R examples/binpacking my-task
```

The copied directory contains three files to adapt:

- **`baseline.py`** defines the initial algorithm. Replace `pack(items, capacity)` with a synchronous, top-level Python function for your task.
- **`evaluator.py`** executes a candidate under the task contract, checks its validity, measures its score, and reports experiment outcomes. Adapt both the normal evaluation and the `probe` response check to your problem.
- **`config.json`** points to the initial program and backend commands. Set the task description and fixed evaluation conditions in `contract`, the score `direction`, and the evaluator-call `budget`.

In `initial_residual`, give the first design question, set `scope` to the function name, and provide a `probe_input` that calls that function. For multiple arguments, use `{"args": [...], "kwargs": {...}}`. Probe arguments and the function's return value must be JSON-serializable. The probe executes the revised function and checks that changed lines in that function were reached. In the bin-packing example, keep `contract.probe_items` consistent with `probe_input` when changing the witness.

## Define useful evidence

Your evaluator receives the candidate and parent source, the selected condition, the frozen task contract, and the current phase. It returns a score, a categorical `outcome`, and a boolean `signature`. Record the outcome categories and what the signature means in `contract`, so the proposer can predict them before execution. The bin-packing example uses `gain`, `unchanged`, and `loss` relative to the parent.

For the `probe` phase, the evaluator also receives the verdict, required response, candidate source, and execution trace. Its `response_valid` field is the task-specific check that the revision responds to that verdict. The example compares packing behavior on a probe instance; adapt the check to the evidence and failure modes that matter for your problem.

See the [backend protocol](backends.md) for the full request and response formats. Proposers and evaluators are commands, so you can use the included Codex adapter or supply your own implementation.

## Run

After editing the files, initialize a fresh workspace and run a round:

```bash
quantforge init runs/my-task --config my-task/config.json
quantforge step runs/my-task
quantforge status runs/my-task
```

Run `step` again to continue. The workspace stores its own programs, experiment packets, results, and budget; paths in the configuration are resolved relative to the configuration directory. The included proposer requires an authenticated [Codex CLI](https://github.com/openai/codex).

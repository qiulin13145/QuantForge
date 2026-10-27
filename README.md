# QuantForge

QuantForge is an evidence-guided search framework for executable algorithms. It maintains a frontier of programs and a frontier of unresolved design questions. Each round registers competing explanations, selects distinguishing controls, resolves their predictions against measured outcomes, and checks the resulting code response before measuring the revised program.

The framework follows [QuantForge: Discovering Residual Decompositions for MXFP4 Post-Training Quantization](https://arxiv.org/abs/2609.34680). Proposers and evaluators are replaceable commands; their inputs and outputs are JSON. The included Block32 example shows how to connect a quantization objective.

## Install

Python 3.10 or newer on macOS or Linux is required.

```bash
git clone https://github.com/qiulin13145/QuantForge.git
cd QuantForge
python3 -m pip install -e .
```

## Start a search

Create a configuration with an initial Python program, an initial residual, a frozen evaluation contract, and commands for the proposer and evaluator. The included configuration uses the Codex CLI proposer and a Block32 evaluator:

```bash
quantforge init runs/block32 --config examples/block32/config.json
quantforge step runs/block32
quantforge status runs/block32
```

`step` completes one round. Run it again to continue from the open residual. The Codex proposer requires an authenticated `codex` command. Set `QUANTFORGE_CODEX_MODEL` to select a model, or replace the proposer command with another implementation of the same interface.

Each workspace stores its own state, programs, frozen packets, results, and call budget. The state is local to the run; `runs/` is ignored by Git. A single writer lock prevents simultaneous changes to one workspace.

## Search cycle

1. Select a retained program and an open residual.
2. Propose a candidate, competing explanations, predictions, and controls.
3. Freeze the experiment and select the minimum-cost distinguishing controls.
4. Evaluate the primary and controls under the same contract, then resolve a verdict.
5. Retain useful candidates independently of the verdict. For a response-bearing verdict, request a successor, check that its target function changed, execute the changed lines with a probe, and ask the evaluator to check the response.
6. Remeasure the successor and open its next residual.

The [backend protocol](docs/backends.md) specifies the JSON interfaces, the evaluator's response check, and the workspace recovery commands. The [paper protocol](docs/paper-protocol.md) maps the two discovery settings in the paper to evaluator requirements.

## Citation

```bibtex
@article{shang2026quantforge,
  title={QuantForge: Discovering Residual Decompositions for MXFP4 Post-Training Quantization},
  author={Shang, Qiulin and Wu, Zhoutong and Hu, Jie and Yuan, Kun},
  journal={arXiv preprint arXiv:2609.34680},
  year={2026}
}
```

## License

MIT. See [LICENSE](LICENSE).

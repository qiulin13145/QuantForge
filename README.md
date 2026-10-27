<h1 align="center">QuantForge</h1>

<p align="center">
  <strong>Discovering algorithms through evidence-guided program evolution</strong>
</p>

<p align="center">
  Turn competing explanations into targeted experiments, verified code revisions, and the next algorithmic insight.
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2609.34680"><img src="https://img.shields.io/badge/arXiv-2609.34680-b31b1b.svg" alt="arXiv paper"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10 or newer"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22a06b.svg" alt="MIT license"></a>
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2609.34680">Paper</a> ·
  <a href="#how-it-works">How It Works</a> ·
  <a href="#a-control-that-changed-the-next-design">Case Study</a> ·
  <a href="#the-discovered-algorithm-hires">HiRes</a> ·
  <a href="#paper-results">Results</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="docs/backends.md">Documentation</a>
</p>

<p align="center">
  Qiulin Shang · Zhoutong Wu · Jie Hu · Kun Yuan<br>
  Peking University
</p>

---

**QuantForge** is a framework for discovering executable algorithms. It combines program evolution with controlled experiments: useful programs are retained by performance, while evidence decides what to change next.

In our [paper](https://arxiv.org/abs/2609.34680), QuantForge discovers **HiRes**, a hierarchical MXFP4 post-training quantization algorithm. Under a matched search budget, it reaches a held-out transfer target in **6 of 8 runs**, compared with **3 of 8** for reflection memory.

<p align="center">
  <img src="assets/quantforge-overview.svg" width="100%" alt="QuantForge overview: programs and evidence co-evolve through targeted experiments and residual compilation">
</p>

<p align="center"><em>QuantForge retains effective programs while controlled evidence guides their next revision.</em> <a href="assets/quantforge-overview.pdf">Original figure · PDF</a></p>

## How It Works

QuantForge builds a search around a simple question: **what should the next program change, and what evidence supports that change?**

1. **Track programs and open questions.** Keep an executable frontier of useful candidates alongside a residual frontier of unresolved design questions.
2. **Test competing explanations.** Register predictions before execution and select the lowest-cost controls that distinguish them.
3. **Turn verdicts into code.** Use the experimental result to direct a successor, then check the changed computation with an execution probe and a task-specific response check.
4. **Measure again.** Evaluate the revised program and use its remaining errors to open the next question.

The search is built around a frozen task contract and supports interchangeable proposer and evaluator commands. Local run state keeps the experiment packet, program lineage, budget, and evidence together across rounds.

## A Control That Changed the Next Design

On Qwen3-4B, the search encountered unusually large activation-quantization error in `down_proj`. Was it caused by **which channels shared a Block32 exponent**, or by the tensor's **global dynamic range**? A function-preserving permutation separated the two explanations and changed the next code revision.

<p align="center">
  <img src="assets/control-guided.gif" width="100%" alt="Animated paper example: observe a quantization residual, run a channel-permutation control, and use its verdict to guide the next program">
</p>

The control supported the block-membership explanation. A verdict-guided successor equalized channels according to their contribution to the shared exponent; a free-reflection successor widened the scale search. Both used the same parent and evidence. PPL is measured on the **search-visible Qwen3-4B**; contaminated blocks have a within-block maximum-to-median magnitude ratio greater than 32. See the [paper's verdict-guided example](https://arxiv.org/html/2609.34680v1#A4.SS2.SSS0.Px2.p3).

## The Discovered Algorithm: HiRes

QuantForge's paper develops **HiRes** as three successive responses to measured quantization residuals. Each stage acts on the model realized by the preceding stage.

<p align="center">
  <img src="assets/hires-equations.png" width="100%" alt="HiRes equations for geometric shaping, discrete realization, and attention and MLP structural recovery">
</p>

<p align="center"><a href="assets/hires-equations.svg">View equations in vector format</a></p>

<details>
<summary>Copy the core equations · LaTeX</summary>

```latex
U = D R_H G P_{\mathrm{ref}},
\quad \widetilde X = XU^{\top},\quad \widetilde W = WU^{-1}.

\Delta(i,c) = 2\delta_{ic}[G_Q d_0-K_Q x]_i
              + \delta_{ic}^{2}[G_Q]_{ii}.

\overline{\mathbf v}_t = a\mathbf v_t+b\mathbf 1,
\quad \overline m = \operatorname{SiLU}\left((1+\beta)g
                    + \alpha\sigma_g\right)\odot(1+\eta)u.
```
</details>

See [Section 5 of the paper](https://arxiv.org/html/2609.34680v1#S5) for definitions and the complete algorithm.

## Paper Results

### Evidence-guided discovery

With the same **240-call search budget** and **eight paired seeds**, QuantForge achieves the strongest held-out result among the compared search methods:

<p align="center">
  <img src="assets/search-progress.png" width="100%" alt="Paper Figure 2: held-out perplexity during search and final results at 240 evaluator calls">
</p>

Search uses Qwen3-4B; transfer is measured on held-out Llama-3.1-8B WikiText-2. QuantForge spends 141 calls on new programs and 99 on controls and compliance probes. Held-out evaluations are performed separately and are not included in the 240-call search budget. See [Section 6.2](https://arxiv.org/html/2609.34680v1#S6.SS2) for the protocol.

### HiRes: a discovered MXFP4 quantizer

Across seven models and seven tasks, HiRes obtains the best **Robust Fit: 0.09300**, compared with 0.09910 for WUSH. It has the lowest Fit-7 on six of the seven models; WUSH leads on Qwen3-4B.

<p align="center">
  <img src="assets/hires-table1.svg" width="100%" alt="Paper Table 1, restyled: HiRes and nine baselines across seven models, mean Fit-7 and Robust Fit">
</p>

<p align="center"><em>Paper Table 1, restyled. Fit-7 combines mean and worst-task damage; Robust Fit applies the same aggregation across models. Lower is better.</em></p>

<details>
<summary>Stage progression and ablations · paper Table 2</summary>
<p align="center"><img src="assets/paper-fit3-ablation.png" width="100%" alt="Paper Table 2: Fit-3 across HiRes stages and ablations on Qwen3-8B and Llama-3-8B"></p>
</details>

These are **paper results** under the shared strict MXFP4 W4A4 evaluation contract. See [Section 6.1](https://arxiv.org/html/2609.34680v1#S6.SS1) for the complete comparison.

## Quick Start

Install QuantForge with Python 3.10 or newer:

```bash
git clone https://github.com/qiulin13145/QuantForge.git
cd QuantForge
python3 -m pip install -e .
```

Start a Block32 search with an authenticated [Codex CLI](https://github.com/openai/codex) proposer:

```bash
quantforge init runs/block32 --config examples/block32/config.json
quantforge step runs/block32
```

Run `quantforge step runs/block32` again to continue the search. Connect your own proposer or objective through the [backend interfaces](docs/backends.md), and explore the [paper protocol](docs/paper-protocol.md) for the model-level evaluation settings.

## Citation

If QuantForge is useful in your research, please cite:

```bibtex
@article{shang2026quantforge,
  title={QuantForge: Discovering Residual Decompositions for MXFP4 Post-Training Quantization},
  author={Shang, Qiulin and Wu, Zhoutong and Hu, Jie and Yuan, Kun},
  journal={arXiv preprint arXiv:2609.34680},
  year={2026}
}
```

## License

Released under the [MIT License](LICENSE).

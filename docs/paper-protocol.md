# Paper protocol

The paper describes two distinct settings. They share the search cycle but differ in their initial program, objective, and information available to search.

| Setting | Initial program | Search-visible objective | Transfer information |
|---|---|---|---|
| Algorithm discovery | GPTQ | Qwen3-4B Fit-3: WikiText-2, C4, ARC-Challenge | Aggregate acceptance against the same comparison program on Llama-3.1-8B |
| Framework comparison | Strict MXFP4 RTN | Qwen3-4B WikiText-2 perplexity | Llama-3.1-8B measurements every 20 evaluator calls, held out from proposal and selection |

To run either setting, supply the corresponding starting program and evaluator. The evaluator owns the model, data, quantization format, calibration, metrics, and resource contract. For the held-out setting, run transfer evaluation separately and do not place its results in the search-visible backend response.

The package provides the controller and a Block32 numerical example. Model checkpoints, datasets, model-level PTQ evaluation, and comparison-arm implementations are provided by the user. Refer to [Appendix A of the paper](https://arxiv.org/html/2609.34680v1#A1) for the full protocols and [Appendix B](https://arxiv.org/html/2609.34680v1#A2) for the MXFP4 execution contract.

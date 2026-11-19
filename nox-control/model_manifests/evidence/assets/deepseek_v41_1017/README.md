# DeepSeek V4.1 tokenizer asset for 4A01

This directory contains the V4.1 tokenizer JSON copied from the pinned official DeepSeek recipe repository. It is a tokenizer input asset for NOX; it does not contain model weights or a training implementation.

## Provenance

- Source: [deepseek-ai/deepseek-recipe](https://github.com/deepseek-ai/deepseek-recipe/tree/935817c66f5d6e64838f419692545f06787e485f)
- Source path: `static/tokenizers/v41/tokenizer.json`
- Immutable source commit: `935817c66f5d6e64838f419692545f06787e485f`
- Git blob SHA-1: `3abdf13e3488acc65e11e6a57f073f6673175c3a`
- File size: 6,367,247 UTF-8 bytes
- Upstream SHA-256: `81f64d1248a68ce3663e07ab3ee48b851e5df0e32d27cb98e4c9a268151e8d99`
- License: MIT, Copyright (c) 2023 DeepSeek. The upstream LICENSE is copied beside the file.
- The upstream README records the image-token reassignment to ID 129264 and says the original import revision was not recorded.

The canonical model is pinned separately to `deepseek-ai/DeepSeek-V4.1-Flash-1017@08c8657f02291e11b6f6b63e0e16014f8e748518`. At that exact model revision, the HF tree omits `tokenizer.json` and `tokenizer_config.json`; the pinned vLLM recipe says 1017 shares the launch checkpoint's tokenizer and prompt encoding. The asset here is the pinned, modified DeepSeek recipe copy; it is not claimed byte-identical to a tokenizer file in the 1017 model repository. Its original import revision was not recorded upstream.

## Training source and limits

The source-adapted NVIDIA recipe and 4A01 source evidence are in [the manifest](../../4A01_DEEPSEEK_V41_1017_TRAINING_SOURCE_20261119.json). That recipe is an 8-node, 64×H100 example, not a V100 training plan. HellaSwag sample limits are pinned in the recipe, but its dataset revision and split-file hashes are not. No model weights, dataset data, or training run are included.

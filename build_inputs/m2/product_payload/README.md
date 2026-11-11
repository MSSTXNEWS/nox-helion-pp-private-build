# product_payload (M2.0-PP)

Real bytes copied from the pinned PRE-PRE source snapshot.

Included and loaded by the app's own code:
- `weights/` — seven research scorers (`VerifiedWeights.load`). They are numeric candidate scorers, not a language model and not a LoRA adapter.
- `helion/data/menu_v2_full_catalog.json` — menu catalog (`load_pinned_menu_source`).
- `helion/data/traits_seed_64.json` — trait seed catalog shipped in the candidate data path.
- `assets/personas_5.json` and `assets/asset_manifest.json` — source catalogs. Pixel files stay in the source `assets/` tree and are not duplicated here.
- `model_config.example.json` — the unbound config the desktop entrypoint accepts (`models` is empty).

Not included, because the bytes are not in this repository:
- Qwen layer `c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515` (397,807,936 bytes)
- tokenizer, adapter, RAG index, cultural index
- an owner-signed license or consent

`GATE_HOLD.json` records that hold. This directory is not product acceptance.

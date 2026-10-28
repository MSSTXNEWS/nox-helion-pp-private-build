# NOX V16 · 12 local video-generation model families · Hardware 16/24 GB
RunID: NOX-V16-VIDEO-CATALOG-20261028

The user corrected the new server memory to **24 GB**, not 254 GB. Current machine: **16 GB**. These are *reported memory amounts*, not verified GPU VRAM. Native E05/E06 GPU guardian must measure actual free VRAM before inference. CPU RAM does not replace GPU VRAM. Nothing in this source installs model weights or establishes that any model fits the current GPU.

## Model catalog (all SOURCE_CATALOG_ONLY, all workflow/weights uninstalled/unverified)
1. Wan 2.1 T2V 1.3B (Apache-2.0): baseline small 480p, official published ~8.19GB GPU requirement on reference.
2. Wan 2.1 VACE 1.3B (Apache-2.0): video edit/conditioning candidate, verify actual node graph.
3. Wan 2.2 TI2V 5B (Apache-2.0): higher quality T2V/I2V, ComfyUI native optimized; official 720p standalone uses 24GB VRAM. No arbitrary 16GB guarantee.
4. Wan 2.2 I2V A14B (Apache-2.0): heavy GPU/large memory, server candidate only after preflight.
5. HunyuanVideo 1.5 T2V (Tencent-Hunyuan Community): high quality, official offloaded GPU minimum 14GB.
6. HunyuanVideo 1.5 I2V (Tencent-Hunyuan Community): image-to-video with same measured GPU gate.
7. Mochi 1 Preview (Apache-2.0): high motion fidelity; lower VRAM ComfyUI workflow requires measured hardware proof.
8. LTX-Video 2B Distilled (checkpoint license REVIEW_REQUIRED): efficient older lightweight model, exact weights terms must be reviewed.
9. LTX 2.5 Fast (LTX-2.x Community): gated licensed weights; LTX Desktop self-hosting requires Windows CUDA 16GB VRAM or more. Optional audio+video.
10. SkyReels V2 I2V 14B (Skywork Community): higher VRAM and license review required.
11. SkyReels V2 Diffusion Forcing (Skywork Community): long-video extension, needs heavy inference/valid workflow.
12. CogVideoX 5B (checkpoint license REVIEW_REQUIRED): fallback, exact license/workflow/VRAM must be reviewed.

**Single runtime**: Existing ComfyUI local 127.0.0.1:8188 port, no new independent image/video server. Source `comfy_video_bridge.py` reuses `ComfyImagePort`. Its requests go only to the approved local ComfyUI /prompt and /history routes. It accepts only a host-authorized, SHA256-pinned workflow graph, installed & license-reviewed source weights, measured free GPU VRAM and measured minimum required VRAM from the trusted native guardian, rights confirmation and no parallel weight-training contention. Jobs return QUEUED_NOT_RENDERED; history returns either NOT_COMPLETE / OUTPUT_MISSING_HOLD / RENDERED_IN_COMFY_NOT_IMPORTED, never false native EXE acceptance. Videos are named files only until the host performs authenticated import.

All models, checkpoint downloads, workflows, custom ComfyUI nodes, LoRAs and providers are **HOLD** until owner validation. User's correction 16/24 is kept as hardware input, no inferred GPU.

No removal or bypass of original NOX consent, AI security, legal or licensing controls. Integration requires #3 model registry, #4 scheduling, #5 sensors, #6 only one host bridge, #7 real Windows same-BuildID/EXE SHA tests. Original D02 HOME and 8 CoreID preserved. Source CI does not mean an actual generated cinematic video.

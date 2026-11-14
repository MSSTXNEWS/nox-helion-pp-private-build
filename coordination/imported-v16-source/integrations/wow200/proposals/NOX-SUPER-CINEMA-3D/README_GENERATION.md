# NOX HELION · LOCAL PHOTO-REAL IMAGE GENERATION BRIDGE
RunID NOX-V16-IMG-COMFY-20261028

SOURCE CANDIDATE — real request/queue/history adapter for **an existing separate local ComfyUI process**, not yet installed in the canonical Windows NOX EXE. It does not download image weights, train any model or claim to have produced an image.

## The exact native architecture
NOX's original chat and shared host remain authoritative. The only allowed network target of LocalTransport is 127.0.0.1:8188; the bridge does **not** expose ComfyUI to public sites or load foreign web pages. Only a trusted native host creates ComfyImagePort; JavaScript must never receive ComfyUI privileges or local file paths. Native user permissions, original security policy and explicit consent remain in force.

ComfyImagePort.prepare() checks: user consent + rights, installed and licensed model with pinned SHA256 from P03 verified artifact registry, preapproved API-format workflow hash and a declared text node, size limits and safe client ID. It changes only the approved text field in a deep copy. The caller must attest/approve **all workflow node classes and model files** before running the graph; a SHA-256 proves identity, not safety. submit() sends a real POST /prompt and returns QUEUED_NOT_RENDERED. result() reads real GET /history/{id}, returning NOT_COMPLETE or RENDERED_IN_COMFY_NOT_IMPORTED. There are no fictional success screens, paid endpoints, safety-filter overrides or unsanctioned weight downloads. The result's image bytes must be imported by the approved host, not interpreted as available in the NOX gallery.

## Ready-made models (available upstream; NOT locally installed by this PR)
1. FLUX.2 [klein] 4B, official Apache 2.0, distilled for image generation and editing. Prefer the official quantized/FP8/GGUF ComfyUI recipe for a 12 GB VRAM card after hardware checks.
2. Qwen-Image-2512, Apache 2.0 (verify exact weights and versions). High quality portrait/text workflows, heavier model and offload may be needed.
3. Stable Diffusion 3.5 Medium, Stability AI Community License (revenue and AUP conditions). Alternative ecosystem and fine-tune routes.

Model licenses are **independent of** ComfyUI licensing. ComfyUI itself is GPL-3.0; this integration keeps it a separate process via HTTP. Distribution or modification of ComfyUI must comply with its license; no blanket proprietary embedding claim. Workflows/custom nodes also require review.

## Why no initial GPU training?
Already trained public image models create photorealistic pictures immediately once installed and compatible. LoRA on approved materials is optional later for consistent owned characters/style. This candidate does not disable safety systems or authorize disallowed generation. A native user-controlled filtering policy, model licensing, rights and applicable law remain separate checks.

## Gate to production
Owner #3: register installed weights, revision, SHA256, real license, VRAM and dependencies. Owner #4: approve workflow/runtime asset provenance, own GPU scheduling. Owner #6: connect this ONE native adapter to the existing images.generate route, give UI host read-only progress and results, no duplicate Web server. Owner #7: verify real RTX 3060 or target Windows hardware at exact EXE BuildID/SHA and one genuine generated image, error/STOP/resource/restart. Pending those gates, route status remains HOLD.

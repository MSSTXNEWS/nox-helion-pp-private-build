# NOX V16 · WOW 1–200 · no-loss source integration

**Target:** PR54 R13 Creative Runtime, itself based on R13 Windows diagnostic `48efe948...`.
**D02:** original four PNGs have hardcoded exact SHA-256 gates in `stage_wow200.py`.
**Source:** exact unchanged Git blobs from PR44, PR38, PR14, PR15, copied into `integrations/wow200/...`; staging writes only a disposable WPF build tree.

## Architecture

- WOW 001–050: actual original 50 P01 route/material presets, bound to existing P01 catalog and **visual previews only**; actions remain handled by the original host, unavailable ones stay HOLD.
- WOW 051–100: source cue engine from PR31.
- WOW 101–150: original WAAPI camera director from PR32.
- WOW 151–200: original composition catalog from PR39 and one unified scene gate PR44, **no duplicate scene renderer**.
- 9-sphere lava/orbital physics PR30 and secondary micro-WOW PR14/15 source code is preserved separately. It cannot be activated on static R13 HOME until an actual approved 9-element DOM rig exists; never invent Core IDs or rewrite D02.
- External 3D/video ComfyUI adapters and 12 video model candidates are preserved as source candidates. A model list is not a working GPU pipeline; no automatic downloads or unknown license bypass.

## Staging

In already verified/disposable `work/e06/staged/R11` (not source archive):

```powershell
python integrations/creative/stage_creative.py work/e06/staged/R11 integrations/creative
python integrations/wow200/stage_wow200.py work/e06/staged/R11 integrations/wow200
```

The second step **rejects** unverified source Git blob bytes, unexpected preimages, duplicate mounting, and any change to D02. It copies the authored `loader.mjs` and original source modules into the already packaged `Assets/creative/wow200/` and extends only secondary `Assets/creative/studio.html`.

## Physical acceptance

Source copied into Git is NOT an installed EXE. Windows host, worker build, actual model downloads and ComfyUI inference, projector devices, mobile HTTPS/private gateway, real chat integration and independent E07 same-EXE acceptance remain separate gated tasks. Prior R13 EXE must remain byte-identical and recoverable.
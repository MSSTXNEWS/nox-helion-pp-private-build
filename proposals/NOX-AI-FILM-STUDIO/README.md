# NOX HELION V16 — AI FILM STUDIO · kino, anime, cartoon, adult anime 18+
RunID: NOX-V16-FILM-STUDIO-20261028
Owner: #1 cinematic UI (source), #2 voice & chat, #3 installed models, #4 inference / RAG, #5 real events, #6 native host integration, #7 final Windows QA.
Status: **SOURCE CANDIDATE**; no completed AI film, installed checkpoints, local GPU movie rendering, native EXE integration or E07 acceptance claimed.

## Physically created
- A separate approved secondary WebView2 film-studio screen `index.html`, `film-studio.css`, `film-studio.js`, with 12 genres, film title and rating, 480p/720p/1080p options, text-to-video models, storyboard timeline, add scenes, soundtrack/dialogue text fields, GUI actions for save/queue/export/projector. Responsive 320–430, 800×480, desktop and 4K scaling. Original D02 HOME unchanged.
- Native `film_studio.py`: validated project and shot schema, actor/character consistency, scene timecodes, 250 scene cap, one-hour chapter limit, named approved source assets, atomic project persistence, actual `ComfyVideoPort.prepare_video` + `queue_video` route of the **existing** image/video COMFY module, and attested output receipts. Never claim a queued clip is rendered.
- Native `render.py`: FFmpeg planned shot-by-shot normalization (H.264/MP4), concat demuxer with portable relative file names and `-safe 1`, SHA-verified owner-authenticated local clip inputs, one MP4 film output, separate SRT dialogue/translation timeline, no shell or arbitrary web URLs. The exporter requires FFmpeg from a trusted installed location, source rights and an explicit user action. Native host must confirm actual media decode and output receipt.
- `voice_timeline` emits timestamped speech segments for the existing native `voice.synthesize` host to use when it becomes available, marked VOICE_NOT_GENERATED until real TTS audio exists. No new TTS provider or voice cloned without consent.
- Human film workflow: write story; name and describe each scene; pick style and models; prepare allowed images; queue shot clips; review/replace bad clips; assemble MP4 + SRT; send approved file to `NOX-PROJECTOR-CINEMA` (existing projector PR) or local player.

## 12 cinematographic styles
1 photoreal 2 anime 3 cartoon_2d 4 cartoon_3d 5 stop_motion 6 manga_motion 7 noir 8 fantasy 9 sci_fi 10 documentary 11 cinematic_3d 12 adult_anime_18.
The last style supports adult animation subject to explicit 18+ approval, sourced/legal content, and explicitly verified adult characters. No sexualized minors or youth-coded sexual content. It does not disable safety filters or model-license requirements. Model providers and source media have separate rights.

## Source/release truth
A frame/clip may take substantial time depending on VRAM, weights, resolution and model. Film creation does NOT require training an image or video model from scratch: reuse already trained ComfyUI-compatible model checkpoints and generate clips sequentially. Offloading RAM does not equal GPU VRAM. Existing current/new-memory reports are 16/24 GB RAM/VRAM type unconfirmed.
UI queues only through `nox.film.command.v1` on explicit user interaction. Without authorized host its buttons are disabled and storyboard is local unsaved work. The user can always inspect the creative workflow. Host MUST validate the existing trusted WebView2 origin, per-user ACL, rights, character age and permit the existing video queue; WebView2 must not be a new privilege boundary.

## Actual release blockers
- A genuine licensed video checkpoint and model-specific signed/verified ComfyUI workflow; real RTX/VRAM preflight; real generated clips and character continuity comparison.
- Native #6 bridge wiring to save/queue/render and film/projector; native #2 synthesis and shot-audio alignment (optional).
- Real FFmpeg installed and signed by trusted host; same-resolution scenes, audio synchronization, and preview on target device; target Windows EXE same SHA independent #7 visual and safety acceptance.
- Final anime/3D quality requires approved character and original 3D asset pipeline. This source has a cinematic interface and working FFmpeg assembly path but does not itself produce photorealistic or anime footage without a generation model.

Run component CI: `python -m unittest discover -s proposals/NOX-AI-FILM-STUDIO -p 'test_*.py' -v`; `node --test proposals/NOX-AI-FILM-STUDIO/test_ui.mjs`. No prior source/asset deletions in this candidate branch.

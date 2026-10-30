# NOX HELION — MASTER READY SOLUTIONS CATALOG · V1.1

Date: 2026-10-30. Scope: EXPRESS INTEGRATOR V16 **and** NOX HELION Release 1. 

## Correctness status
This is a **candidate reuse registry**, not a signed dependency lock, test pass, legal license review, software install or claim that everything is implemented. The Google Drive-wide audit is **PARTIAL**: 705 paragraphs of FIN ZAGR V16 and additional key documents were examined, but not every item in every Drive folder/file. Validate provider availability/licence per pinned release before use.

**Design / security lock:** one WPF/WebView2/NSIS Host, one existing Ollama / SQLite / RAG / events.v3, no duplicate backend, no fake LIVE; preserve bytewise HOME/MENU/WORK/passport images, SourceLock 729/3, D02/WOW200, 8 CoreID, 5 Persona, STOP/ACL/native consent; T02 only shared journal writer. Do not build final EXE before same-SHA T08/T09/T10 source gates. All installed native E07 after real EXE.

## Source document inventory
- [FIN ZAGR V16](https://docs.google.com/document/d/11EM0qW3PJN0WqV8Euc1A2X4c0UukHiVq_0WfaLYVYpc/edit)
- [FULL OWNER FUNCTION + WISHLIST MASTER](https://docs.google.com/document/d/1g7JUanN5lz9ysxOzKO35wXxr399r0oEYQJ09R1hQFjg/edit)
- [ALL PAGES MAX](https://drive.google.com/file/d/1JdEqs0nVIBVFS8nulUAcN-d6ZZCRaoQ9/view)
- [DESIGN MENU V2](https://docs.google.com/document/d/1HGDamioSf-5pxROAik-8VPbJgwO9YXcmD2SRuKmgtWw/edit)
- [CREATIVE STUDIO V5](https://docs.google.com/document/d/1sLmld8svnmSiWDjbnrPCQDII__KFjDrp5ZTaYR9kaOs/edit)
- [CONTROL CENTER SPEC](https://docs.google.com/document/d/1cg8a-on6H-JmmLWcztis2huCh_6BCOzahft4sD7gLeM/edit)
- [WEB RELEASE V1.2](https://docs.google.com/document/d/1FQQiEE0eBMPVoXD3wq0RaChHsZWuc-VqQ2dtyGaLNAQ/edit)
- [Existing MEGAPACK 1 ready-components artifact](https://drive.google.com/file/d/1mdYA-7Aro1j5Bx-cJE1Y_XDcn4XEo-Oj/view)

## Release 1 functional coverage gaps discovered from Drive
| R1 capability | Scope actually demanded | Reuse candidates | Delivery note |
|---|---|---|---|
| Game + AI NPC | playable save/reload; inventory/quests/rewards, authoritative state | Godot, demo projects, SQLite | Mandatory R1, not launcher P0 |
| Multiplayer & co-watch | auth rooms, reconnect, state sync, voice/video | LiveKit, Godot networking, WebRTC/Jitsi | server/auth and licence gate |
| Social & communications | human-vs-AI labels, DMs/groups, moderation, revocation | Matrix/Element, existing NOX Social | adapters, no new social backend by default |
| Calls | contacts/dial/translation/TTS, SIP billing and STOP | SIPSorcery, NAudio, whisper.cpp, PJSIP | actual PSTN requires provider |
| Work OS | tasks, notes, projects, docs, calendar, email, resumes | SQLite, DuckDB, Graph/Gmail, ECharts | OAuth scopes explicit |
| Site & app factory | templates, editor, preview, Git diffs, tests, deploy receipts | Monaco/CodeMirror, Vite/Astro, Playwright | deployment requires consent |
| Creative Studio | books, podcasts, game/3D/video/image/music rights, jobs, export | Godot, Blender, ComfyUI, FFmpeg, OBS, Audacity, Penpot | Creative V5 is a separate spec, no fake revenue |
| Model and training | local inference, download weights, RAG vs LoRA, GPU, rights | Ollama, hub, PEFT, Accelerate, sqlite-vec | preserve existing P02/P04 |
| WebView cinematics | HOME + eight cores, eight MENU groups, 6 FX engines, 10+10+10 | original D02 assets + Motion/OGL/GSAP | no replacement images/faces |
| Control Center | live task scheduler roster, SHA evidence, progress truth | existing NOX data + ECharts/OpenTelemetry | not a second HOME |
| Plugin ecosystem | scopes/version/health, install/revoke, secret vault, budgets | MCP spec/servers, Graph, Gmail, Vercel/Railway | no silent install |
| Windows release | real onehost installer, rollback, 14 native pending, E07 10/10 | WebView2/NSIS/FlaUI/Pester/GitLab | frozen SHA and independent sign-off |

## 8 family registry (name, official source, purpose)
### WINDOWS_INSTALLER_P01
- [Microsoft WebView2 Samples](https://github.com/MicrosoftEdge/WebView2Samples) — WPF host HTML bridge
- [WebView2 official documentation](https://learn.microsoft.com/microsoft-edge/webview2/) — profile/security
- [NSIS](https://github.com/NSIS-Dev/nsis) — retain installer
- [NSIS Modern UI 2](https://nsis.sourceforge.io/Docs/Modern%20UI%202/Readme.html) — wizard components
- [CommunityToolkit.Mvvm](https://github.com/CommunityToolkit/dotnet) — WPF commands
- [Microsoft.Extensions.Hosting](https://learn.microsoft.com/dotnet/core/extensions/generic-host) — DI/lifecycle
- [WinGet CLI](https://github.com/microsoft/winget-cli) — permission-gated updater
- [restic](https://github.com/restic/restic) — existing backup
- [FlaUI](https://github.com/FlaUI/FlaUI) — installed Windows WPF E2E
- [Pester](https://github.com/pester/Pester) — PowerShell tests
- [PSScriptAnalyzer](https://github.com/PowerShell/PSScriptanalyzer) — build lint
- [Velopack](https://github.com/velopack/velopack) — R2 comparison only

### CINEMATIC_SHELL_PAGES
- [Motion](https://github.com/motiondivision/motion) — approved animations
- [GSAP](https://github.com/greensock/GSAP) — motion timelines, licence review
- [OGL](https://github.com/oframe/ogl) — small WebGL
- [Three.js](https://github.com/mrdoob/three.js) — optional existing 3D
- [PixiJS](https://github.com/pixijs/pixijs) — 2D effects
- [Lottie-web](https://github.com/airbnb/lottie-web) — approved animations
- [Fluent UI System Icons](https://github.com/microsoft/fluentui-system-icons) — icons
- [Lucide](https://github.com/lucide-icons/lucide) — icons
- [Fuse.js](https://github.com/krisk/Fuse) — Ctrl+K search
- [Floating UI](https://github.com/floating-ui/floating-ui) — overlay position
- [Apache ECharts](https://github.com/apache/echarts) — real telemetry

### LLM_MODEL_CENTER_P02_P03
- [Ollama](https://github.com/ollama/ollama) — single existing local LLM
- [Ollama API](https://docs.ollama.com/api) — chat/tags/pull/embed
- [OllamaSharp](https://github.com/awaescher/OllamaSharp) — .NET client optional
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — inference alternate, no second live host
- [huggingface_hub](https://github.com/huggingface/huggingface_hub) — download by revision
- [Transformers](https://github.com/huggingface/transformers) — model metadata
- [safetensors](https://github.com/huggingface/safetensors) — safe weights
- [ONNX Runtime](https://github.com/microsoft/onnxruntime) — CPU/GPU optional
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) — image workflow adapter
- [Diffusers](https://github.com/huggingface/diffusers) — image models adapter

### VOICE_CALLS_SOCIAL
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp) — offline ASR
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — ASR GPU candidate
- [Silero VAD](https://github.com/snakers4/silero-vad) — VAD
- [Piper](https://github.com/OHF-Voice/piper1-gpl) — TTS GPL compliance
- [Kokoro](https://github.com/hexgrad/kokoro) — TTS candidate
- [NAudio](https://github.com/naudio/NAudio) — Windows audio
- [Marian NMT](https://github.com/marian-nmt/marian) — offline translation
- [Argos Translate](https://github.com/argosopentech/argos-translate) — offline translation
- [SIPSorcery](https://github.com/sipsorcery-org/sipsorcery) — SIP .NET
- [PJSIP](https://github.com/pjsip/pjproject) — SIP alternate
- [LiveKit](https://github.com/livekit/livekit) — realtime rooms; server/auth required
- [Jitsi Meet](https://github.com/jitsi/jitsi-meet) — external/self-host meeting
- [Matrix Synapse](https://github.com/element-hq/synapse) — social protocol, not R1 backend replacement
- [Element Web](https://github.com/element-hq/element-web) — social UI reference, not full rebrand

### RAG_GPU_LEARNING_P04
- [sentence-transformers](https://github.com/huggingface/sentence-transformers) — embeddings
- [sqlite-vec](https://github.com/asg017/sqlite-vec) — SQLite vectors
- [FAISS](https://github.com/facebookresearch/faiss) — vector index alternative
- [LlamaIndex](https://github.com/run-llama/llama_index) — selective loaders
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) — PDF AGPL/paid gate
- [pypdf](https://github.com/py-pdf/pypdf) — PDF read
- [Unstructured](https://github.com/Unstructured-IO/unstructured) — document extraction
- [PEFT](https://github.com/huggingface/peft) — LoRA
- [TRL](https://github.com/huggingface/trl) — training
- [Accelerate](https://github.com/huggingface/accelerate) — training engine
- [bitsandbytes](https://github.com/bitsandbytes-foundation/bitsandbytes) — GPU compatibility gate
- [Axolotl](https://github.com/axolotl-ai-cloud/axolotl) — trainer configs
- [Unsloth](https://github.com/unslothai/unsloth) — Windows/GPU gating
- [pynvml](https://github.com/gpuopenanalytics/pynvml) — real GPU
- [psutil](https://github.com/giampaolo/psutil) — real CPU/RAM

### CREATIVE_STUDIO_VIDEO_3D_AUDIO
- [Godot](https://github.com/godotengine/godot) — R1 playable game/AI NPC
- [Godot demos](https://github.com/godotengine/godot-demo-projects) — starter game scenes and saves
- [Blender](https://github.com/blender/blender) — 3D authoring
- [Blender Studio](https://studio.blender.org/training/) — 3D animation reference
- [Remotion](https://github.com/remotion-dev/remotion) — programmatic video; licence gate
- [FFmpeg](https://github.com/FFmpeg/FFmpeg) — video processing GPL/LGPL gate
- [OBS Studio](https://github.com/obsproject/obs-studio) — screen capture
- [Audacity](https://github.com/audacity/audacity) — audio editing
- [OpenCV](https://github.com/opencv/opencv) — vision
- [Pillow](https://github.com/python-pillow/Pillow) — images
- [ImageMagick](https://github.com/ImageMagick/ImageMagick) — images; policy limits
- [Tesseract](https://github.com/tesseract-ocr/tesseract) — OCR
- [Penpot](https://github.com/penpot/penpot) — design source/templates
- [GIMP](https://gitlab.gnome.org/GNOME/gimp) — image authoring
- [Krita](https://invent.kde.org/graphics/krita) — drawing
- [LMMS](https://github.com/LMMS/lmms) — music authoring
- [MuseScore](https://github.com/musescore/MuseScore) — score editor

### WORK_OS_SITES_APPS_DATA
- [Monaco Editor](https://github.com/microsoft/monaco-editor) — source editor
- [CodeMirror](https://github.com/codemirror/dev) — lighter editor
- [Vite](https://github.com/vitejs/vite) — web previews/build
- [Astro](https://github.com/withastro/astro) — site templates
- [Next.js](https://github.com/vercel/next.js) — web app templates; avoid 2nd production runtime by default
- [Tauri](https://github.com/tauri-apps/tauri) — R2 compare, not new host
- [DuckDB](https://github.com/duckdb/duckdb) — local analytics
- [Apache Arrow](https://github.com/apache/arrow) — Parquet/Arrow
- [Pandas](https://github.com/pandas-dev/pandas) — data analysis
- [Plotly](https://github.com/plotly/plotly.py) — charts
- [Pandoc](https://github.com/jgm/pandoc) — document conversion
- [LibreOffice](https://www.libreoffice.org/) — office conversion external
- [python-pptx](https://github.com/scanny/python-pptx) — slides
- [python-docx](https://github.com/python-openxml/python-docx) — documents
- [openpyxl](https://openpyxl.readthedocs.io/) — spreadsheets
- [PDF.js](https://github.com/mozilla/pdf.js) — PDF view

### CONNECTORS_AUTONOMY_SECURITY
- [MCP specification](https://modelcontextprotocol.io/) — tool manifests
- [MCP servers](https://github.com/modelcontextprotocol/servers) — reference adapters
- [Microsoft Graph](https://learn.microsoft.com/graph/overview) — Outlook/calendar/contacts auth
- [Gmail API](https://developers.google.com/workspace/gmail/api) — mail after OAuth
- [Google Calendar API](https://developers.google.com/workspace/calendar/api) — calendar after OAuth
- [GitHub REST](https://docs.github.com/rest) — repo-scoped tools
- [Vercel API](https://vercel.com/docs/rest-api) — deploy after approval
- [Railway API](https://docs.railway.com/reference/public-api) — deploy after approval
- [n8n](https://github.com/n8n-io/n8n) — source-available licence check; R2
- [Temporal](https://github.com/temporalio/temporal) — durable job framework, too heavy for R1
- [Polly](https://github.com/App-vNext/Polly) — resilience
- [Serilog](https://github.com/serilog/serilog) — logs
- [OpenTelemetry .NET](https://github.com/open-telemetry/opentelemetry-dotnet) — traces
- [Gitleaks](https://github.com/gitleaks/gitleaks) — secrets
- [Syft](https://github.com/anchore/syft) — SBOM
- [Grype](https://github.com/anchore/grype) — dependency security
- [Cosign](https://github.com/sigstore/cosign) — artifact signatures
- [Playwright](https://github.com/microsoft/playwright) — web QA
- [pytest](https://github.com/pytest-dev/pytest) — Python QA
- [xUnit](https://github.com/xunit/xunit) — C# QA
- [GitLab Windows runner](https://docs.gitlab.com/ci/runners/hosted_runners/windows/) — source/build diagnostics

## Priority to accelerate
1. Source code/OneHost/NSIS/GitLab + P01–P05 real same-SHA QA. Reuse existing code before all third-party candidates.
2. Release 1 existing UI/routes: approved HOME/MENU/WORK, route parity, 6 FX engines, real events, F11/Escape/reduced motion.
3. Existing Ollama, sqlite/RAG, Voice, R1 game/Work OS/Social/Creative adapters; prototypes must not pretend native QA.
4. Add only compatible, licence-reviewed dependencies with pinned commits/package hashes, SBOM, offline cache and reproducibility receipts.
5. Avoid framework replacement, second services and optional GPU media engines until core Release 1 gates complete.

## Risk and diligence
- NSIS + old scripts already present; do NOT replace it with WiX/Velopack without a separate migration decision.
- GPL/AGPL/LGPL/non-standard examples (Piper, PyMuPDF, ffmpeg codecs, LibVLC, Remotion, n8n) require actual build/config/weights/commercial legal review.
- A GitHub repository being public does NOT prove a model, voice or media weight can be commercially used.
- All candidate links must be checked against actual current upstream license/version/security before admission. No source code copied in this register.
- R1 game, social, Work OS, Creative and plugin sections were OMITTED from the previous narrow installer catalog and have now been added.


## CREATIVE STUDIO V5 — expansion verified 2026-10-30

[Full addendum: 33 Studio screens/capability slices × three adaptable code candidates (99 mapping entries), source V5 acceptance and 8 separate new WOW proposals](NOX_CREATIVE_STUDIO_V5_READY_CODE_MATRIX_R1_20261030.md). This is a reference/code-candidate matrix, not proof of 99 verified integrations or an authorisation to expand Release 1. Covers writing lab W01–W18, book/world bible, cinema, shorts, music, podcasts, playable games, 3D, model lab, brand/revenue workflows.

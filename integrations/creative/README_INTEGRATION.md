# NOX HELION · R13 Creative Runtime integration

**Target:** `MSSTXNEWS/nox-helion-pp-private-build` R13 SHA `48efe948051c987d9922c172740a6aa2115f2970`.

This is an additive Windows candidate, **not** E07 release acceptance. The original D02 home/menu/core files are never replaced. Existing eight CoreIDs, eight top-menu tiles, primary chat, PC controls and installer scripts remain intact.

## Native connections implemented

- Existing `MainWindow.HandleMessage` is extended by exactly two trusted native actions: `creativeInvoke` and `creativeProjector`.
- `CreativeHostBridge.cs` starts the compiled `NOX_CreativeWorker.exe` **on demand**, without a new exposed network port; JSON-lines over parent/child standard streams; UI remains one WPF/WebView2 host.
- `creative/studio.html` renders inside the existing screen/navigation; the ordinary NOX chat intercepts *explicit* creative commands and routes them to the studio. Existing noncreative conversation continues through the original chat.
- Worker reuses prebuilt `Studio.dispatch`: real Ollama storyboard + SRT, local ComfyUI workflow/checkpoints/history, Hugging Face exact weight selection, FFmpeg real MP4, procedural GLB, installed eSpeak voice, document/site/code cue generators, cancel rendering.
- Native file chooser copies verified-size/extension media into the selected local NOX project's assets; no file paths from untrusted web payload are honored.
- Extra WebView2 projector window within the same WPF host, under same local origin and session. The viewer chooses local video for playback (the user-data folder is not exposed as a static web origin). Display enumeration/move still requires the OS/user.
- Responsive 320/390/800x480/fullHD/4K creative CSS; 200 combinations (20 material profiles x 10 motion profiles) from original NOX palettes, NOT 200 heavyweight engines.

## Not yet proven or delivered

- Independent Windows E07 same-EXE installation, GPU-rendered video workflow output, all model weight downloads, hosted HTTPS mobile PWA, real synchronized multi-projector output, arbitrary 3D generative AI, telephone integration, and full 540-tool catalog.
- A model catalog entry is NOT a downloaded model, and a downloaded model is NOT a working generation pipeline.
- PyInstaller's optional dependencies are bundled, but installed FFmpeg, Ollama, ComfyUI, voice engines, GPU and local/remote permission still determine which tasks execute. No fake LIVE/progress or hidden cloud charges.

## Reproduction

Run `python integrations/creative/stage_creative.py work/e06/staged/R11 integrations/creative` only **after** pinned R13 source verification and existing E06 compiler overlays. Build the approved Windows worker from `creative_worker.py` via PyInstaller. Before invoking the existing NSIS manifest/installer builder, run `patch_installer.py` against its disposable script and the worker distribution. Build and independently check same EXE SHA.

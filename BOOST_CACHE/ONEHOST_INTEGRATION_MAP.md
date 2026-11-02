# NOX HELION · MEGA BOOST / physical monolith / one-host handoff

**Not a Windows release.** Cache only; E07 is unproven until installed on Windows.

## Canonical owners
- GitHub PR #162 source snapshot base: ed4fbb76a04f3998d9dfe891e42a9a53caa6be3c.
- Windows: EXISTING WPF shell, EXISTING WebView2 bridge (coordination/e06/OneHostP02WebView2Bridge.cs), EXISTING native Python/P02 process.
- FirstBoot A1: src/nox_selfbuilder/a1_existing_components.py and firstboot_coordinator.py. Never simulate native callbacks, ACL, SID, STOP, consent.
- MENU10: ui/onehost-menu-bindings.mjs and ui/nox-r11-wow.mjs. No second HTTP server.
- WOW200: integrations/creative/stage_creative.py + integrations/wow200/stage_wow200.py on a disposable staged build tree. Never overwrite the approved D02 images.
- Approved D02 images: taken from the owner's Google Drive FINISH_LOCK_ASSETS and SHA checked individually during package construction.
- Approved app archive: NOX_APP_R9.zip taken from same Drive folder; size and ZIP CRC checked.
- Windows dependencies: original SHA-pinned R11 source artifact, two NuGet groups, Ollama installer chunks and transfer manifests. They are not auto-executed.
- All 10 GitHub Actions source/installer artifacts: exact archive ZIP SHA-256 and size checked before bundling.

## Integration / release order (4 gates)
G1: SourceLock on current source SHA + native A1 factory and FirstBoot.
G2: Existing OneHost, WPF/WebView2 GUI and real authenticated WebMessage/native IPC.
G3: Original build_onehost_installer.ps1 and T06 on Windows -> NSIS Setup.exe.
G4: Install the SAME built EXE in Windows VM -> E07 smoke of mandatory functions and receipts.

The monolith packaging does NOT fake or override any of G1-G4. It preserves source and dependency bytes; the setup remains to be built/accepted.

No extension creates another backend, HTTP port, database, renderer, or agent scheduler. Unverified NuGet signatures and third-party license holds remain until independently resolved.

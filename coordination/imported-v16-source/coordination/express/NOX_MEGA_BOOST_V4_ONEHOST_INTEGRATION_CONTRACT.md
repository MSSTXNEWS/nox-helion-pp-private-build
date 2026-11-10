# NOX EXPRESS · BOOST V4 injection contract (single OneHost)
## Source of truth
BOOST cache in persistent project Library: /NOX_HELION/BOOST_CACHE/.
Monolith ZIP64: NOX_HELION_MEGA_BOOST_MONOLITH_V4.zip (six ordered volumes).
Size: 2327776086 bytes.
SHA-256: 2ca2647e46edd1e110db1569cb6a636ceee8e8154b416560ad43a87fb95545bd.
Source cache verified separately from same-SHA release acceptance. No auto-execution.

## Integration path
1. Pin this PR HEAD as the only canonical source revision. Do not copy stale GitLab code over the current tree.
2. Reuse the ORIGINAL e06/build_onehost_installer.ps1 + original WPF, WebView2, existing authenticated private Python/P02 host and NSIS.
3. Stage approved source assets via integrations/creative/stage_creative.py and integrations/wow200/stage_wow200.py on disposable build tree.
4. Reuse ui/onehost-menu-bindings.mjs / ui/nox-r11-wow.mjs. No new scene renderer, backend, API listener or database.
5. Use original D02 HOME/MENU/CORE approved PNG from FINISH_LOCK_ASSETS. Verify their SHA against integrations/wow200/stage_wow200.py.
6. For prerequisites, select saved WebView2 x64 from R11 cache and existing NuGet offline feed; never download unpinned replacements or execute installers before signature check and native consent.
7. A1/FirstBoot factory must come from authenticated WPF owner ports. Do not substitute synthetic policy, SID, STOP, ACL, approvals, or callbacks.
8. Run existing Windows T06 and independent installed E07 on the SAME source SHA.

## Current blocker
GitLab pipeline 3019190901 / job 17675560494: 17/17 NativeIngress PASS; NSIS candidate built; installed smoke HOLD due to T06_WEBVIEW2_RUNTIME_STILL_MISSING_AFTER_INSTALL. Microsoft-signed bootstrapper and standalone installer signatures valid, but strict original preflight still does not accept the runtime. Inspect registration diagnostics and process installation context before retrying; no CI infinite retry.

## Ownership
I0 only integrator of shared release branch. Parallel workers use isolated branches and no-loss staged outputs. Four release gates: SourceLock/A1; WPF/Python/WebView2 real callbacks; NSIS setup; E07 installed acceptance.

# NOX P03 MICRO-WOW C39 — 9 features, host-neutral add-on

**Scope:** secondary model-management screen only. HOME D02, eight CoreIDs, MainWindow.xaml.cs, source archives, queues, installer and events.v3 are unchanged. No external CDN/API, NuGet dependency, or runtime downloads.

## Nine UI functions in one lightweight WebView2 screen

1. **Energy ring**: percentage comes only from genuine completed/total transfer bytes; idle is not simulated progress.
2. **Model DNA**: exact artifact tag/revision/license/source/size/SHA/VRAM, unknowns shown as N/D or REVIEW_REQUIRED.
3. **Quick Control**: STOP / retry / diagnosis buttons enabled only when host publishes explicit capabilities and a valid job state. Host ACK is not task completion.
4. **Unified iconography**: four local Microsoft Fluent UI System Icons SVGs (MIT, retained attribution) combined with original NOX geometric CSS. No icon framework or external request.
5. **Quantum Filters**: local instant catalog search and reviewed-only filtering, no backend search.
6. **Twin Scan**: two-model side-by-side comparison only on existing metadata.
7. **Event Pulse**: up to ten actual model lifecycle events, no dummy activity.
8. **Hardware Harmony**: VRAM/RAM/disk figures only if host passes verified readings, unknown otherwise.
9. **Pre-flight Radar**: read-only source, license, immutable revision, SHA, disk and VRAM evidence state. UI never authorizes a download.

## Integration seam (owner #6)

1. Mount `index.html`, `ui.css`, `ui.js` using existing WebView2 local app origin; prohibit navigation to external sources in that privileged pane. Do not load third-party websites in this privileged WebView2 instance.
2. Reference `ModelWowBridgeContract.cs` from the existing P03 .NET 8 project and call `SnapshotJson(ModelCatalog.OfficialFamilies, await queue.ReadAsync(...), selectedJobId, hardwareSnapshot, capabilities)`. Transmit the returned JSON via `CoreWebView2.PostWebMessageAsJson`, **only to the checked, trusted local origin**. DeviceSnapshot values must come from actual telemetry; pass null if unavailable.
3. For existing `ModelLifecycleEvent` call `ModelWowBridgeContract.EventJson(e)` and use the same WebView2 outbound message.
4. For incoming WebMessageReceived, validate `args.Source` against the local app origin, then validate command shape with `TryParseCommand(..., currentQueueSnapshot, allowedCapabilities, out cmd)`, plus user ACL, host prerequisites and queue task state. `stop` maps to existing `ModelDownloadQueueWorker.CancelAsync`, `retry` maps to `RetryAsync`, diagnosis maps to existing `WindowsComponentAdapter.DetectAsync`. Return an ACK via `PostWebMessageAsJson`; the worker publishes actual outcome separately through lifecycle events. No generic command execution.
5. Host alone maps event data to P01/P05 `events.v3` and keeps current file ownership and SourceLock. Do not merge without approved original tree and E07 seal.

**Caveat**: UI and mapping source are delivered. No Windows host wiring or build is claimed in this patch. No demo/fake sensors or fictional transfer percentages in production UI. No external icon downloads are required.

**Feature budget:** target +2% of base work (not independently measured). If budget overrun: disable comparison and decorative animation by feature flag/CSS first, retain security/provenance.
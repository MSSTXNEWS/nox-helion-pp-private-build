// T06 · Original MainWindow partial. One WPF/WebView2, one pinned original
// Python process and existing P02 NativePythonPipe. No added HTTP/DB/host.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using Nox.P02;
using Nox.P03;
using Nox.P03.Wow;
using System.Linq;
namespace NoxP01;
public partial class MainWindow
{
    private const string NativePythonSha = "4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3";
    private static readonly HashSet<string> AllowedP02 = new(StringComparer.Ordinal) {
        "helion.chat","core.chat","persona.chat","chat.model","chat.history",
        "chat.rag","chat.voice","chat.stop","calls.history","chat.commands",
        "models.installed","models.digest","gpu.preflight","training.start",
        "training.pause","training.resume","training.checkpoints","training.evaluate",
        "system.autostart", "browser.open", "browser.navidle"
    };
    private Process? _nativeP02Process;
    private NativePythonPipe? _nativeP02Pipe;
    private OneHostP02WebView2Bridge? _nativeP02Bridge;
    private ModelCenterNativeRoutes? _nativeModels;
    private CancellationTokenSource _nativeModelsStop = new();
    private CoreWebView2? _nativeP02Core;
    private CoreWebView2? _failedNativeP02Core;
    private bool _nativeModelsStopDisposed;
    private long _nativeDocumentEpoch;
    private readonly HashSet<string> _nativeP03Nonces = new(StringComparer.Ordinal);
    // One child-only WPF consent key; never included in renderer JSON.
    private byte[]? _a1OwnerProofKey;
    private string? _a1OwnerProofRunId;
    private string? _a1OwnerApprovedAction;
    private long _a1OwnerApprovedEpoch;
    private long _a1OwnerStopEpoch; // Mirrors original P02 chat.stop generation.
    private System.Windows.Controls.Button? _nativeBrowserBack;
    private bool _nativeBrowserFenceInstalled;
    private EventHandler<CoreWebView2WebResourceRequestedEventArgs>? _nativeBrowserFilter;
    private EventHandler<CoreWebView2ContentLoadingEventArgs>? _nativeBrowserOnShell;

    private bool ShowNativeBrowserBack()
    {
        // Native Windows control, not a WebView host object or a second browser.
        if (_nativeBrowserBack is not null) return true;
        if (Content is not System.Windows.Controls.Panel panel) return false;
        var button = new System.Windows.Controls.Button {
            Content = "← HOME NOX", Width = 142, Height = 36,
            HorizontalAlignment = HorizontalAlignment.Right,
            VerticalAlignment = VerticalAlignment.Top,
            Margin = new Thickness(9)
        };
        button.Click += (_, _) => _nativeP02Bridge?.ReturnToReviewedShell();
        System.Windows.Controls.Panel.SetZIndex(button, 9999);
        panel.Children.Add(button); _nativeBrowserBack = button;
        return true;
    }
    private void HideNativeBrowserBack()
    {
        if (_nativeBrowserBack is not { } button) return;
        if (button.Parent is System.Windows.Controls.Panel panel) panel.Children.Remove(button);
        _nativeBrowserBack = null;
    }
    private bool EnsureNativeBrowserNetworkFence(CoreWebView2 core)
    {
        if (_nativeBrowserFenceInstalled) return true;
        try {
            core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All);
            _nativeBrowserFilter = (_, e) => {
                if (_nativeP02Bridge?.BrowserExternalActive != true) return;
                if (_nativeP02Bridge.BrowserAllowsRequest(e.Request.Uri)) return;
                e.Response = core.Environment.CreateWebResourceResponse(
                    null, 403, "NOX_BLOCKED", "Content-Type: text/plain");
            };
            core.WebResourceRequested += _nativeBrowserFilter;
            _nativeBrowserFenceInstalled = true;
            return true;
        } catch { return false; }
    }

    private Task<string?> PickNativeGgufAsync(CancellationToken cancel)
    {
        if (cancel.IsCancellationRequested) return Task.FromResult<string?>(null);
        var picker=new Microsoft.Win32.OpenFileDialog {
            Title="NOX · Выбрать проверенный GGUF",Filter="GGUF weights (*.gguf)|*.gguf",
            CheckFileExists=true,Multiselect=false
        };
        if (picker.ShowDialog(this)!=true || cancel.IsCancellationRequested)
            return Task.FromResult<string?>(null);
        if (!PlainBackendPath(picker.FileName)) return Task.FromResult<string?>(null);
        var accepted=MessageBox.Show(this,"Импортировать выбранные локальные веса после проверки SHA и лицензии?",
            "NOX · Model Center",MessageBoxButton.YesNo,MessageBoxImage.Question,MessageBoxResult.No);
        return Task.FromResult<string?>(accepted==MessageBoxResult.Yes&&!cancel.IsCancellationRequested?picker.FileName:null);
    }

    private sealed class NativeModelEvents(MainWindow owner) : IModelLifecycleEventSink
    {
        public async ValueTask PublishToP01Async(ModelLifecycleEvent item, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            // Both owner sinks publish on the original WPF STA dispatcher.
            // WebView2 Core must never be called on the download-worker thread.
            await owner.Dispatcher.InvokeAsync(() => {
                // Preserve private model lifecycle data inside the original trusted WebView2.
                // External/pending-return browser mode must not see job identifiers.
                var core = owner._nativeP02Core;
                var bridge = owner._nativeP02Bridge;
                var sid = WindowsIdentity.GetCurrent().User?.Value;
                if (core is null || bridge is null || bridge.BrowserExternalActive ||
                    !IsTrustedNoxDocument(core.Source) ||
                    string.IsNullOrEmpty(sid) || !owner.NativeP02Acl(sid, "models.queue")) return;
                owner.PostMessage(new {
                    kind="modelLifecycle", eventId=item.EventId, jobId=item.JobId,
                    phase=item.Phase,state=item.Status,completedBytes=item.CompletedBytes,
                    totalBytes=item.TotalBytes,observedAt=item.AtUtc
                });
                if (IsP03Document(core.Source)) {
                    try { core.PostWebMessageAsJson(ModelWowBridgeContract.EventJson(item)); }
                    catch (Exception ex) { Trace.TraceError("P03_EVENT_UI_DROP {0}", ex.GetType().Name); }
                }
            });
        }
        public async ValueTask PublishToP05Async(ModelLifecycleEvent item, CancellationToken ct)
        {
            ct.ThrowIfCancellationRequested();
            await owner.Dispatcher.InvokeAsync(() => owner.AppendRuntimeV3(
                "task.progress",item.JobId.ToString("N"),"models.download",item.Status,
                "P03 event "+item.EventId.ToString("N")+" / "+item.Phase,"P03.ModelCenter",
                item.CompletedBytes,item.TotalBytes,packageId:"P03"));
        }
    }

    private object CreateA1PrivateConsentReceipt(string action)
    {
        var secret=_a1OwnerProofKey;
        var runId=_a1OwnerProofRunId;
        if (secret is not { Length: 32 } || runId is null ||
            _nativeP02Process is not { HasExited: false } ||
            _nativeModelsStop.IsCancellationRequested)
            throw new UnauthorizedAccessException("A1_WPF_OWNER_PROOF_UNAVAILABLE");
        var sid=WindowsIdentity.GetCurrent().User?.Value;
        if (string.IsNullOrEmpty(sid) || !NativeP02Acl(sid,"chat.commands"))
            throw new UnauthorizedAccessException("A1_WINDOWS_SID_OR_ACL_DENIED");
        var now=DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        var stopEpoch=Interlocked.Read(ref _a1OwnerStopEpoch);
        var expiry=now+20;
        var nonce=Convert.ToHexString(RandomNumberGenerator.GetBytes(16)).ToLowerInvariant();
        var sidHash=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(sid))).ToLowerInvariant();
        const string schema="NOX-A1-WPF-OWNER-CONSENT-v1";
        var transcript=string.Join("\n",schema,runId,action,NativePythonSha,
            sidHash,stopEpoch.ToString(System.Globalization.CultureInfo.InvariantCulture),
            now.ToString(System.Globalization.CultureInfo.InvariantCulture),
            expiry.ToString(System.Globalization.CultureInfo.InvariantCulture),nonce);
        var mac=Convert.ToHexString(HMACSHA256.HashData(secret,Encoding.ASCII.GetBytes(transcript))).ToLowerInvariant();
        return new {schema,run_id=runId,action,backend_sha256=NativePythonSha,
            sid_sha256=sidHash,native_stop_epoch=stopEpoch,nonce,issued_unix=now,expires_unix=expiry,mac};
    }

    private async Task<NativePipeResult> DispatchNativeOwnerAsync(string route, JsonElement payload,
        CancellationToken cancel)
    {
        if (route == "browser.navidle") {
            // B6: native idle entry for NOX Browser. No second WebView.
            // Reports NAV_IDLE only when the original core is alive and not external.
            if (cancel.IsCancellationRequested || _nativeP02Core is not { } core ||
                _nativeP02Bridge is not { } bridge ||
                ReferenceEquals(core, _failedNativeP02Core) ||
                bridge.BrowserExternalActive)
                return new NativePipeResult("", false, null, "NAV_IDLE_HOLD");
            return new NativePipeResult("", true,
                JsonSerializer.SerializeToElement(new { status = "NAV_IDLE" }), null);
        }
        if (route == "browser.open") {
            if (cancel.IsCancellationRequested || _nativeP02Core is not { } core ||
                _nativeP02Bridge is not { } bridge ||
                payload.ValueKind != JsonValueKind.Object ||
                payload.EnumerateObject().Count() != 1 ||
                !payload.TryGetProperty("url", out var field) ||
                field.ValueKind != JsonValueKind.String ||
                field.GetString() is not string address || address.Length > 2048 ||
                !Uri.TryCreate(address, UriKind.Absolute, out var target) ||
                !NoxHelion.P02.SpaceBrowserBoundary.MayNavigateReviewedExternal(
                    target, new[]{target.IdnHost}, true, true, true, true) ||
                !EnsureNativeBrowserNetworkFence(core) || !ShowNativeBrowserBack())
                return new NativePipeResult("",false,null,"BROWSER_NATIVE_POLICY_HOLD");
            try {
                core.Settings.IsWebMessageEnabled = false;
                core.Settings.AreHostObjectsAllowed = false;
                if (cancel.IsCancellationRequested || !bridge.TryOpenReviewedExternal(
                    target, new[]{target.IdnHost}, nativeGestureVerified:true,
                    ipcDetached:!core.Settings.IsWebMessageEnabled,
                    hostObjectsRemoved:!core.Settings.AreHostObjectsAllowed,
                    networkIsolationAttested:_nativeBrowserFenceInstalled)) {
                    if (!bridge.BrowserExternalActive) {
                        HideNativeBrowserBack();
                        core.Settings.IsWebMessageEnabled = true; // trusted source only
                    }
                    return new NativePipeResult("",false,null,"BROWSER_NAVIGATION_HOLD");
                }
                return new NativePipeResult("",true,
                    JsonSerializer.SerializeToElement(new { status="NAVIGATION_REQUESTED" }),null);
            } catch {
                // Never restore the IPC channel while an external document
                // may be active; retain the native Back action for recovery.
                return new NativePipeResult("",false,null,"BROWSER_NAVIGATION_EXCEPTION_HOLD");
            }
        }
        if(route=="system.autostart") {
            if(payload.ValueKind != JsonValueKind.Object || payload.EnumerateObject().Count()!=1 ||
                !payload.TryGetProperty("enabled",out var requested) ||
                requested.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                return new NativePipeResult("",false,null,"NOX_AUTOSTART_BOOLEAN_REQUIRED");
            try {
                cancel.ThrowIfCancellationRequested();
                var path=Environment.ProcessPath ?? "";
                var enabled=NoXAutostart.SetEnabled(path,requested.GetBoolean(),nativeConsent:true);
                return new NativePipeResult("",true,
                    JsonSerializer.SerializeToElement(new {enabled}),null);
            } catch(OperationCanceledException) {throw;}
              catch {return new NativePipeResult("",false,null,"NOX_AUTOSTART_NATIVE_HOLD");}
        }
        if(route=="chat.stop") {
            Interlocked.Increment(ref _a1OwnerStopEpoch);
            _a1OwnerApprovedAction=null;
            if (_a1OwnerProofKey is not null) {
                CryptographicOperations.ZeroMemory(_a1OwnerProofKey);
                _a1OwnerProofKey=null;
            }
            _nativeModels?.StopMergedImport();
            _nativeModelsStop.Cancel();_nativeModelsStop.Dispose();
            _nativeModelsStop=new CancellationTokenSource();
            if(_nativeP02Pipe is null)return new NativePipeResult("",false,null,"NATIVE_PIPE_CLOSED");
            return await _nativeP02Pipe.RequestAsync(route,payload,TimeSpan.FromSeconds(10),cancel);
        }
        using var ownerCancel=CancellationTokenSource.CreateLinkedTokenSource(cancel,_nativeModelsStop.Token);
        cancel=ownerCancel.Token;
        if (route=="chat.commands" && payload.TryGetProperty("action",out var command) &&
            command.GetString()=="training.import") {
            if (_nativeModels is null || _nativeP02Pipe is null)
                return new NativePipeResult("",false,null,"P03_NATIVE_OWNER_HOLD");
            try {
                // The page supplies only a native registered job ID. The
                // source-bound approval is fetched from the private Python
                // owner, never deserialized from renderer authority fields.
                var request=new Dictionary<string,object?> {
                    ["action"]="training.import.prepare",
                    ["job_id"]=payload.GetProperty("job_id").GetString(),
                    ["native_approval_id"]="NOX-NATIVE-"+Guid.NewGuid().ToString("N")
                };
                foreach(var key in new[]{"core_id","persona_id"})
                    if(payload.TryGetProperty(key,out var selector))request[key]=selector.GetString();
                var proof=await _nativeP02Pipe.RequestAsync("chat.commands",request,
                    TimeSpan.FromSeconds(60),cancel);
                if(!proof.Accepted || proof.Result is not JsonElement approved)
                    return new NativePipeResult("",false,null,proof.ErrorCode??"P04_MERGE_PROOF_HOLD");
                var approval=approved.Deserialize<P04MergedImportApproval>(
                    new JsonSerializerOptions(JsonSerializerDefaults.Web))
                    ??throw new InvalidOperationException("P04_NATIVE_APPROVAL_HOLD");
                var imported=await _nativeModels.ImportMergedAsync(approval,true,cancel);
                request["action"]="training.import.record";
                request.Remove("native_approval_id");
                request["receipt_path"]=imported.GetProperty("receiptPath").GetString();
                return await _nativeP02Pipe.RequestAsync("chat.commands",request,
                    TimeSpan.FromSeconds(60),cancel);
            } catch(OperationCanceledException) { throw; }
            catch(SafetensorsImportHold held) { return new NativePipeResult("",false,null,held.Code); }
            catch { return new NativePipeResult("",false,null,"P04_P03_NATIVE_IMPORT_HOLD"); }
        }
        if (_nativeModels is not null && ModelCenterNativeRoutes.Routes.Contains(route)) {
            try {
                var value=await _nativeModels.ExecuteAsync(route,payload,true,cancel);
                return new NativePipeResult("",true,value,null);
            } catch(OperationCanceledException ex) when (
                !cancel.IsCancellationRequested &&
                string.Equals(ex.Message,"P03_NATIVE_FILE_SELECTION_CANCELLED",StringComparison.Ordinal)) {
                // Voluntary GGUF picker decline is a terminal HOLD, not a lost native ACK.
                // Real STOP, host shutdown and revoked document cancellation still propagate.
                return new NativePipeResult("",false,null,"P03_NATIVE_FILE_SELECTION_CANCELLED");
            } catch(OperationCanceledException) { throw; }
            catch { return new NativePipeResult("",false,null,"P03_NATIVE_OWNER_HOLD"); }
        }
        if (_nativeP02Pipe is null) return new NativePipeResult("",false,null,"NATIVE_PIPE_CLOSED");
        if (route=="chat.commands" && payload.ValueKind==JsonValueKind.Object &&
            payload.TryGetProperty("action",out var a1Action) &&
            a1Action.ValueKind==JsonValueKind.String &&
            a1Action.GetString() is string a1Name &&
            (a1Name=="selfbuilder.a1.boot" || a1Name=="selfbuilder.a1.tick")) {
            var nativeApproved=_a1OwnerApprovedAction==a1Name &&
                _a1OwnerApprovedEpoch==Interlocked.Read(ref _nativeDocumentEpoch);
            _a1OwnerApprovedAction=null; // WPF approval is consumed once.
            if (!nativeApproved || cancel.IsCancellationRequested ||
                payload.EnumerateObject().Count()!=1)
                return new NativePipeResult("",false,null,"A1_WPF_FRESH_CONSENT_REQUIRED");
            try {
                var ticket=CreateA1PrivateConsentReceipt(a1Name);
                return await _nativeP02Pipe.RequestWpfApprovedA1Async(a1Name,ticket,cancel);
            } catch (OperationCanceledException) { throw; }
              catch { return new NativePipeResult("",false,null,"A1_WPF_OWNER_PROOF_HOLD"); }
        }
        return await _nativeP02Pipe.RequestAsync(route,payload,TimeSpan.FromSeconds(60),cancel);
    }

    private bool LegacyDocumentCurrent(string source, long epoch) =>
        _nativeP02Core is not null && Interlocked.Read(ref _nativeDocumentEpoch)==epoch &&
        string.Equals(_nativeP02Core.Source,source,StringComparison.Ordinal);

    // StageNativeP02 inserts this before the original action switch. Legacy
    // local controls reuse the same private pipe; explicit OpenAI remains on
    // its original separately consented API path.
    private bool TryDispatchLegacyNative(JsonElement root, string source)
    {
        if (!root.TryGetProperty("action", out var action) || action.ValueKind != JsonValueKind.String)
            return false;
        var name = action.GetString();
        if (name == "chatStart" && root.TryGetProperty("provider", out var provider) &&
            string.Equals(provider.GetString(), "OPENAI", StringComparison.OrdinalIgnoreCase)) return false;
        if (name is not ("chatModels" or "chatStart" or "chatStop" or "openModelCenter")) return false;
        if (!Uri.TryCreate(source, UriKind.Absolute, out var origin) ||
            origin.Scheme != "https" || !origin.IsDefaultPort || origin.UserInfo.Length != 0 ||
            !string.Equals(origin.Host, "nox.local", StringComparison.OrdinalIgnoreCase)) return true;
        // Preserve STOP for an existing explicitly selected OpenAI request.
        if (name == "chatStop") StopChat(GetString(root, "chatId"));
        _ = DispatchLegacyNativeAsync(name, root.Clone(), source, Interlocked.Read(ref _nativeDocumentEpoch));
        return true;
    }

    private async Task DispatchLegacyNativeAsync(string action, JsonElement root, string source, long epoch)
    {
        var chatId = GetString(root, "chatId");
        var route = action switch {
            "chatModels" => "chat.model", "chatStart" => "helion.chat",
            "chatStop" => "chat.stop", _ => "models.catalog"
        };
        try {
            var sid = WindowsIdentity.GetCurrent().User?.Value;
            if (sid is null || !NativeP02Acl(sid, route) || _nativeP02Pipe is null)
                throw new NativePipeHold("NATIVE_PERMISSION_DENIED");
            var payload = action == "chatStart" ? JsonSerializer.SerializeToElement(new {
                text = GetString(root,"message"), model = GetString(root,"model"),
                core_id = LegacyCoreId(GetString(root,"coreId")),
                persona_id = LegacyPersonaId(GetString(root,"personaId"))
            }) : JsonSerializer.SerializeToElement(new {});
            if (route != "chat.stop" && !await ConfirmP02NativeAsync(route,payload,CancellationToken.None))
                throw new NativePipeHold("NATIVE_CONSENT_DENIED");
            if (!NativeP02Acl(sid,route) || !LegacyDocumentCurrent(source,epoch))
                throw new NativePipeHold("NATIVE_PERMISSION_DENIED");
            var result = action is "openModelCenter" or "chatStop" ? await DispatchNativeOwnerAsync(route,payload,CancellationToken.None) :
                await _nativeP02Pipe.RequestAsync(route,payload,TimeSpan.FromMinutes(3),
                onEvent: item => Dispatcher.BeginInvoke(new Action(() => {
                    if (!NativeP02Acl(sid,route) || !LegacyDocumentCurrent(source,epoch)) return;
                    if (item.TryGetProperty("delta",out var delta) && delta.ValueKind==JsonValueKind.String)
                        PostMessage(new {kind="chatToken",chatId,token=delta.GetString()});
                })));
            if (!LegacyDocumentCurrent(source,epoch)) return;
            if (!result.Accepted) throw new NativePipeHold(result.ErrorCode??"NATIVE_PROVIDER_HOLD");
            if (action == "chatModels") {
                var models = result.Result is JsonElement data && data.TryGetProperty("models",out var list)
                    ? list.Clone() : JsonSerializer.SerializeToElement(Array.Empty<string>());
                var modelState = result.Result is JsonElement inventory && inventory.TryGetProperty("provider_state",out var ps)
                    ? ps.GetString() : "HOLD";
                PostMessage(new {kind="chatModels",state=modelState,chatId,models,
                    history=Array.Empty<object>(),historyState="SELECT_NATIVE_PERSONA_SCOPE",
                    message="Модели из единого локального P02; история доступна в выбранной Persona."});
            } else if (action=="openModelCenter") {
                PostMessage(new {kind="p02NativeResult",routeId=route,state="COMPLETED",result=result.Result});
                // Approved secondary page inside the SAME original WebView2.
                if (_nativeP02Core is { } web && LegacyDocumentCurrent(source,epoch))
                    web.Navigate("https://nox.local/creative/modelcenter/index.html");
            } else PostMessage(new {kind="chatFinished",chatId,
                state=action=="chatStop"?"STOP_REQUESTED":"COMPLETED"});
        } catch (Exception error) {
            if (!LegacyDocumentCurrent(source,epoch)) return;
            PostMessage(new {kind="chatError",chatId,
                code=error is NativePipeHold held?held.Code:"NATIVE_TRANSPORT_HOLD",
                message="Локальный маршрут NOX недоступен; состояние сохранено."});
        }
    }

    private static string? LegacyCoreId(string? value) => value?.ToLowerInvariant() switch {
        "consciousness" or "persona" or "atlas" or "voice" or "reflection" or "core" or "nexus" or "forge"
            => "core."+value.ToLowerInvariant(), _=>value
    };
    private static string? LegacyPersonaId(string? value) => value?.ToLowerInvariant() switch {
        "kairen"=>"persona.kairen_voss", "adrian"=>"persona.adrian_marrow",
        "leon"=>"persona.leon_ardis", "elina"=>"persona.elina_veil",
        "cassien"=>"persona.kassien_veir", _=>value
    };

    private bool NativeP02Acl(string sid, string route)
    {
        try {
            return (AllowedP02.Contains(route) || _nativeModels is not null && ModelCenterNativeRoutes.Routes.Contains(route)) &&
                _nativeP02Process is { HasExited: false } &&
                string.Equals(WindowsIdentity.GetCurrent().User?.Value, sid, StringComparison.Ordinal);
        } catch { return false; }
    }
    private Task<bool> ConfirmP02NativeAsync(string route, JsonElement payload, CancellationToken cancel)
    {
        if (cancel.IsCancellationRequested) return Task.FromResult(false);
        if (route == "chat.stop" || route == "chat.model") return Task.FromResult(true);
        // Existing WPF native window, never browser-supplied consent.
        var label = route;
        if (route == "browser.open") {
            if (payload.ValueKind != JsonValueKind.Object ||
                payload.EnumerateObject().Count() != 1 ||
                !payload.TryGetProperty("url", out var u) ||
                u.ValueKind != JsonValueKind.String ||
                u.GetString() is not string address || address.Length > 2048 ||
                !Uri.TryCreate(address, UriKind.Absolute, out var target) ||
                !NoxHelion.P02.SpaceBrowserBoundary.MayNavigateReviewedExternal(
                    target, new[]{target.IdnHost}, true, true, true, true))
                return Task.FromResult(false);
            label = "Открыть проверенный HTTPS только в NOX: " + target.AbsoluteUri;
        }
        if(route=="system.autostart") {
            if(payload.ValueKind != JsonValueKind.Object ||
                !payload.TryGetProperty("enabled",out var on) ||
                on.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                return Task.FromResult(false);
            label=on.GetBoolean()?"Автозапуск NOX при входе в Windows: ВКЛ":
                "Автозапуск NOX при входе в Windows: ВЫКЛ";
        }
        if (route == "chat.commands") {
            if (!payload.TryGetProperty("action", out var action) ||
                action.ValueKind != JsonValueKind.String) return Task.FromResult(false);
            var command = action.GetString();
            if (command is not ("selfbuilder.worker.status" or "selfbuilder.capabilities" or
                "selfbuilder.propose" or "selfbuilder.feedback" or "selfbuilder.worker.stop" or
                "selfbuilder.study.queue" or "selfbuilder.learning.proofs" or
                "selfbuilder.seed.inspect" or "selfbuilder.coding.models" or "selfbuilder.worker.start" or
                "training.merge" or "training.import" or "training.activate" or "training.rollback" or
                "selfbuilder.a1.status" or "selfbuilder.a1.boot" or "selfbuilder.a1.tick" or
                "selfbuilder.activator.status"))
                return Task.FromResult(false);
            if ((command == "selfbuilder.a1.status" || command == "selfbuilder.a1.boot" ||
                 command == "selfbuilder.a1.tick") && payload.EnumerateObject().Count() != 1)
                return Task.FromResult(false);
            if (command == "selfbuilder.activator.status") {
                // Read-only local inventory from the trusted NOX virtual origin.
                // SID, origin, ACL and exact payload are still checked natively.
                if (payload.EnumerateObject().Count() != 1) return Task.FromResult(false);
                return Task.FromResult(!cancel.IsCancellationRequested);
            }
            label += " / " + command;
        }
        var answer=MessageBox.Show(this, "Разрешить локальный маршрут NOX: "+label+"?",
            "NOX HELION · Native consent",MessageBoxButton.YesNo,
            MessageBoxImage.Question,MessageBoxResult.No);
        var approved=!cancel.IsCancellationRequested && answer==MessageBoxResult.Yes;
        if (approved && route=="chat.commands" &&
            payload.TryGetProperty("action",out var attestedCommand) &&
            attestedCommand.GetString() is string a1Command &&
            (a1Command=="selfbuilder.a1.boot" || a1Command=="selfbuilder.a1.tick")) {
            _a1OwnerApprovedAction=a1Command;
            _a1OwnerApprovedEpoch=Interlocked.Read(ref _nativeDocumentEpoch);
        }
        return Task.FromResult(approved);
    }
    private static bool PlainBackendPath(string path)
    {
        try {
            FileSystemInfo? node=new FileInfo(path);
            while (node is not null) {
                if ((node.Attributes & FileAttributes.ReparsePoint)!=0) return false;
                node=node is DirectoryInfo directory?directory.Parent:(node as FileInfo)?.Directory;
            }
            return true;
        } catch { return false; }
    }
    // A closed browser CoreWebView2 is not a recoverable renderer reload.
    // The original WPF owner must tear down the private child, invalidate A1
    // proof, and require a NEW original control/core for any next handshake.
    private void OnNativeP02BrowserProcessExited(CoreWebView2 failedCore)
    {
        if (!Dispatcher.CheckAccess()) {
            Dispatcher.BeginInvoke(new Action(() => OnNativeP02BrowserProcessExited(failedCore)));
            return;
        }
        if (!ReferenceEquals(_nativeP02Core, failedCore)) return;
        _failedNativeP02Core = failedCore;
        WriteLog("P02_BROWSER_PROCESS_EXIT_OWNER_SHUTDOWN");
        ShutdownNativeP02();
    }
    private void OnNativeP02NavigationStarting(object? sender, CoreWebView2NavigationStartingEventArgs e)
    { Interlocked.Increment(ref _nativeDocumentEpoch); }
    private void OnNativeP02SourceChanged(object? sender, CoreWebView2SourceChangedEventArgs e)
    { Interlocked.Increment(ref _nativeDocumentEpoch); }
    private void OnNativeP02ContentLoading(object? sender, CoreWebView2ContentLoadingEventArgs e)
    { Interlocked.Increment(ref _nativeDocumentEpoch); }

    private async Task InitializeNativeP02Async(CoreWebView2 core)
    {
        if (ReferenceEquals(_failedNativeP02Core, core)) {
            WriteLog("P02_BROWSER_CLOSED_CORE_RECREATE_REQUIRED");
            return;
        }
        // Another genuine Core means the previous bridge/child must not keep
        // the old window's permissions or callbacks after control recreation.
        if (_nativeP02Core is not null && !ReferenceEquals(_nativeP02Core, core))
            ShutdownNativeP02();
        if (_nativeP02Process is not null || _nativeP02Pipe is not null) return;
        if (_nativeModelsStopDisposed) {
            _nativeModelsStop = new CancellationTokenSource();
            _nativeModelsStopDisposed = false;
        }
        var binary=Path.Combine(AppContext.BaseDirectory,"Backend","NOX_HELION_PRIVATE_CANDIDATE.exe");
        Process? child=null; NativePythonPipe? transport=null;
        try {
            if (!File.Exists(binary) || !PlainBackendPath(binary))
                throw new IOException("P02_ORIGINAL_EXECUTABLE_MISSING_OR_REPARSE");
            await using(var stream=File.OpenRead(binary)) {
                var sha=Convert.ToHexString(await SHA256.HashDataAsync(stream)).ToLowerInvariant();
                if (!string.Equals(sha,NativePythonSha,StringComparison.Ordinal))
                    throw new IOException("P02_ORIGINAL_EXECUTABLE_SHA_HOLD");
            }
            var sid=WindowsIdentity.GetCurrent().User?.Value;
            if(string.IsNullOrEmpty(sid))throw new UnauthorizedAccessException("P02_WINDOWS_SID_REQUIRED");
            var runId="NOX-P02-"+Guid.NewGuid().ToString("N");
            var args=new ProcessStartInfo(binary) {
                UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,
                RedirectStandardOutput=true,RedirectStandardError=false,
                WorkingDirectory=AppContext.BaseDirectory
            };
            // The original EXE must really implement NativeIngress.handle.
            // --diagnose is NEVER accepted as a success substitute.
            args.ArgumentList.Add("--native-stdio");
            args.ArgumentList.Add("--run-id");args.ArgumentList.Add(runId);
            args.ArgumentList.Add("--data-dir");
            args.ArgumentList.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"NOX_HELION"));
            var a1Secret=RandomNumberGenerator.GetBytes(32);
            args.Environment["NOX_A1_WPF_OWNER_KEY"]=Convert.ToHexString(a1Secret).ToLowerInvariant();
            child=Process.Start(args)??throw new IOException("P02_ORIGINAL_PROCESS_HOLD");
            _a1OwnerProofKey=a1Secret;
            _a1OwnerProofRunId=runId;
            _nativeP02Process=child;
            transport=new NativePythonPipe(child.StandardOutput.BaseStream,
                child.StandardInput.BaseStream,runId);
            var handshake=await transport.RequestAsync("chat.model",new {},
                TimeSpan.FromSeconds(40)); // Allows P02's bounded discovery timeout to return honest OFFLINE.
            if(!handshake.Accepted)throw new IOException("P02_REAL_NATIVE_INGRESS_NOT_READY");
            _nativeP02Core=core;
            _nativeP02Bridge=new OneHostP02WebView2Bridge(core,
                new Uri("https://nox.local/"),transport,sid,
                NativeP02Acl,ConfirmP02NativeAsync,WriteLog,DispatchNativeOwnerAsync,
                OnNativeP02BrowserProcessExited);
            _nativeBrowserOnShell = (_, _) => {
                if (_nativeP02Bridge is { BrowserExternalActive: false } &&
                    Uri.TryCreate(core.Source, UriKind.Absolute, out var source) &&
                    source.Scheme == Uri.UriSchemeHttps && source.IsDefaultPort &&
                    string.Equals(source.IdnHost,"nox.local",StringComparison.OrdinalIgnoreCase)) {
                    core.Settings.IsWebMessageEnabled = true;
                    HideNativeBrowserBack();
                }
            };
            core.ContentLoading += _nativeBrowserOnShell;
            _nativeP02Pipe=transport;
            _nativeModels=ModelCenterNativeRoutes.Create(
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"NOX_HELION"),
                new NativeModelEvents(this),()=>ModelArtifactReviewRegistry.LoadReviewedArtifacts(
                    Path.Combine(AppContext.BaseDirectory,"contracts","p03_reviewed_artifacts.json"),
                    "3b47af8b85aefd88408dd5cc63ad9615da87427d4d0cb2b56b0f5a4246ffbd60"),
                PickNativeGgufAsync);
            core.WebMessageReceived += OnP03WebMessageReceived;
            core.NavigationStarting += OnNativeP02NavigationStarting;
            core.SourceChanged += OnNativeP02SourceChanged;
            core.ContentLoading += OnNativeP02ContentLoading;
            _failedNativeP02Core=null;
            WriteLog("P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK");
        } catch(Exception exception) {
            _a1OwnerApprovedAction=null;
            _a1OwnerProofRunId=null;
            if (_a1OwnerProofKey is not null) {
                CryptographicOperations.ZeroMemory(_a1OwnerProofKey);
                _a1OwnerProofKey=null;
            }
            WriteLog("P02_ORIGINAL_NATIVE_HOLD "+exception.GetType().Name);
            _nativeP02Bridge?.Dispose();_nativeP02Bridge=null;
            _nativeModels?.Dispose();_nativeModels=null;
            core.WebMessageReceived -= OnP03WebMessageReceived;
            core.NavigationStarting -= OnNativeP02NavigationStarting;
            core.SourceChanged -= OnNativeP02SourceChanged;
            core.ContentLoading -= OnNativeP02ContentLoading;
            if (_nativeBrowserOnShell is not null) core.ContentLoading -= _nativeBrowserOnShell;
            _nativeBrowserOnShell=null;
            _nativeP02Core=null;
            if(transport is not null)await transport.DisposeAsync();
            if(child is not null) {
                try {if(!child.HasExited)child.Kill(entireProcessTree:true);}catch{}
                child.Dispose();
            }
            _nativeP02Process=null;_nativeP02Pipe=null;
            // No synthetic ready state; existing original UI/chat remain unchanged.
        }
    }
    private static bool IsTrustedNoxDocument(string? source) =>
        Uri.TryCreate(source, UriKind.Absolute, out var uri) &&
        uri.Scheme == Uri.UriSchemeHttps && uri.IsDefaultPort &&
        uri.UserInfo.Length == 0 &&
        uri.Host.Equals("nox.local", StringComparison.OrdinalIgnoreCase);

    private static bool IsP03Document(string? source) =>
        Uri.TryCreate(source, UriKind.Absolute, out var uri) &&
        uri.Scheme == Uri.UriSchemeHttps && uri.IsDefaultPort &&
        uri.UserInfo.Length == 0 && uri.Host.Equals("nox.local", StringComparison.OrdinalIgnoreCase) &&
        uri.AbsolutePath.Equals("/creative/modelcenter/index.html", StringComparison.Ordinal) &&
        uri.Query.Length == 0 && uri.Fragment.Length == 0;

    private async Task PublishP03SnapshotAsync(long epoch, CancellationToken ct)
    {
        var core = _nativeP02Core;
        var models = _nativeModels;
        if (models is null || core is null || !IsP03Document(core.Source)) return;
        var reviewed = models.ReadReviewed();
        var jobs = await models.ReadJobsAsync(ct);
        var hardware = WindowsHardwareFacts.Capture();
        var families = ModelCatalog.OfficialFamilies.Select(f =>
            reviewed.FirstOrDefault(x => x.Id == f.Id && x.CanOfferOneClickPull) ?? f).ToArray();
        var mostRecent = jobs.OrderByDescending(x => x.UpdatedAtUtc).FirstOrDefault();
        var caps = new ModelWowBridgeContract.Capabilities(
            Stop: true, Retry: true, Diagnose: true,
            Pull: reviewed.Any(x => x.CanOfferOneClickPull),
            ImportGguf: reviewed.Any(x => x.CanOfferOneClickPull &&
                !string.IsNullOrWhiteSpace(x.ReviewedRightsReceiptId)));
        var snapshot = ModelWowBridgeContract.SnapshotJson(families, jobs, mostRecent?.Id,
            new ModelWowBridgeContract.DeviceSnapshot(null,
                hardware.AvailableMemoryBytes is long ram ? ram / 1073741824d : null,
                hardware.SystemDiskFreeBytes is long disk ? disk / 1073741824d : null), caps);
        if (_nativeP02Core is { } current && IsP03Document(current.Source) &&
            Interlocked.Read(ref _nativeDocumentEpoch) == epoch)
            current.PostWebMessageAsJson(snapshot);
    }

    // Source identity and authority are validated on the original WPF owner.
    // Never create another WebView, HTTP server, queue, downloader or model.
    private async void OnP03WebMessageReceived(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        if (_nativeModels is null || !IsP03Document(e.Source) ||
            _nativeP02Core is null || !IsP03Document(_nativeP02Core.Source) ||
            !string.Equals(e.Source, _nativeP02Core.Source, StringComparison.Ordinal))
            return;
        var epoch = Interlocked.Read(ref _nativeDocumentEpoch);
        // Pin the original owner STOP generation across asynchronous P03 preflight.
        // A subsequent chat.stop cancels this token, even after CTS rotation.
        var stopGeneration = _nativeModelsStop.Token;
        if (e.WebMessageAsJson.Length > 2048) return;
        try
        {
            using var json = JsonDocument.Parse(e.WebMessageAsJson,
                new JsonDocumentOptions { MaxDepth = 8 });
            var root = json.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                !root.TryGetProperty("type", out var kind) ||
                kind.ValueKind != JsonValueKind.String) return;
            var type = kind.GetString();
            var sid = WindowsIdentity.GetCurrent().User?.Value;
            if (string.IsNullOrEmpty(sid) || !NativeP02Acl(sid, "models.queue")) return;
            if (type == "p03.ready.v1")
            {
                if (root.EnumerateObject().Count() != 1) return;
                await PublishP03SnapshotAsync(epoch, CancellationToken.None);
                return;
            }
            if (type != "p03.command.v1") return;
            var reviewed = _nativeModels.ReadReviewed();
            var jobs = await _nativeModels.ReadJobsAsync(CancellationToken.None);
            var caps = new ModelWowBridgeContract.Capabilities(
                Stop: true, Retry: true, Diagnose: true,
                Pull: reviewed.Any(x => x.CanOfferOneClickPull),
                ImportGguf: reviewed.Any(x => x.CanOfferOneClickPull &&
                    !string.IsNullOrWhiteSpace(x.ReviewedRightsReceiptId)));
            if (!ModelWowBridgeContract.TryParseCommand(e.WebMessageAsJson, jobs,
                    reviewed, caps, out var command) || command is null ||
                _nativeP03Nonces.Count >= 8192 ||
                !_nativeP03Nonces.Add(command.CommandId)) return;
            var route = command.Action switch
            {
                "pull" => "models.pull", "importGguf" => "models.gguf.import",
                "stop" => "models.cancel", "retry" => "models.retry",
                "diagnose" => "models.preflight", _ => ""
            };
            // A native cancellation request must overtake a pending STOP.
            var activeStopToken = command.Action == "stop" ? CancellationToken.None : stopGeneration;
            var accepted = false;
            var reason = "NOT_AUTHORIZED";
            if (NativeP02Acl(sid, route) &&
                (command.Action is "stop" or "diagnose" ||
                 await ConfirmP02NativeAsync(route, root, activeStopToken)))
            {
                // Native consent may show a modal dialog. Reject a stale
                // document, revoked SID or changed ACL BEFORE any mutation.
                if (activeStopToken.IsCancellationRequested ||
                    Interlocked.Read(ref _nativeDocumentEpoch) != epoch ||
                    _nativeP02Core is null || !IsP03Document(_nativeP02Core.Source) ||
                    !NativeP02Acl(sid, route)) return;
                JsonElement payload = JsonSerializer.SerializeToElement(new {});
                if (command.Action is "stop" or "retry")
                    payload = JsonSerializer.SerializeToElement(new { jobId = command.JobId!.Value.ToString("D") });
                else if (command.Action is "pull" or "importGguf")
                {
                    var id = command.Action == "pull" ? command.ModelId :
                        root.TryGetProperty("modelId", out var selected) && selected.ValueKind == JsonValueKind.String ?
                            selected.GetString() : null;
                    var allowed = reviewed.Where(x => x.Id == id && x.CanOfferOneClickPull).Take(2).ToArray();
                    if (allowed.Length == 1)
                        payload = JsonSerializer.SerializeToElement(new { modelTag = allowed[0].ExactTag });
                    else reason = "REVIEW_REQUIRED";
                }
                if (reason != "REVIEW_REQUIRED")
                {
                    activeStopToken.ThrowIfCancellationRequested();
                    var result = await _nativeModels.ExecuteAsync(route, payload,
                        command.Action is not ("stop" or "diagnose"), activeStopToken);
                    accepted = command.Action != "stop" ||
                        result.TryGetProperty("cancelled", out var flag) &&
                        flag.ValueKind == JsonValueKind.True;
                    reason = accepted ? "" : "STOP_PENDING";
                }
            }
            if (!activeStopToken.IsCancellationRequested &&
                _nativeP02Core is { } web && IsP03Document(web.Source) &&
                Interlocked.Read(ref _nativeDocumentEpoch) == epoch &&
                NativeP02Acl(sid, "models.queue"))
            {
                web.PostWebMessageAsJson(ModelWowBridgeContract.AckJson(command, accepted, reason));
                await PublishP03SnapshotAsync(epoch, CancellationToken.None);
            }
        }
        catch (Exception ex)
        {
            Trace.TraceError("P03_MICROWOW_COMMAND_HOLD {0}", ex.GetType().Name);
            // No false ACK or connection state on an unverified owner failure.
        }
    }

    private void ShutdownNativeP02()
    {
        // Revoke any pending one-shot A1 consent and erase the child-only
        // HMAC material BEFORE tearing down the existing private child pipe.
        // A later restart must never inherit an old owner ticket or key.
        _a1OwnerApprovedAction=null;
        _a1OwnerApprovedEpoch=0;
        _a1OwnerProofRunId=null;
        if (_a1OwnerProofKey is not null) {
            CryptographicOperations.ZeroMemory(_a1OwnerProofKey);
            _a1OwnerProofKey=null;
        }
        try{_nativeModelsStop.Cancel();}catch(ObjectDisposedException){}
        _nativeModelsStop.Dispose();
        _nativeModelsStopDisposed=true;
        if (_nativeP02Core is { } web) {
            web.WebMessageReceived -= OnP03WebMessageReceived;
            web.NavigationStarting -= OnNativeP02NavigationStarting;
            web.SourceChanged -= OnNativeP02SourceChanged;
            web.ContentLoading -= OnNativeP02ContentLoading;
            if (_nativeBrowserFilter is not null) web.WebResourceRequested -= _nativeBrowserFilter;
            if (_nativeBrowserOnShell is not null) web.ContentLoading -= _nativeBrowserOnShell;
        }
        _nativeBrowserFilter=null;_nativeBrowserOnShell=null;_nativeBrowserFenceInstalled=false;
        Interlocked.Increment(ref _nativeDocumentEpoch);_nativeP02Core=null;
        HideNativeBrowserBack();
        _nativeP02Bridge?.Dispose();_nativeP02Bridge=null;
        _nativeModels?.Dispose();_nativeModels=null;
        var child=_nativeP02Process;_nativeP02Process=null;
        try {if(child is not null && !child.HasExited)child.Kill(entireProcessTree:true);}catch{}
        child?.Dispose();
        if(_nativeP02Pipe is not null)_=_nativeP02Pipe.DisposeAsync();
        _nativeP02Pipe=null;
    }
}

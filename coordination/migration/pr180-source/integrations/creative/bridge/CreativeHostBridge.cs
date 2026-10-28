// NOX HELION · E06 R13 creative bridge; one trusted WPF host, on-demand hidden worker.
// NOX's original D02, 8 CoreID, chat, STOP and windows owner controls are unchanged.
using System;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Collections.Concurrent;
using System.IO;
using System.Text.Json;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Microsoft.Web.WebView2.Core;

namespace NoxP01;
public partial class MainWindow
{
    private readonly SemaphoreSlim _creativeStartGate = new(1,1);
    private readonly SemaphoreSlim _creativeWriteGate = new(1,1);
    private Process? _creativeWorker;
    private readonly ConcurrentDictionary<string,byte> _creativePending = new(StringComparer.Ordinal);
    private Window? _creativeProjector;

    private async Task DispatchCreativeAsync(JsonElement message)
    {
        var requestId=GetString(message,"requestId");
        if (!Guid.TryParseExact(requestId, "D", out _) ||
            !message.TryGetProperty("payload",out var payload) ||
            payload.ValueKind!=JsonValueKind.Object || Encoding.UTF8.GetByteCount(payload.GetRawText())>262144)
        {
            PostMessage(new {kind="creativeResult",requestId,ok=false,error="Invalid trusted creative request"});
            return;
        }
        var action=GetString(payload,"action");
        if (action=="native_import") { ImportCreativeAsset(requestId!,payload); return; }
        if (action=="stop")
        {
            StopCreativeWorker();
            PostMessage(new {kind="creativeResult",requestId,ok=true,
                data=new {status="STOPPED",source="NATIVE_PROCESS_TREE_TERMINATION_REQUESTED"}});
            return;
        }
        if (action=="download")
        {
            // Reuse existing approved P03 ModelCenter instead of starting a second
            // Hugging Face/Ollama downloader with competing queue and cancellation.
            try
            {
                OpenModelCenter();
                PostMessage(new {kind="creativeResult",requestId,ok=true,
                    data=new {status="OWNER_WINDOW_OPEN_REQUESTED",owner="P03",
                        message="Выбери нужные веса в едином NOX ModelCenter. Загрузка не запущена автоматически."}});
            }
            catch(Exception ex)
            {
                WriteLog("CREATIVE_P03_ROUTE " + ex.GetType().Name);
                PostMessage(new {kind="creativeResult",requestId,ok=false,error="NOX ModelCenter unavailable"});
            }
            return;
        }
        try
        {
            _creativePending.TryAdd(requestId!,0);
            var worker=await EnsureCreativeWorkerAsync();
            var line=JsonSerializer.Serialize(new {request_id=requestId,payload});
            await _creativeWriteGate.WaitAsync();
            try
            {
                if (worker.HasExited) throw new InvalidOperationException("Creative worker exited");
                await worker.StandardInput.WriteLineAsync(line);
                await worker.StandardInput.FlushAsync();
            }
            finally { _creativeWriteGate.Release(); }
        }
        catch (Exception ex)
        {
            _creativePending.TryRemove(requestId!,out _);
            WriteLog("CREATIVE_DISPATCH_FAILED "+ex.GetType().Name);
            PostMessage(new {kind="creativeResult",requestId,ok=false,error="Creative engine offline; check the installed worker and runtime"});
        }
    }

    // E06 source-trust fix: the installed worker must match the existing P01
    // signed-payload SHA manifest. Manifest + ACL/installer provenance are separate
    // release gates; this is not an Authenticode signature or native E07 proof.
    private static void AssertPinnedCreativeWorker(string worker)
    {
        var root=Path.GetFullPath(AppContext.BaseDirectory);
        var backend=Path.Combine(root,"Backend");
        var creative=Path.Combine(backend,"Creative");
        var expected=Path.Combine(creative,"NOX_CreativeWorker.exe");
        var full=Path.GetFullPath(worker);
        if (!string.Equals(full,expected,StringComparison.OrdinalIgnoreCase))
            throw new IOException("CREATIVE_WORKER_FIXED_PATH_REQUIRED");
        var manifest=Path.Combine(root,"payload.sha256.json");
        foreach (var item in new[]{root,backend,creative,full,manifest})
        {
            if (!File.Exists(item) && !Directory.Exists(item))
                throw new IOException("CREATIVE_PAYLOAD_INPUT_MISSING");
            if ((File.GetAttributes(item) & FileAttributes.ReparsePoint)!=0)
                throw new IOException("CREATIVE_PAYLOAD_REPARSE_HOLD");
        }
        var manifestInfo=new FileInfo(manifest);
        if (manifestInfo.Length<64 || manifestInfo.Length>4_194_304)
            throw new IOException("CREATIVE_MANIFEST_SIZE_HOLD");
        using var json=JsonDocument.Parse(File.ReadAllBytes(manifest));
        var doc=json.RootElement;
        if (doc.ValueKind!=JsonValueKind.Object ||
            !doc.TryGetProperty("schema",out var schema) ||
            schema.GetString()!="NOX_P01_PAYLOAD_SHA256_V1" ||
            !doc.TryGetProperty("files",out var entries) ||
            entries.ValueKind!=JsonValueKind.Array)
            throw new IOException("CREATIVE_PAYLOAD_MANIFEST_SCHEMA_HOLD");
        string? pinned=null; long size=-1; int matches=0;
        foreach (var entry in entries.EnumerateArray())
        {
            if (entry.ValueKind!=JsonValueKind.Object ||
                !entry.TryGetProperty("path",out var path) ||
                path.ValueKind!=JsonValueKind.String) continue;
            if (!string.Equals(path.GetString(),"Backend/Creative/NOX_CreativeWorker.exe",
                               StringComparison.OrdinalIgnoreCase)) continue;
            matches++;
            if (!entry.TryGetProperty("sha256",out var digest) ||
                digest.ValueKind!=JsonValueKind.String ||
                !entry.TryGetProperty("bytes",out var length) ||
                !length.TryGetInt64(out size) || size<=0)
                throw new IOException("CREATIVE_MANIFEST_WORKER_ENTRY_HOLD");
            pinned=digest.GetString();
        }
        if (matches!=1 || pinned is null || pinned.Length!=64 ||
            !Regex.IsMatch(pinned,@"\A[0-9a-fA-F]{64}\z") ||
            new FileInfo(full).Length!=size)
            throw new IOException("CREATIVE_WORKER_NOT_EXACTLY_PINNED");
        // Fail closed on altered bytes. The canonical installer must separately
        // protect its own manifest/install root from user modification.
        using var stream=new FileStream(full,FileMode.Open,FileAccess.Read,FileShare.Read);
        var observed=SHA256.HashData(stream);
        if (!CryptographicOperations.FixedTimeEquals(observed,Convert.FromHexString(pinned)))
            throw new IOException("CREATIVE_WORKER_SHA256_MISMATCH_HOLD");
    }

    private async Task<Process> EnsureCreativeWorkerAsync()
    {
        await _creativeStartGate.WaitAsync();
        try
        {
            if (_creativeWorker is {HasExited:false} existing)return existing;
            var path=Path.Combine(AppContext.BaseDirectory,"Backend","Creative","NOX_CreativeWorker.exe");
            AssertPinnedCreativeWorker(path);
            var start=new ProcessStartInfo(path)
            {
                UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,
                RedirectStandardOutput=true,RedirectStandardError=true,
                WorkingDirectory=Path.GetDirectoryName(path)!,WindowStyle=ProcessWindowStyle.Hidden,
                StandardInputEncoding=Encoding.UTF8,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
            };
            start.ArgumentList.Add(Path.Combine(_data,"creative"));
            var process=Process.Start(start) ?? throw new InvalidOperationException("Worker startup failed");
            _creativeWorker=process;
            _=Task.Run(async () =>
            {
                try
                {
                    while (await process.StandardOutput.ReadLineAsync() is { } line)
                    {
                        if (line.Length>8_000_000) { WriteLog("CREATIVE_RESPONSE_TOO_LARGE"); continue; }
                        using var doc=JsonDocument.Parse(line);
                        if (!doc.RootElement.TryGetProperty("request_id",out var id) || id.ValueKind!=JsonValueKind.String ||
                            !Guid.TryParseExact(id.GetString(),"D",out _))continue;
                        if (!_creativePending.TryRemove(id.GetString()!,out _)) continue;
                        var ok=doc.RootElement.TryGetProperty("ok",out var good) && good.ValueKind==JsonValueKind.True;
                        object response=ok
                            ? new {kind="creativeResult",requestId=id.GetString(),ok=true,data=doc.RootElement.GetProperty("data").Clone()}
                            : new {kind="creativeResult",requestId=id.GetString(),ok=false,error=doc.RootElement.TryGetProperty("error",out var er)?er.GetString():"Worker error"};
                        await Dispatcher.InvokeAsync(()=>PostMessage(response));
                    }
                }
                catch(Exception ex){WriteLog("CREATIVE_WORKER_READ "+ex.GetType().Name);}
            });
            _=Task.Run(async () =>
            {
                try
                {
                    // Do not surface arbitrary worker stderr (could contain user data).
                    while(await process.StandardError.ReadLineAsync() is { } _){}
                }
                catch{}
            });
            return process;
        }
        finally{_creativeStartGate.Release();}
    }

    private void ImportCreativeAsset(string requestId, JsonElement payload)
    {
        var project=GetString(payload,"project_id");
        if (project is null || !Regex.IsMatch(project,@"\A[a-zA-Z0-9_-]{1,48}\z"))
        {
            PostMessage(new {kind="creativeResult",requestId,ok=false,error="Choose a safe project ID first"});return;
        }
        var picker=new Microsoft.Win32.OpenFileDialog
        {
            Filter="Media and NOX assets|*.mp4;*.mov;*.webm;*.png;*.jpg;*.jpeg;*.wav;*.mp3;*.srt;*.glb;*.json|All files|*.*",
            CheckFileExists=true,Multiselect=false,Title="NOX · Импорт файла в творческий проект"
        };
        if(picker.ShowDialog(this)!=true)
        {
            PostMessage(new {kind="creativeResult",requestId,ok=false,error="Import cancelled"});return;
        }
        try
        {
            var path=picker.FileName;
            var allowed=new[]{".mp4",".mov",".webm",".png",".jpg",".jpeg",".wav",".mp3",".srt",".glb",".json"};
            if(Array.IndexOf(allowed,Path.GetExtension(path).ToLowerInvariant())<0)throw new InvalidOperationException("Unsupported asset type");
            var size=new FileInfo(path).Length;
            if(size<1 || size>268435456L)throw new InvalidOperationException("Only 1..256 MiB files accepted");
            var folder=Path.Combine(_data,"creative","projects",project,"assets");
            Directory.CreateDirectory(folder);
            var name=Guid.NewGuid().ToString("N")[..10]+"_"+Path.GetFileName(path);
            var dest=Path.Combine(folder,name);
            File.Copy(path,dest,overwrite:false);
            PostMessage(new {kind="creativeResult",requestId,ok=true,data=new {status="IMPORTED",project_id=project,path="assets/"+name,bytes=size}});
        }
        catch(Exception ex)
        {
            WriteLog("CREATIVE_IMPORT "+ex.GetType().Name);
            PostMessage(new {kind="creativeResult",requestId,ok=false,error="Cannot import selected media; check type, size and destination"});
        }
    }

    private string? _creativeProjectorProjectId;

    private async Task OpenCreativeProjectorAsync(string? requestedProjectId = null)
    {
        try
        {
            // Never accept a path, URL, encoded slash, or arbitrary Windows file.
            // The user must explicitly select a project in the trusted NOX studio.
            string? projectId = null;
            string? projectRoot = null;
            if (!string.IsNullOrEmpty(requestedProjectId))
            {
                if (!Regex.IsMatch(requestedProjectId, @"\A[a-zA-Z0-9_-]{1,48}\z"))
                    throw new InvalidOperationException("Invalid NOX project identity");
                projectRoot = Path.Combine(_data, "creative", "projects");
                var projectFolder = Path.Combine(projectRoot, requestedProjectId);
                var movie = Path.Combine(projectFolder, "NOX_MOVIE_FINAL.mp4");
                // Fail closed on junction/symlink redirection; don't expose wider data roots.
                if (Directory.Exists(projectRoot) && Directory.Exists(projectFolder) && File.Exists(movie) &&
                    (new DirectoryInfo(projectRoot).Attributes & FileAttributes.ReparsePoint) == 0 &&
                    (new DirectoryInfo(projectFolder).Attributes & FileAttributes.ReparsePoint) == 0 &&
                    (new FileInfo(movie).Attributes & FileAttributes.ReparsePoint) == 0 &&
                    new FileInfo(movie).Length > 0)
                    projectId = requestedProjectId;
                else
                    WriteLog("CREATIVE_PROJECTOR_MP4_NOT_READY");
            }
            if(_creativeProjector is {IsVisible:true} current)
            {
                if (string.Equals(_creativeProjectorProjectId, projectId, StringComparison.Ordinal))
                { current.Activate(); return; }
                // A new selected movie must not leave the old projector playing.
                current.Close();
            }
            var theater=new Window{Title="NOX HELION · CINEMA / PROJECTOR",Width=1100,Height=700,
                MinWidth=350,MinHeight=300,Owner=this,WindowStartupLocation=WindowStartupLocation.CenterOwner};
            var viewer=new Microsoft.Web.WebView2.Wpf.WebView2();
            theater.Content=viewer;
            _creativeProjector=theater;
            _creativeProjectorProjectId=projectId;
            theater.Closed+=(_,_)=>{
                if(ReferenceEquals(_creativeProjector,theater)){
                    _creativeProjector=null;_creativeProjectorProjectId=null;
                }
            };
            theater.Show();
            var env=View.CoreWebView2?.Environment ?? throw new InvalidOperationException("WebView2 is offline");
            await viewer.EnsureCoreWebView2Async(env);
            viewer.CoreWebView2.Settings.AreHostObjectsAllowed=false;
            viewer.CoreWebView2.Settings.AreDevToolsEnabled=false;
            viewer.CoreWebView2.Settings.IsWebMessageEnabled=false;
            viewer.CoreWebView2.NewWindowRequested+=(_,e)=>{e.Handled=true;};
            viewer.CoreWebView2.NavigationStarting+=(_,e)=>{
                if(!Uri.TryCreate(e.Uri,UriKind.Absolute,out var uri) || uri.Scheme!="https" ||
                   !uri.Host.Equals("nox.local",StringComparison.OrdinalIgnoreCase))e.Cancel=true;
            };
            viewer.CoreWebView2.SetVirtualHostNameToFolderMapping("nox.local",
                Path.Combine(AppContext.BaseDirectory,"Assets"),CoreWebView2HostResourceAccessKind.DenyCors);
            var theaterUrl="https://nox.local/creative/theater.html";
            if(projectId is not null && projectRoot is not null)
            {
                // Separate virtual origin: media as <video src> only; CORS fetch denied.
                // No Python server, unrestricted file:// access, or privileged JS bridge.
                viewer.CoreWebView2.SetVirtualHostNameToFolderMapping(
                    "nox-projects.invalid",projectRoot,CoreWebView2HostResourceAccessKind.DenyCors);
                theaterUrl += "?local_project_media=1&project="+Uri.EscapeDataString(projectId);
            }
            viewer.CoreWebView2.Navigate(theaterUrl);
        }
        catch(Exception ex){WriteLog("CREATIVE_PROJECTOR "+ex.GetType().Name);}
    }

    private void StopCreativeWorker()
    {
        try { if(_creativeWorker is {HasExited:false} p)p.Kill(entireProcessTree:true); }
        catch(Exception ex) { WriteLog("CREATIVE_WORKER_STOP "+ex.GetType().Name); }
        foreach(var pending in _creativePending.Keys)
        {
            if(_creativePending.TryRemove(pending,out _))
                PostMessage(new {kind="creativeResult",requestId=pending,ok=false,error="STOPPED_BY_USER"});
        }
    }
}
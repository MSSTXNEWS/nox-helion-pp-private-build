// NOX HELION · E06 R13 creative bridge; one trusted WPF host, on-demand hidden worker.
// NOX's original D02, 8 CoreID, chat, STOP and windows owner controls are unchanged.
using System;
using System.Diagnostics;
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
            payload.ValueKind!=JsonValueKind.Object || payload.GetRawText().Length>262144)
        {
            PostMessage(new {kind="creativeResult",requestId,ok=false,error="Invalid trusted creative request"});
            return;
        }
        var action=GetString(payload,"action");
        if (action=="native_import") { ImportCreativeAsset(requestId!,payload); return; }
        if (action=="open_browser") { OpenCreativeBrowser(requestId!,payload); return; }
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

    private async Task<Process> EnsureCreativeWorkerAsync()
    {
        await _creativeStartGate.WaitAsync();
        try
        {
            if (_creativeWorker is {HasExited:false} existing)return existing;
            var path=Path.Combine(AppContext.BaseDirectory,"Backend","Creative","NOX_CreativeWorker.exe");
            if (!File.Exists(path)) throw new FileNotFoundException("The signed-payload creative worker is unavailable");
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

    private void OpenCreativeBrowser(string requestId, JsonElement payload)
    {
        // Existing system browser, not a second WebView2 host. Only approved public model-card origins.
        var target = GetString(payload, "url");
        var valid = target is not null && target.Length <= 2048 &&
            Uri.TryCreate(target, UriKind.Absolute, out var parsed) &&
            parsed.Scheme == Uri.UriSchemeHttps && parsed.IsDefaultPort &&
            string.IsNullOrEmpty(parsed.UserInfo) &&
            (parsed.IdnHost.Equals("huggingface.co", StringComparison.OrdinalIgnoreCase) ||
             parsed.IdnHost.Equals("github.com", StringComparison.OrdinalIgnoreCase));
        if (!valid)
        {
            PostMessage(new {kind="creativeResult",requestId,ok=false,error="HTTPS model-card origin not approved"});
            return;
        }
        try
        {
            Process.Start(new ProcessStartInfo(target!) { UseShellExecute = true });
            PostMessage(new {kind="creativeResult",requestId,ok=true,
                data=new {status="SYSTEM_BROWSER_DISPATCHED",navigationAccepted=false}});
        }
        catch (Exception ex)
        {
            WriteLog("CREATIVE_BROWSER " + ex.GetType().Name);
            PostMessage(new {kind="creativeResult",requestId,ok=false,error="System browser could not be launched"});
        }
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

    private async Task OpenCreativeProjectorAsync()
    {
        try
        {
            if(_creativeProjector is {IsVisible:true} current){current.Activate();return;}
            var theater=new Window{Title="NOX HELION · CINEMA / PROJECTOR",Width=1100,Height=700,
                MinWidth=350,MinHeight=300,Owner=this,WindowStartupLocation=WindowStartupLocation.CenterOwner};
            var viewer=new Microsoft.Web.WebView2.Wpf.WebView2();
            theater.Content=viewer;
            _creativeProjector=theater;
            theater.Closed+=(_,_)=>{if(ReferenceEquals(_creativeProjector,theater))_creativeProjector=null;};
            theater.Show();
            var env=View.CoreWebView2?.Environment ?? throw new InvalidOperationException("WebView2 is offline");
            await viewer.EnsureCoreWebView2Async(env);
            viewer.CoreWebView2.Settings.AreHostObjectsAllowed=false;
            viewer.CoreWebView2.Settings.AreDevToolsEnabled=false;
            viewer.CoreWebView2.Settings.IsWebMessageEnabled=false;
            viewer.CoreWebView2.NewWindowRequested+=(_,e)=>{e.Handled=true;};
            viewer.CoreWebView2.NavigationStarting+=(_,e)=>{
                if(!Uri.TryCreate(e.Uri,UriKind.Absolute,out var uri) || uri.Scheme!="https" || !uri.Host.Equals("nox.local",StringComparison.OrdinalIgnoreCase))e.Cancel=true;
            };
            viewer.CoreWebView2.SetVirtualHostNameToFolderMapping("nox.local",Path.Combine(AppContext.BaseDirectory,"Assets"),CoreWebView2HostResourceAccessKind.DenyCors);
            viewer.CoreWebView2.Navigate("https://nox.local/creative/theater.html");
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
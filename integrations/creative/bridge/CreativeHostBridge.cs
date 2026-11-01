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
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using Microsoft.Web.WebView2.Wpf;

namespace NoxP01;
public partial class MainWindow
{
    private readonly SemaphoreSlim _creativeStartGate = new(1,1);
    private readonly SemaphoreSlim _creativeWriteGate = new(1,1);
    private Process? _creativeWorker;
    private readonly ConcurrentDictionary<string,byte> _creativePending = new(StringComparer.Ordinal);
    private Window? _creativeProjector;
    private string? _creativeProjectorProjectId;

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
            // STOP is not accepted merely because Kill was requested. The
            // existing worker must actually exit before success is reported.
            var stopResult=await StopCreativeWorkerAsync();
            if (stopResult=="STOPPED" || stopResult=="NO_ACTIVE_WORKER")
                PostMessage(new {kind="creativeResult",requestId,ok=true,
                    data=new {status=stopResult,source=stopResult=="STOPPED"
                        ? "NATIVE_WORKER_EXIT_VERIFIED" : "NATIVE_NO_ACTIVE_WORKER"}});
            else
                PostMessage(new {kind="creativeResult",requestId,ok=false,
                    error="CREATIVE_STOP_NOT_CONFIRMED"});
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
            // Only the first in-flight request may own this GUID. Never send a
            // duplicate to the original worker or remove the first receipt.
            if (!_creativePending.TryAdd(requestId!,0))
            {
                WriteLog("CREATIVE_DUPLICATE_REQUEST_ID");
                return;
            }
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

    // Runtime payload consistency check. This deliberately reuses the existing
    // P01 SHA-256 installer manifest; no second installer or worker is introduced.
    // NOTE: A writable manifest is not an immutable trust anchor. The E06 host
    // still owns installer ACL/signature attestation and Windows E07 acceptance.
    private static FileStream HoldApprovedCreativeWorker(string workerPath)
    {
        const string ownerRelative = "Backend/Creative/NOX_CreativeWorker.exe";
        var root = Path.GetFullPath(AppContext.BaseDirectory)
            .TrimEnd(Path.DirectorySeparatorChar);
        var approved = Path.Combine(root, "Backend", "Creative", "NOX_CreativeWorker.exe");
        if (!string.Equals(Path.GetFullPath(workerPath), approved,
                StringComparison.OrdinalIgnoreCase))
            throw new IOException("CREATIVE_WORKER_PATH_NOT_APPROVED");

        // Reject junctions/symlinks in every installed parent up to the
        // application root. The installer already performs the same kind of
        // check during staging; this rejects post-install link substitutions.
        for (var dir = new DirectoryInfo(Path.GetDirectoryName(approved)!); ; dir = dir.Parent!)
        {
            if (!dir.Exists || (dir.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new IOException("CREATIVE_WORKER_PARENT_REPARSE_HOLD");
            if (string.Equals(dir.FullName.TrimEnd(Path.DirectorySeparatorChar),
                    root, StringComparison.OrdinalIgnoreCase))
                break;
            if (dir.Parent is null)
                throw new IOException("CREATIVE_WORKER_OUTSIDE_APPROVED_ROOT");
        }
        var item = new FileInfo(approved);
        if (!item.Exists || (item.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new IOException("CREATIVE_WORKER_NOT_REGULAR");
        var manifestPath = Path.Combine(root, "payload.sha256.json");
        var manifestFile = new FileInfo(manifestPath);
        if (!manifestFile.Exists || (manifestFile.Attributes & FileAttributes.ReparsePoint) != 0
                || manifestFile.Length is <= 0 or > 16_777_216)
            throw new IOException("CREATIVE_PAYLOAD_MANIFEST_HOLD");
        long expectedLength = -1;
        string? expectedHash = null;
        using (var manifestStream = new FileStream(manifestPath, FileMode.Open,
                   FileAccess.Read, FileShare.Read))
        using (var manifest = JsonDocument.Parse(manifestStream))
        {
            var document = manifest.RootElement;
            if (document.ValueKind != JsonValueKind.Object ||
                !document.TryGetProperty("schema", out var schema) ||
                schema.GetString() != "NOX_P01_PAYLOAD_SHA256_V1" ||
                !document.TryGetProperty("files", out var list) ||
                list.ValueKind != JsonValueKind.Array)
                throw new IOException("CREATIVE_PAYLOAD_SCHEMA_HOLD");
            int matches = 0;
            foreach (var entry in list.EnumerateArray())
            {
                if (entry.ValueKind != JsonValueKind.Object ||
                    !entry.TryGetProperty("path", out var pathValue) ||
                    pathValue.ValueKind != JsonValueKind.String)
                    throw new IOException("CREATIVE_PAYLOAD_ENTRY_HOLD");
                if (pathValue.GetString()?.Replace('\\', '/') != ownerRelative)
                    continue;
                matches++;
                if (matches != 1 ||
                    !entry.TryGetProperty("bytes", out var byteCount) ||
                    !byteCount.TryGetInt64(out expectedLength) || expectedLength <= 0 ||
                    !entry.TryGetProperty("sha256", out var shaValue) ||
                    shaValue.ValueKind != JsonValueKind.String)
                    throw new IOException("CREATIVE_PAYLOAD_WORKER_RECORD_HOLD");
                expectedHash = shaValue.GetString();
                if (expectedHash is null || !Regex.IsMatch(expectedHash,
                        @"\A[a-fA-F0-9]{64}\z"))
                    throw new IOException("CREATIVE_PAYLOAD_SHA_FORMAT_HOLD");
            }
            if (matches != 1)
                throw new IOException("CREATIVE_PAYLOAD_PIN_MISSING_OR_DUPLICATED");
        }
        // Keep an open read-only handle without FILE_SHARE_DELETE while
        // creating the process, so path replacement cannot race the hash
        // check on a normal Windows/NTFS installation.
        var handle = new FileStream(approved, FileMode.Open, FileAccess.Read, FileShare.Read);
        try
        {
            if (handle.Length != expectedLength ||
                !string.Equals(Convert.ToHexString(SHA256.HashData(handle)),
                    expectedHash, StringComparison.OrdinalIgnoreCase))
                throw new IOException("CREATIVE_WORKER_SHA256_MISMATCH");
            return handle;
        }
        catch
        {
            handle.Dispose();
            throw;
        }
    }

    // An untrusted child may emit an 8 MiB+ line WITHOUT a newline.
    // StreamReader.ReadLineAsync would allocate the whole line before its
    // length is checked. Keep only a bounded chunk buffer and discard the
    // oversize frame through its delimiter, without losing later frames.
    private sealed class BoundedCreativeLineReader(StreamReader source)
    {
        private readonly char[] _chunk = new char[4096];
        private int _position, _length;

        public async Task<(string? Text, bool Oversized)> ReadAsync()
        {
            var line = new StringBuilder();
            var oversize = false;
            while (true)
            {
                if (_position >= _length)
                {
                    _length = await source.ReadAsync(_chunk.AsMemory()).ConfigureAwait(false);
                    _position = 0;
                    if (_length == 0)
                        return (oversize ? string.Empty : line.Length == 0 ? null : line.ToString(), oversize);
                }
                var ch = _chunk[_position++];
                if (ch == '\n')
                {
                    if (!oversize && line.Length != 0 && line[line.Length - 1] == '\r')
                        line.Length--;
                    return (oversize ? string.Empty : line.ToString(), oversize);
                }
                if (!oversize)
                {
                    if (line.Length >= 8_000_000) { oversize = true; line.Clear(); }
                    else line.Append(ch);
                }
            }
        }
    }

    private async Task<Process> EnsureCreativeWorkerAsync()
    {
        await _creativeStartGate.WaitAsync();
        try
        {
            if (_creativeWorker is {HasExited:false} existing)return existing;
            var path=Path.Combine(AppContext.BaseDirectory,"Backend","Creative","NOX_CreativeWorker.exe");
            using var verifiedWorker = HoldApprovedCreativeWorker(path);
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
                    var reader = new BoundedCreativeLineReader(process.StandardOutput);
                    while (true)
                    {
                        var (line, oversized) = await reader.ReadAsync();
                        if (line is null) break;
                        if (oversized) { WriteLog("CREATIVE_RESPONSE_TOO_LARGE"); continue; }
                        // A malformed frame must not kill the long-lived reader:
                        // handle each line independently and preserve later pending requests.
                        try
                        {
                            using var doc=JsonDocument.Parse(line);
                            var record=doc.RootElement;
                            if (doc.RootElement.ValueKind!=JsonValueKind.Object)
                            {
                                WriteLog("CREATIVE_STDOUT_NOT_OBJECT");
                                continue;
                            }
                            if (!record.TryGetProperty("request_id",out var id) || id.ValueKind!=JsonValueKind.String ||
                                !Guid.TryParseExact(id.GetString(),"D",out _))continue;
                            var responseId=id.GetString()!;
                            if (!_creativePending.TryRemove(responseId,out _)) continue;
                            var ok=record.TryGetProperty("ok",out var good) && good.ValueKind==JsonValueKind.True;
                            object response;
                            if (ok && record.TryGetProperty("data",out var data))
                                response=new {kind="creativeResult",requestId=responseId,ok=true,data=data.Clone()};
                            else
                            {
                                var errorText=ok ? "Creative worker response missing data" :
                                    record.TryGetProperty("error",out var er) && er.ValueKind==JsonValueKind.String
                                        ? er.GetString() : "Worker error";
                                response=new {kind="creativeResult",requestId=responseId,ok=false,error=errorText};
                            }
                            await Dispatcher.InvokeAsync(()=>PostMessage(response));
                        }
                        catch(JsonException) { WriteLog("CREATIVE_STDOUT_INVALID_JSON"); }
                        catch(InvalidOperationException) { WriteLog("CREATIVE_STDOUT_INVALID_SHAPE"); }
                    }
                }
                catch(Exception ex){WriteLog("CREATIVE_WORKER_READ "+ex.GetType().Name);}
            });
            _=Task.Run(async () =>
            {
                try
                {
                    // Do not surface arbitrary worker stderr (could contain user data).
                    var discard = new char[4096];
                    while (await process.StandardError.ReadAsync(discard.AsMemory()).ConfigureAwait(false) > 0) { }
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
            var trustedRoot=Path.GetFullPath(_data).TrimEnd(Path.DirectorySeparatorChar,Path.AltDirectorySeparatorChar);
            var fullFolder=Path.GetFullPath(folder);
            if (!fullFolder.StartsWith(trustedRoot+Path.DirectorySeparatorChar,
                    StringComparison.OrdinalIgnoreCase))
                throw new IOException("CREATIVE_IMPORT_OUTSIDE_DATA_ROOT");
            // Reject an existing junction/symlink at any directory ancestor,
            // including the data root, before creating or writing the import.
            // Windows E07 must still verify directory-swap races and ACL.
            void VerifyTrustedFolder()
            {
                for (DirectoryInfo? node=new DirectoryInfo(fullFolder);
                     node is not null; node=node.Parent)
                {
                    if (node.Exists && (node.Attributes & FileAttributes.ReparsePoint)!=0)
                        throw new IOException("CREATIVE_IMPORT_REPARSE_HOLD");
                }
            }
            VerifyTrustedFolder();
            Directory.CreateDirectory(folder);
            VerifyTrustedFolder();
            var name=Guid.NewGuid().ToString("N")[..10]+"_"+Path.GetFileName(path);
            var dest=Path.Combine(folder,name);
            VerifyTrustedFolder();
            File.Copy(path,dest,overwrite:false);
            PostMessage(new {kind="creativeResult",requestId,ok=true,data=new {status="IMPORTED",project_id=project,path="assets/"+name,bytes=size}});
        }
        catch(Exception ex)
        {
            WriteLog("CREATIVE_IMPORT "+ex.GetType().Name);
            PostMessage(new {kind="creativeResult",requestId,ok=false,error="Cannot import selected media; check type, size and destination"});
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NoxRect { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
    private struct NoxMonitorInfo
    {
        public uint Size;
        public NoxRect Bounds, Work;
        public uint Flags;
        [MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)] public string Device;
    }
    private sealed record NoxMonitor(string Device, NoxRect Bounds, bool Primary);
    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate bool NoxEnumMonitor(IntPtr monitor,IntPtr hdc,ref NoxRect bounds,IntPtr data);
    [DllImport("user32.dll",SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumDisplayMonitors(IntPtr hdc,IntPtr clip,NoxEnumMonitor callback,IntPtr data);
    [DllImport("user32.dll",EntryPoint="GetMonitorInfoW",CharSet=CharSet.Unicode,SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetMonitorInfoW(IntPtr monitor,ref NoxMonitorInfo info);
    [DllImport("user32.dll",SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowPos(IntPtr hwnd,IntPtr insertAfter,int x,int y,int width,int height,uint flags);
    [DllImport("user32.dll",SetLastError=true)]
    private static extern IntPtr MonitorFromWindow(IntPtr hwnd,uint flags);

    private static List<NoxMonitor> NoxConnectedMonitors()
    {
        var screens=new List<NoxMonitor>();
        NoxEnumMonitor callback=(IntPtr monitor,IntPtr hdc,ref NoxRect ignored,IntPtr data)=>{
            var info=new NoxMonitorInfo{Size=(uint)Marshal.SizeOf<NoxMonitorInfo>(),Device=string.Empty};
            if(GetMonitorInfoW(monitor,ref info) && info.Bounds.Right>info.Bounds.Left &&
               info.Bounds.Bottom>info.Bounds.Top && !string.IsNullOrWhiteSpace(info.Device))
                screens.Add(new NoxMonitor(info.Device.TrimEnd('\0'),info.Bounds,(info.Flags&1u)!=0));
            return true;
        };
        if(!EnumDisplayMonitors(IntPtr.Zero,IntPtr.Zero,callback,IntPtr.Zero))
            return new List<NoxMonitor>();
        screens.Sort((a,b)=>b.Primary.CompareTo(a.Primary));
        return screens;
    }

    private static WebView2? FindNoxTheaterViewer(Window theater)
    {
        if(theater.Content is DockPanel container)
            foreach(UIElement child in container.Children)
                if(child is WebView2 viewer) return viewer;
        return theater.Content as WebView2;
    }

    private void AttachNoxProjectorControls(Window theater,WebView2 viewer)
    {
        var layout=new DockPanel{LastChildFill=true};
        // Reuse the obsidian/amber visual language of the approved NOX WORK screen.
        // A WrapPanel preserves controls on 350px mini windows and high-DPI layouts.
        var bar=new WrapPanel{Orientation=Orientation.Horizontal,MinHeight=52,
            Background=new LinearGradientBrush(
                System.Windows.Media.Color.FromRgb(17,27,38),
                System.Windows.Media.Color.FromRgb(4,8,15),90)};
        var picker=new ComboBox{Width=235,MinHeight=44,Margin=new Thickness(6,4,4,4),
            VerticalAlignment=VerticalAlignment.Center};
        var refresh=new Button{Content="Обновить экраны",Margin=new Thickness(3)};
        var select=new Button{Content="Показать на экране",Margin=new Thickness(3)};
        var fullscreen=new Button{Content="Полный экран",Margin=new Thickness(3)};
        var state=new TextBlock{Text="Выберите монитор или проектор",Foreground=new SolidColorBrush(
                System.Windows.Media.Color.FromRgb(178,207,220)),
                Margin=new Thickness(8,4,8,4),VerticalAlignment=VerticalAlignment.Center,
                MaxWidth=280,TextWrapping=TextWrapping.Wrap};
        foreach(Control chrome in new Control[]{picker,refresh,select,fullscreen})
        {
            chrome.Background=new SolidColorBrush(System.Windows.Media.Color.FromRgb(24,33,44));
            chrome.Foreground=new SolidColorBrush(System.Windows.Media.Color.FromRgb(247,224,193));
            chrome.BorderBrush=new SolidColorBrush(System.Windows.Media.Color.FromRgb(171,117,63));
            chrome.BorderThickness=new Thickness(1);
            chrome.Padding=new Thickness(9,5,9,5);
            chrome.MinHeight=44;
        }
        var accent=new SolidColorBrush(System.Windows.Media.Color.FromRgb(222,157,82));
        select.BorderBrush=accent;
        fullscreen.BorderBrush=accent;
        bar.Children.Add(picker);bar.Children.Add(refresh);bar.Children.Add(select);
        bar.Children.Add(fullscreen);bar.Children.Add(state);
        DockPanel.SetDock(bar,Dock.Top);layout.Children.Add(bar);layout.Children.Add(viewer);
        theater.Content=layout;
        // The native window is the fullscreen owner. Collapse the chrome during
        // playback and reveal it on pointer-at-top, preserving a way back to windowed.
        string? device=null;
        bool expanded=false;
        Rect? previousWindowBounds=null;
        var chromeTimer=new System.Windows.Threading.DispatcherTimer{
            Interval=TimeSpan.FromMilliseconds(250)};
        chromeTimer.Tick+=(_,_)=>{
            if(!theater.IsVisible)return;
            if(expanded)
            {
                var y=Mouse.GetPosition(theater).Y;
                bar.Visibility=y>=0 && y<=72?Visibility.Visible:Visibility.Collapsed;
            }
        };
        chromeTimer.Start();
        theater.Closed+=(_,_)=>chromeTimer.Stop();
        void UpdateList()
        {
            var previous=(picker.SelectedItem as ComboBoxItem)?.Tag as NoxMonitor;
            var list=NoxConnectedMonitors();
            picker.Items.Clear();
            foreach(var item in list)
                picker.Items.Add(new ComboBoxItem{Tag=item,
                    Content=(item.Primary?"Основной · ":"Внешний · ")+item.Device+" · "+
                       (item.Bounds.Right-item.Bounds.Left)+"×"+(item.Bounds.Bottom-item.Bounds.Top)});
            if(list.Count==0){state.Text="DISPLAY_HOLD: Windows не обнаружила экранов";return;}
            var index=previous is null?0:list.FindIndex(x=>x.Device==previous.Device);
            picker.SelectedIndex=index<0?0:index;
        }

        bool Move(NoxMonitor requested)
        {
            // Re-read Windows state on each click. Never honor a raw JS monitor index.
            var current=NoxConnectedMonitors().Find(x=>x.Device==requested.Device);
            if(current is null){state.Text="DISPLAY_HOLD: экран отключён";UpdateList();return false;}
            var handle=new WindowInteropHelper(theater).Handle;
            if(handle==IntPtr.Zero){state.Text="DISPLAY_HOLD: окно не готово";return false;}
            var rect=current.Bounds;
            const uint noZOrderNoActivateShow=0x0004u|0x0010u|0x0040u;
            if(!SetWindowPos(handle,IntPtr.Zero,rect.Left,rect.Top,
                  rect.Right-rect.Left,rect.Bottom-rect.Top,noZOrderNoActivateShow))
            {state.Text="DISPLAY_HOLD: перенос отклонён Windows";return false;}
            device=current.Device;
            state.Text="Выбран экран "+current.Device+"; управление фильмом — в плеере";
            return true;
        }

        void ToggleFullscreen()
        {
            if(expanded)
            {
                expanded=false;
                theater.WindowState=WindowState.Normal;
                theater.WindowStyle=WindowStyle.SingleBorderWindow;
                theater.ResizeMode=ResizeMode.CanResize;
                fullscreen.Content="Полный экран";
                bar.Visibility=Visibility.Visible;
                if(previousWindowBounds is { } saved)
                {
                    theater.Left=saved.Left;theater.Top=saved.Top;
                    theater.Width=saved.Width;theater.Height=saved.Height;
                    previousWindowBounds=null;
                }
                if(viewer.CoreWebView2 is not null)
                    _=viewer.CoreWebView2.ExecuteScriptAsync("document.body.classList.remove('projector-fullscreen')");
                state.Text="Обычное окно кинотеатра";
                return;
            }
            var handle=new WindowInteropHelper(theater).Handle;
            if(handle==IntPtr.Zero){state.Text="DISPLAY_HOLD: окно не готово";return;}
            NoxMonitor? monitor=device is null?null:NoxConnectedMonitors().Find(x=>x.Device==device);
            if(monitor is null)
            {
                var nearest=MonitorFromWindow(handle,2u);
                if(nearest!=IntPtr.Zero)
                {
                    var info=new NoxMonitorInfo{Size=(uint)Marshal.SizeOf<NoxMonitorInfo>(),Device=string.Empty};
                    if(GetMonitorInfoW(nearest,ref info))
                        monitor=NoxConnectedMonitors().Find(x=>x.Device==info.Device.TrimEnd('\0'));
                }
            }
            if(monitor is null){state.Text="DISPLAY_HOLD: монитор не найден";return;}
            previousWindowBounds=new Rect(theater.Left,theater.Top,theater.Width,theater.Height);
            theater.WindowState=WindowState.Normal;
            theater.WindowStyle=WindowStyle.None;
            theater.ResizeMode=ResizeMode.NoResize;
            if(!Move(monitor))
            {
                theater.WindowStyle=WindowStyle.SingleBorderWindow;
                theater.ResizeMode=ResizeMode.CanResize;
                previousWindowBounds=null;
                return;
            }
            expanded=true;
            fullscreen.Content="Вернуть окно";
            bar.Visibility=Visibility.Collapsed;
            if(viewer.CoreWebView2 is not null)
                _=viewer.CoreWebView2.ExecuteScriptAsync("document.body.classList.add('projector-fullscreen')");
        }

        refresh.Click+=(_,_)=>UpdateList();
        picker.DropDownOpened+=(_,_)=>UpdateList();
        select.Click+=(_,_)=>{
            if(picker.SelectedItem is not ComboBoxItem entry || entry.Tag is not NoxMonitor monitor)
            {state.Text="DISPLAY_HOLD: сначала выберите экран";return;}
            if(expanded)ToggleFullscreen();
            Move(monitor);
        };
        fullscreen.Click+=(_,_)=>ToggleFullscreen();
        theater.PreviewKeyDown+=(_,e)=>{
            if(e.Key==Key.F11){ToggleFullscreen();e.Handled=true;}
            else if(e.Key==Key.Escape && expanded){ToggleFullscreen();e.Handled=true;}
        };

        HwndSource? source=null;
        HwndSourceHook? hook=null;
        hook=(IntPtr hwnd,int message,IntPtr wparam,IntPtr lparam,ref bool handled)=>{
            if(message==0x007E) // WM_DISPLAYCHANGE
                _=theater.Dispatcher.BeginInvoke(new Action(()=>{
                    if(!theater.IsVisible)return;
                    var current=NoxConnectedMonitors();
                    if(device is not null && !current.Exists(x=>x.Device==device))
                    {
                        device=null;
                        if(expanded)ToggleFullscreen();
                        theater.WindowState=WindowState.Normal;
                        theater.WindowStyle=WindowStyle.SingleBorderWindow;
                        theater.ResizeMode=ResizeMode.CanResize;
                        theater.Width=1100;theater.Height=700;
                        theater.Left=Left+30;theater.Top=Top+30;
                        state.Text="DISPLAY_HOLD: проектор отключён, окно восстановлено";
                        WriteLog("CREATIVE_PROJECTOR_DISPLAY_DISCONNECTED");
                    }
                    UpdateList();
                }));
            return IntPtr.Zero;
        };
        theater.SourceInitialized+=(_,_)=>{
            source=HwndSource.FromHwnd(new WindowInteropHelper(theater).Handle);
            if(source is not null && hook is not null)source.AddHook(hook);
        };
        theater.Closed+=(_,_)=>{
            if(source is not null && hook is not null)source.RemoveHook(hook);
        };
        UpdateList();
    }
    // Reuse the EXISTING WebView2 cinema projector and its local subtitle picker.
    // Caller: trusted WPF/native owner after ACL; this method is NOT a JS endpoint.
    // Opening a window never proves playback or subtitle import.
    private async Task<string> OpenOwnerMediaRouteAsync(
        string routeId, Func<string, bool> nativeConsent, CancellationToken stop)
    {
        if (routeId is not ("media.player" or "media.subtitles"))
            throw new ArgumentOutOfRangeException(nameof(routeId));
        if (nativeConsent is null) throw new ArgumentNullException(nameof(nativeConsent));
        stop.ThrowIfCancellationRequested();
        if (nativeConsent(routeId) != true)
            throw new UnauthorizedAccessException("Native media consent required");
        stop.ThrowIfCancellationRequested();
        if (_creativeProjector is not { IsVisible: true })
            await OpenCreativeProjectorAsync();
        stop.ThrowIfCancellationRequested();
        if (_creativeProjector is not { IsVisible: true } projector ||
            FindNoxTheaterViewer(projector) is not { } viewer ||
            viewer.CoreWebView2 is null)
            return "MEDIA_OWNER_UI_NOT_READY";
        // Existing theater navigations stay under the original exact mapped
        // nox.local origin. WebMessage stays disabled on its viewing instance.
        if (routeId == "media.subtitles")
        {
            var found = await viewer.CoreWebView2.ExecuteScriptAsync(
                "Boolean(document.getElementById('subtitles'))");
            stop.ThrowIfCancellationRequested();
            if (!string.Equals(found, "true", StringComparison.Ordinal))
                return "SUBTITLES_FILE_INPUT_NOT_READY";
            await viewer.CoreWebView2.ExecuteScriptAsync(
                "document.getElementById('subtitles').focus();");
            stop.ThrowIfCancellationRequested();
            return "SUBTITLE_PICKER_READY_NOT_IMPORTED";
        }
        projector.Activate();
        return "MEDIA_PLAYER_UI_OPEN_NOT_PLAYING";
    }

    private async Task OpenCreativeProjectorAsync(string? requestedProjectId = null)
    {
        Window? openingProjector = null;
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
            var theater=new Window{Title="NOX HELION · CINEMA / PROJECTOR",
                Width=Math.Max(320,Math.Min(1100,SystemParameters.WorkArea.Width-20)),
                Height=Math.Max(260,Math.Min(700,SystemParameters.WorkArea.Height-20)),
                MinWidth=320,MinHeight=260,Owner=this,WindowStartupLocation=WindowStartupLocation.CenterOwner};
            openingProjector=theater;
            var viewer=new Microsoft.Web.WebView2.Wpf.WebView2();
            AttachNoxProjectorControls(theater,viewer);
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
            var theaterUrl="https://nox.local/creative/theater.html?nox_native_viewer=1";
            if(projectId is not null && projectRoot is not null)
            {
                // Separate virtual origin: media as <video src> only; CORS fetch denied.
                // No Python server, unrestricted file:// access, or privileged JS bridge.
                viewer.CoreWebView2.SetVirtualHostNameToFolderMapping(
                    "nox-projects.invalid",projectRoot,CoreWebView2HostResourceAccessKind.DenyCors);
                theaterUrl += "&local_project_media=1&project="+Uri.EscapeDataString(projectId);
            }
            viewer.CoreWebView2.Navigate(theaterUrl);
        }
        catch(Exception ex)
        {
            WriteLog("CREATIVE_PROJECTOR "+ex.GetType().Name);
            // A failed WebView2 setup must not leave a blank window marked ready.
            // Only close THIS attempt: a concurrent owner projector may exist.
            if (openingProjector is not null)
            {
                try { openingProjector.Close(); }
                catch(Exception closeEx) { WriteLog("CREATIVE_PROJECTOR_CLOSE "+closeEx.GetType().Name); }
                if (ReferenceEquals(_creativeProjector,openingProjector))
                {
                    _creativeProjector=null;
                    _creativeProjectorProjectId=null;
                }
            }
        }
    }

    private async Task<string> StopCreativeWorkerAsync()
    {
        // Hold the same existing start/write gates so a simultaneous dispatch
        // cannot restart the worker while STOP is being verified.
        await _creativeStartGate.WaitAsync();
        try
        {
            await _creativeWriteGate.WaitAsync();
            try
            {
                var worker=_creativeWorker;
                // Pending requests with no worker can be queued for startup;
                // do not claim they were stopped before their owner confirms.
                if (worker is null && !_creativePending.IsEmpty)
                    return "STOP_UNCONFIRMED";
                if (worker is not null)
                {
                    try
                    {
                        if (!worker.HasExited)
                            worker.Kill(entireProcessTree:true);
                        // Kill() returns before process exit. Never claim STOPPED
                        // until this exact parent worker has observed exit.
                        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(5));
                        await worker.WaitForExitAsync(timeout.Token);
                        if (!worker.HasExited)
                        {
                            WriteLog("CREATIVE_WORKER_STOP_EXIT_NOT_CONFIRMED");
                            return "STOP_UNCONFIRMED";
                        }
                    }
                    catch (Exception ex)
                    {
                        // Preserve in-flight request receipts on timeout/Kill
                        // failure; an unverified worker may still be alive.
                        WriteLog("CREATIVE_WORKER_STOP_UNCONFIRMED "+ex.GetType().Name);
                        return "STOP_UNCONFIRMED";
                    }
                    if (ReferenceEquals(_creativeWorker,worker))
                        _creativeWorker=null;
                }
                // Only a verified stop (or no running worker) is allowed to
                // dismiss existing owner request IDs as STOPPED_BY_USER.
                foreach(var pending in _creativePending.Keys)
                {
                    if(_creativePending.TryRemove(pending,out _))
                        PostMessage(new {kind="creativeResult",requestId=pending,
                            ok=false,error="STOPPED_BY_USER"});
                }
                return worker is null ? "NO_ACTIVE_WORKER" : "STOPPED";
            }
            finally { _creativeWriteGate.Release(); }
        }
        finally { _creativeStartGate.Release(); }
    }
}
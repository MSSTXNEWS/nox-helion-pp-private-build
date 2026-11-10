// T06 · Original MainWindow partial. One WPF/WebView2, one pinned original
// Python process and existing P02 NativePythonPipe. No added HTTP/DB/host.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using Microsoft.Web.WebView2.Core;
using Nox.P02;
namespace NoxP01;
public partial class MainWindow
{
    private const string NativePythonSha = "4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3";
    private static readonly HashSet<string> AllowedP02 = new(StringComparer.Ordinal) {
        "helion.chat","core.chat","persona.chat","chat.model","chat.history",
        "chat.rag","chat.voice","chat.stop","calls.history"
    };
    private Process? _nativeP02Process;
    private NativePythonPipe? _nativeP02Pipe;
    private OneHostP02WebView2Bridge? _nativeP02Bridge;

    private bool NativeP02Acl(string sid, string route)
    {
        try {
            return AllowedP02.Contains(route) && _nativeP02Process is { HasExited: false } &&
                string.Equals(WindowsIdentity.GetCurrent().User?.Value, sid, StringComparison.Ordinal);
        } catch { return false; }
    }
    private Task<bool> ConfirmP02NativeAsync(string route, CancellationToken cancel)
    {
        if (cancel.IsCancellationRequested) return Task.FromResult(false);
        if (route == "chat.stop" || route == "chat.model") return Task.FromResult(true);
        // Existing WPF native window, never browser-supplied consent.
        var answer=MessageBox.Show(this, "Разрешить локальный маршрут NOX: "+route+"?",
            "NOX HELION · Native consent",MessageBoxButton.YesNo,
            MessageBoxImage.Question,MessageBoxResult.No);
        return Task.FromResult(!cancel.IsCancellationRequested && answer==MessageBoxResult.Yes);
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
    private async Task InitializeNativeP02Async(CoreWebView2 core)
    {
        if (_nativeP02Process is not null || _nativeP02Pipe is not null) return;
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
            child=Process.Start(args)??throw new IOException("P02_ORIGINAL_PROCESS_HOLD");
            _nativeP02Process=child;
            transport=new NativePythonPipe(child.StandardOutput.BaseStream,
                child.StandardInput.BaseStream,runId);
            var handshake=await transport.RequestAsync("chat.model",new {},
                TimeSpan.FromSeconds(6));
            if(!handshake.Accepted)throw new IOException("P02_REAL_NATIVE_INGRESS_NOT_READY");
            _nativeP02Bridge=new OneHostP02WebView2Bridge(core,
                new Uri("https://nox.local/"),transport,sid,
                NativeP02Acl,ConfirmP02NativeAsync);
            _nativeP02Pipe=transport;
            WriteLog("P02_ORIGINAL_NATIVE_PIPE_HANDSHAKE_OK");
        } catch(Exception exception) {
            WriteLog("P02_ORIGINAL_NATIVE_HOLD "+exception.GetType().Name);
            _nativeP02Bridge?.Dispose();_nativeP02Bridge=null;
            if(transport is not null)await transport.DisposeAsync();
            if(child is not null) {
                try {if(!child.HasExited)child.Kill(entireProcessTree:true);}catch{}
                child.Dispose();
            }
            _nativeP02Process=null;_nativeP02Pipe=null;
            // No synthetic ready state; existing original UI/chat remain unchanged.
        }
    }
    private void ShutdownNativeP02()
    {
        _nativeP02Bridge?.Dispose();_nativeP02Bridge=null;
        var child=_nativeP02Process;_nativeP02Process=null;
        try {if(child is not null && !child.HasExited)child.Kill(entireProcessTree:true);}catch{}
        child?.Dispose();
        if(_nativeP02Pipe is not null)_=_nativeP02Pipe.DisposeAsync();
        _nativeP02Pipe=null;
    }
}

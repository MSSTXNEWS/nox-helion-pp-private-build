using System.Diagnostics;
using Nox.P02;

string runId="NOX-C11-NATIVE-WINDOWS-SMOKE";
string python = Environment.GetEnvironmentVariable("PYTHON") ?? "python";
string fixture = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,"..","..","..","..","pipe-smoke","fixture_existing_owner.py"));
if (!File.Exists(fixture)) fixture=Path.GetFullPath("Packages/P02/worker-chat/pipe-smoke/fixture_existing_owner.py");
if (!File.Exists(fixture)) throw new FileNotFoundException("P02 owner's original protocol fixture absent",fixture);
var start = new ProcessStartInfo(python) { UseShellExecute=false, CreateNoWindow=true, RedirectStandardInput=true, RedirectStandardOutput=true, RedirectStandardError=true };
start.ArgumentList.Add("-u"); start.ArgumentList.Add(fixture); start.ArgumentList.Add(runId);
start.Environment["PYTHONPATH"]=Path.GetFullPath("Packages/P02/worker-python");
using var child = Process.Start(start) ?? throw new Exception("Windows process not launched");
try {
    await using (var transport=new NativePythonPipe(child.StandardOutput.BaseStream,child.StandardInput.BaseStream,runId)) {
        var model = await transport.RequestAsync("chat.model",new { },TimeSpan.FromSeconds(8));
        if (!model.Accepted || model.Result is null || model.Result.Value.GetProperty("route").GetString()!="chat.model") throw new Exception("Existing model route not crossed");
        bool denied=false;
        try { await transport.RequestAsync("chat.model",new { admin=true }); } catch(NativePipeHold e) when(e.Code=="PAGE_AUTHORITY_CLAIM_DENIED") { denied=true; }
        if (!denied) throw new Exception("Page privilege spoof was not denied");
        // The Python owner's chat worker intentionally waits for STOP.  WPF STOP must overtake it.
        var chat = transport.RequestAsync("helion.chat",new { text="Привет" },TimeSpan.FromSeconds(8));
        await Task.Delay(200);
        var stop = await transport.RequestAsync("chat.stop",new {},TimeSpan.FromSeconds(8));
        var complete = await chat;
        if (!stop.Accepted || !complete.Accepted || stop.RequestId==complete.RequestId)
            throw new Exception("Asynchronous framed STOP/request correlation failed");
        Console.WriteLine("P02_NATIVE_DOTNET_TO_ORIGINAL_PYTHON_PIPE=PASS");
        Console.WriteLine("P02_RUN_ID_NONCE_STOP_IDENTITY=PASS");
    }
    child.StandardInput.Close();
    if(!child.WaitForExit(5000)||child.ExitCode!=0)throw new Exception("Python owner transport failed");
    Console.WriteLine("P02_SINGLE_HOST_TRANSPORT_COMPONENT=PASS_NOT_EXE");
} finally {if(!child.HasExited)child.Kill(entireProcessTree:true);}

using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using Nox.Pack01;
using NoxP04.Rag;
using NoxP04.GpuGuardian;

internal static class Program
{
    private static void Require(bool ok,string msg)
    { if(!ok)throw new InvalidOperationException("P04_PACK_TEST_"+msg); }

    private static async Task Serve(HttpListener listener,CancellationToken ct)
    {
        while(!ct.IsCancellationRequested)
        {
            HttpListenerContext ctx;
            try {ctx=await listener.GetContextAsync().WaitAsync(ct);}
            catch(OperationCanceledException){break;}
            catch(HttpListenerException)when(ct.IsCancellationRequested){break;}
            try
            {
                if(ctx.Request.Url?.AbsolutePath!="/api/embed" || ctx.Request.HttpMethod!="POST")
                {ctx.Response.StatusCode=404;}
                else
                {
                    using var reader=new StreamReader(ctx.Request.InputStream,Encoding.UTF8);
                    var raw=await reader.ReadToEndAsync(ct);
                    using var request=JsonDocument.Parse(raw);
                    var vectors=request.RootElement.GetProperty("input").EnumerateArray()
                        .Select(x=>x.GetString()?.Contains("alpha",StringComparison.OrdinalIgnoreCase)==true
                            ? new float[]{1,0,0}:new float[]{0,1,0}).ToArray();
                    var payload=JsonSerializer.SerializeToUtf8Bytes(new{embeddings=vectors});
                    ctx.Response.StatusCode=200;ctx.Response.ContentType="application/json";
                    ctx.Response.ContentLength64=payload.Length;
                    await ctx.Response.OutputStream.WriteAsync(payload,ct);
                }
            }
            catch{ctx.Response.StatusCode=500;}
            finally{ctx.Response.Close();}
        }
    }

    static async Task<int> Main()
    {
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(45));
        var probe=new TcpListener(IPAddress.Loopback,0);
        probe.Start();int port=((IPEndPoint)probe.LocalEndpoint).Port;probe.Stop();
        using var listener=new HttpListener();
        listener.Prefixes.Add("http://127.0.0.1:"+port+"/");listener.Start();
        var server=Serve(listener,timeout.Token);
        var root=Path.Combine(Path.GetTempPath(),"NOX_PACK_P04_"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            using var rag=new RagService(new Uri("http://127.0.0.1:"+port+"/"),
                "no-model-local-test",Path.Combine(root,"index.json"));
            var ingest=new RagIngestionService(rag);
            var nativeApproved=false;
            var pack=new P04OwnerPack(ingest,new GpuGuardian(),
                _=>nativeApproved);
            Require(P04OwnerPack.Supported.Count==6,"EXACT_SIX");
            bool denied=false;
            try {await pack.ExecuteAsync("rag.import","S-1-5-21-1111","room-1",
                input:"alpha one",sourceId:"src-one",fileName:"source.md",cancel:timeout.Token);}
            catch(UnauthorizedAccessException){denied=true;}
            Require(denied,"NATIVE_IMPORT_DENY");
            nativeApproved=true;
            var receipt=(RagIngestionReceipt)await pack.ExecuteAsync("rag.import",
                "S-1-5-21-1111","room-1",input:"alpha one",sourceId:"src-one",
                fileName:"source.md",cancel:timeout.Token);
            Require(receipt.IndexedChunks>0&&receipt.SourceIdentitySha256.Length==64,"TRUE_IMPORT");
            nativeApproved=false;
            var context=(RagContextResult)await pack.ExecuteAsync("rag.search",
                "S-1-5-21-1111","room-1",input:"alpha",cancel:timeout.Token);
            Require(context.Sources.Count>0 && context.ContextText.Contains("SHA256:"),"TRUE_SEARCH");
            var chatRag=new P02RagChatOwnerPort(new RagChatContextProvider(ingest),
                identity=>identity.WindowsSid=="S-1-5-21-1111"&&
                          identity.ConversationId=="room-1"&&
                          identity.SessionId=="real-native-host-session");
            var linked=await chatRag.RetrieveAsync(new NativeP02ChatScope(
                "S-1-5-21-1111","room-1","real-native-host-session"),"alpha",cancel:timeout.Token);
            Require(linked.Sources.Count>0&&linked.ContextText.Contains("SHA256:"),"P02_CHAT_RAG_REAL_CITATIONS");
            denied=false;
            try {
                await chatRag.RetrieveAsync(new NativeP02ChatScope(
                    "S-1-5-21-2222","room-1","page-supplied-session"),"alpha",cancel:timeout.Token);
            }catch(UnauthorizedAccessException){denied=true;}
            Require(denied,"P02_CHAT_RAG_NATIVE_SESSION_DENY");
            var outsider=(RagContextResult)await pack.ExecuteAsync("rag.search",
                "S-1-5-21-2222","room-1",input:"alpha",cancel:timeout.Token);
            Require(outsider.Sources.Count==0,"ACL");
            denied=false;
            try {await pack.ExecuteAsync("memory.manage","S-1-5-21-1111","room-1",
                sourceId:"src-one",cancel:timeout.Token);}
            catch(UnauthorizedAccessException){denied=true;}
            Require(denied,"NATIVE_DELETE_DENY");
            nativeApproved=true;
            var deleted=(bool)await pack.ExecuteAsync("memory.manage","S-1-5-21-1111",
                "room-1",sourceId:"src-one",cancel:timeout.Token);
            Require(deleted,"DELETE_ACK");
            var after=(RagContextResult)await pack.ExecuteAsync("rag.search",
                "S-1-5-21-1111","room-1",input:"alpha",cancel:timeout.Token);
            Require(after.Sources.Count==0,"DELETE_VERIFIED");
            var gpu=(IReadOnlyList<GpuTelemetrySample>)await pack.ExecuteAsync("gpu.preflight",
                "S-1-5-21-1111","room-1",cancel:timeout.Token);
            Require(gpu.Count>=1&&gpu.All(x=>x.State!="READY"||x.TemperatureC is >=0 and <=150),"TRUTHFUL_GPU");
            denied=false;
            try {await pack.ExecuteAsync("training.pause","S-1-5-21-1111","room-1",cancel:timeout.Token);}
            catch(InvalidOperationException){denied=true;}
            Require(denied,"UNBOUND_WORKER_HOLD");
            Console.WriteLine("NOX_P04_PACK_PASS: six P04 methods plus P02.chat.rag, source citations, native ACL and GPU truth");
            return 0;
        }
        finally
        {
            timeout.Cancel();listener.Stop();
            try{await server.WaitAsync(TimeSpan.FromSeconds(2));}catch(OperationCanceledException){}
            try{Directory.Delete(root,true);}catch{}
        }
    }
}
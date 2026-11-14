// P02 offline deterministic contract smoke (not executed in this conversation).
// dotnet run --project Packages/P02/smoke/P02.Smoke.csproj
using System;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.P02;

var root=Path.Combine(Path.GetTempPath(),"nox-p02-smoke-"+Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
try
{
    var store=new ChatSqliteStore(Path.Combine(root,"state","chat.db"));
    await store.InitializeAsync();
    await store.CreateChatAsync("t1","alice","chat1");
    await store.AddMessageAsync("t1","alice","chat1","user","Hi");
    var entries=await store.ListMessagesAsync("t1","alice","chat1");
    Check(entries.Count==1 && entries[0].Content=="Hi","Chat history round-trip");

    var denied=false;
    try { _=await store.ListMessagesAsync("t1","mallory","chat1"); }
    catch(UnauthorizedAccessException) { denied=true; }
    Check(denied,"Cross-principal chat access denied");

    var pipeline=new AttachmentPipeline(store,Path.Combine(root,"attachments"));
    await using (var input=new MemoryStream(Encoding.ASCII.GetBytes("%PDF-1.7\n%fixture")))
    {
        var ack=await pipeline.StoreAsync("t1","alice","chat1",input,"application/pdf");
        Check(ack.StoredId.Length==32 && ack.Sha256.Length==64,"Receipt ID and SHA");
        await using(var checkedContent=await pipeline.OpenAuthorizedAsync("t1","alice","chat1",ack.StoredId))
        {
            Check(checkedContent.Length==ack.Bytes,"Attachment authorized read");
        }
        denied=false;
        try { _=await pipeline.OpenAuthorizedAsync("t1","mallory","chat1",ack.StoredId); }
        catch(UnauthorizedAccessException) { denied=true; }
        Check(denied,"Cross-principal attachment read denied");

        var storageId=await store.DeleteAttachmentAsync("t1","alice","chat1",ack.StoredId);
        pipeline.PurgeDeletedChatFiles(new ChatDeleteReceipt("chat1",new[]{storageId}));
        denied=false;
        try { _=await store.GetAttachmentAsync("t1","alice","chat1",ack.StoredId); }
        catch(UnauthorizedAccessException) { denied=true; }
        Check(denied,"Selective attachment removal");
    }

    var rejected=false;
    try
    {
        await using var fake=new MemoryStream(new byte[]{0x4D,0x5A,0x90});
        await pipeline.StoreAsync("t1","alice","chat1",fake,"application/pdf");
    }
    catch(InvalidDataException) { rejected=true; }
    Check(rejected,"MIME signature mismatch denied");

    Check(SpaceBrowserBoundary.Classify(new Uri("https://example.com"))==
        SpaceOriginClass.ExternalWeb,"External origin classified as unprivileged");
    Check(!SpaceBrowserBoundary.MayInvokeNative("history.delete",new Uri("https://example.com"),
        isMainFrame:true,hostHasVerifiedUserConsent:true),"External page cannot invoke host");
    Check(!SpaceBrowserBoundary.MayExposeHostObjects(new Uri("https://nox.invalid")),
        "Host objects remain disabled");

    using(var http=new HttpClient(new FakeOllamaHandler()))
    using(var ollama=new OllamaChatClient(new Uri("http://127.0.0.1:11434/"),http))
    {
        var models=await ollama.GetModelsAsync(CancellationToken.None);
        Check(models.Count==1 && models[0].Name=="tiny:latest","Model list parse");
        var fragments="";
        var completed=false;
        await foreach(var chunk in ollama.StreamChatAsync("tiny:latest",
            new[]{new OllamaMessage("user","Hi")},CancellationToken.None))
        {
            fragments+=chunk.Text;
            if(chunk.Done) completed=true;
        }
        Check(fragments=="Hello" && completed,"Streaming NDJSON and done marker");
        using var stop=new CancellationTokenSource();
        stop.Cancel();
        var stopped=false;
        try
        {
            await foreach(var _ in ollama.StreamChatAsync("tiny:latest",
                new[]{new OllamaMessage("user","Hi")},stop.Token)) { }
        }
        catch(OperationCanceledException) { stopped=true; }
        Check(stopped,"Pre-cancelled STOP propagated");
    }

    var removed=await store.PruneMessagesAsync("t1","alice","chat1",
        DateTimeOffset.UtcNow.AddMinutes(1));
    Check(removed==1,"Retention pruning");
    var deletion=await store.DeleteChatAsync("t1","alice","chat1");
    pipeline.PurgeDeletedChatFiles(deletion);
    Check(deletion.ChatId=="chat1","Chat deletion receipt");
    Console.WriteLine("P02 smoke PASS (offline fixtures, not Windows E07 acceptance)");
}
finally
{
    try { Directory.Delete(root,recursive:true); }
    catch(IOException) { /* pooled SQLite handles may outlive process: temp cleanup deferred */ }
    catch(UnauthorizedAccessException) { /* cleanup reported by host, not silent success */ }
}

static void Check(bool condition,string message)
{
    if(!condition) throw new Exception("P02 smoke FAILED: "+message);
    Console.WriteLine("PASS "+message);
}

sealed class FakeOllamaHandler : HttpMessageHandler
{
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct)
    {
        string json=request.RequestUri!.AbsolutePath switch
        {
            "/api/tags" => "{\"models\":[{\"name\":\"tiny:latest\",\"size\":16}]}",
            "/api/chat" => "{\"message\":{\"role\":\"assistant\",\"content\":\"Hello\"},\"done\":false}\n"+
                           "{\"message\":{\"role\":\"assistant\",\"content\":\"\"},\"done\":true,\"done_reason\":\"stop\"}\n",
            _ => throw new InvalidOperationException("Unexpected Ollama endpoint")
        };
        var response=new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content=new StringContent(json,Encoding.UTF8,
                request.RequestUri.AbsolutePath=="/api/chat"?"application/x-ndjson":"application/json")
        };
        return Task.FromResult(response);
    }
}

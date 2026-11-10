// Synthetic source regression only: real queue/adapter/receipts, simulated Ollama.
// No GPU training, installed model, Windows acceptance or license claim.
using System.Buffers.Binary;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Nox.P03;

var cases=new (string,Func<Task>)[] {
    ("merge-import-receipt",Success), ("mutated-payload-denied",Mutation),
    ("native-rights-denied",Rights), ("native-consent-denied",Consent),
    ("unsupported-architecture-hold",Unsupported), ("existing-tag-not-overwritten",Collision),
    ("stop-during-upload",Stop), ("null-gguf-sha-denied",NullGgufSha)
};
foreach(var (name,run) in cases){await run();Console.WriteLine("PASS "+name);}
Console.WriteLine($"SOURCE_FIXTURE_PASS {cases.Length}/{cases.Length}");

static void Check(bool value,string message){if(!value)throw new Exception(message);}
static async Task Denied(Func<Task> action){try{await action();}catch(InvalidDataException){return;}catch(UnauthorizedAccessException){return;}throw new Exception("Expected denial");}
static async Task Success(){using var f=new Fixture();var job=await f.Queue.EnqueueVerifiedMergedAsync(f.Approval,true);await f.Worker.RunNextAsync(default,job.Id);var result=(await f.Queue.ReadAsync()).Single();Check(result.State==ModelJobState.Completed,"not complete");var receipt=JsonSerializer.Deserialize<ModelInstallReceipt>(await File.ReadAllTextAsync(result.ReceiptPath!),new JsonSerializerOptions(JsonSerializerDefaults.Web))!;Check(receipt.Operation=="safetensors-import"&&receipt.MergedPayloadSha256==f.Approval.MergedPayloadSha256,"bad receipt binding");Check(receipt.ImportedFiles?.Count==3&&receipt.OllamaDigest=="sha256:"+new string('a',64),"bad actual digest/files");Check(f.Handler.Creates==1&&f.Handler.Blobs.Count==3,"missing actual blob protocol");await ModelLocalAttestation.VerifyReceiptAsync(result.ReceiptPath!,receipt,default);}
static async Task Mutation(){using var f=new Fixture();var job=await f.Queue.EnqueueVerifiedMergedAsync(f.Approval,true);await File.AppendAllTextAsync(Path.Combine(f.Merged,"config.json")," ");await f.Worker.RunNextAsync(default,job.Id);Check((await f.Queue.ReadAsync()).Single().State==ModelJobState.Failed,"mutated source accepted");Check(f.Handler.Calls==0,"network before source rejection");}
static async Task Rights(){using var f=new Fixture();await Denied(()=>f.Queue.EnqueueVerifiedMergedAsync(f.Approval with{NativeRightsVerified=false},true));Check((await f.Queue.ReadAsync()).Count==0,"denied job persisted");}
static async Task Consent(){using var f=new Fixture();await Denied(()=>f.Queue.EnqueueVerifiedMergedAsync(f.Approval,false));Check((await f.Queue.ReadAsync()).Count==0,"unconsented job persisted");}
static async Task Unsupported(){using var f=new Fixture();f.Handler.Unsupported=true;var job=await f.Queue.EnqueueVerifiedMergedAsync(f.Approval,true);await f.Worker.RunNextAsync(default,job.Id);var result=(await f.Queue.ReadAsync()).Single();Check(result.State==ModelJobState.Failed&&result.Error=="P03_SAFETENSORS_ARCHITECTURE_UNSUPPORTED","unsupported architecture not HOLD");Check(result.ReceiptPath is null,"false import receipt");}
static async Task Collision(){using var f=new Fixture();var job=await f.Queue.EnqueueVerifiedMergedAsync(f.Approval,true);f.Handler.CollisionTag=job.ModelTag;await f.Worker.RunNextAsync(default,job.Id);var result=(await f.Queue.ReadAsync()).Single();Check(result.Error=="P03_CANDIDATE_TAG_ALREADY_EXISTS"&&f.Handler.Creates==0,"prior tag overwritten");}
static async Task Stop(){using var f=new Fixture();f.Handler.BlockUploads=true;var job=await f.Queue.EnqueueVerifiedMergedAsync(f.Approval,true);var work=f.Worker.RunNextAsync(default,job.Id);await f.Handler.UploadStarted.Task.WaitAsync(TimeSpan.FromSeconds(5));Check(await f.Worker.CancelAsync(job.Id),"cancel failed");await work.WaitAsync(TimeSpan.FromSeconds(5));var result=(await f.Queue.ReadAsync()).Single();Check(result.State==ModelJobState.Cancelled&&result.ReceiptPath is null,"STOP became success");}
static async Task NullGgufSha(){using var f=new Fixture();await Denied(()=>f.Queue.EnqueueVerifiedGgufAsync("local:1","not-used.gguf",5,null!,"rights","https://example.test/license"));}

sealed class Fixture:IDisposable
{
    public string Root{get;}=Path.Combine(Path.GetTempPath(),"nox-k03-"+Guid.NewGuid().ToString("N"));
    public string Merged{get;}
    public P04MergedImportApproval Approval{get;}
    public ModelDownloadQueueStore Queue{get;}
    public FakeOllama Handler{get;}=new();
    public ModelDownloadQueueWorker Worker{get;}
    private readonly HttpClient _http;
    public Fixture(){Directory.CreateDirectory(Root);Merged=Path.Combine(Root,"merged");Directory.CreateDirectory(Merged);
        File.WriteAllText(Path.Combine(Merged,"config.json"),"{\"model_type\":\"llama\"}");
        File.WriteAllText(Path.Combine(Merged,"tokenizer.json"),"{\"fixture\":true}");
        var header=Encoding.UTF8.GetBytes("{\"w\":{\"dtype\":\"U8\",\"shape\":[4],\"data_offsets\":[0,4]}}");
        using(var weights=File.Create(Path.Combine(Merged,"model.safetensors"))){var len=new byte[8];BinaryPrimitives.WriteUInt64LittleEndian(len,(ulong)header.Length);weights.Write(len);weights.Write(header);weights.Write(new byte[]{1,2,3,4});}
        string A=new('a',64),B=new('b',64),C=new('c',64),D=new('d',64);
        var training=new {schema="NOX-QLORA-TRAINING-RECEIPT-v2",status="COMPLETED",model=new{id="fixture",revision="rev",snapshot_sha256=A},adapter_sha256=B,
            dataset=new{rights_attestation_id="fixture-rights",rights_attestation_sha256=C,owner_approval_id="fixture-owner",license_id="fixture-license",train_sha256=A,holdout_sha256=D},
            training=new{evaluation_status="VALID",baseline_eval_loss=2.0,adapter_eval_loss=1.0}};
        var trainingPath=Path.Combine(Root,"training-receipt.json");File.WriteAllText(trainingPath,JsonSerializer.Serialize(training));
        var trainingSha=Hash(trainingPath);var tree=Tree(Merged);
        var merge=new {schema="NOX-QLORA-MERGE-RECEIPT-v1",status="CREATED",model_id="fixture",model_revision="rev",model_snapshot_sha256=A,training_receipt_sha256=trainingSha,adapter_sha256=B,adapter_eval_loss=1.0,baseline_eval_loss=2.0,merged_payload_sha256=tree,evidence_verified=false};
        var mergePath=Path.Combine(Merged,"merge-receipt.json");File.WriteAllText(mergePath,JsonSerializer.Serialize(merge));
        Approval=new(Merged,tree,Hash(mergePath),trainingPath,trainingSha,"fixture-rights",C,"https://example.test/license","fixture-native-approval",true);
        Queue=new ModelDownloadQueueStore(Path.Combine(Root,"queue"));_http=new HttpClient(Handler){BaseAddress=new Uri("http://127.0.0.1:11434/")};
        Worker=new(Queue,new OllamaModelAdapter(_http,Path.Combine(Root,"receipts")),new ModelLifecyclePublisher(new Sink()));
    }
    private static string Hash(string path)=>Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
    private static string Tree(string path){using var hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);foreach(var file in Directory.GetFiles(path).OrderBy(Path.GetFileName,StringComparer.Ordinal)){var name=Encoding.UTF8.GetBytes(Path.GetFileName(file));var size=new byte[4];BinaryPrimitives.WriteUInt32BigEndian(size,(uint)name.Length);hash.AppendData(size);hash.AppendData(name);hash.AppendData(Convert.FromHexString(Hash(file)));}return Convert.ToHexString(hash.GetHashAndReset()).ToLowerInvariant();}
    public void Dispose(){_http.Dispose();Directory.Delete(Root,true);}
}
sealed class Sink:IModelLifecycleEventSink{public ValueTask PublishToP01Async(ModelLifecycleEvent e,CancellationToken ct)=>ValueTask.CompletedTask;public ValueTask PublishToP05Async(ModelLifecycleEvent e,CancellationToken ct)=>ValueTask.CompletedTask;}
sealed class FakeOllama:HttpMessageHandler
{
    public int Calls,Creates;public bool Unsupported,BlockUploads;public string? CollisionTag,CreatedTag;
    public HashSet<string> Blobs{get;}=[];public TaskCompletionSource UploadStarted{get;}=new(TaskCreationOptions.RunContinuationsAsynchronously);
    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken ct){Calls++;var path=request.RequestUri!.AbsolutePath;string body="";var status=HttpStatusCode.OK;
        if(path=="/api/tags"){var tag=CollisionTag??CreatedTag;body=JsonSerializer.Serialize(new{models=tag is null?Array.Empty<object>():new object[]{new{name=tag,digest="sha256:"+new string('a',64)}}});}
        else if(path.StartsWith("/api/blobs/",StringComparison.Ordinal)){var digest=path[11..];if(request.Method==HttpMethod.Head){if(!Blobs.Contains(digest))status=HttpStatusCode.NotFound;}else {UploadStarted.TrySetResult();if(BlockUploads)await Task.Delay(Timeout.Infinite,ct);var bytes=await request.Content!.ReadAsByteArrayAsync(ct);if(digest!="sha256:"+Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant())throw new Exception("uploaded bytes do not match digest");Blobs.Add(digest);}}
        else if(path=="/api/create"){Creates++;using var doc=JsonDocument.Parse(await request.Content!.ReadAsStringAsync(ct));var files=doc.RootElement.GetProperty("files");if(files.EnumerateObject().Any(x=>!Blobs.Contains(x.Value.GetString()!)))throw new Exception("create references missing blob");if(Unsupported)body="{\"error\":\"unsupported architecture fixture\"}\n";else{CreatedTag=doc.RootElement.GetProperty("model").GetString();body="{\"status\":\"success\"}\n";}}
        else throw new Exception("unexpected endpoint "+path);
        return new HttpResponseMessage(status){Content=new StringContent(body),RequestMessage=request};
    }
}

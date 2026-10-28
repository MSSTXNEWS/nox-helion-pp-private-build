using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Nox.P03;

static void Check(bool ok, string name) {
    if (!ok) throw new Exception("FAILED: "+name);
    Console.WriteLine("PASS "+name);
}
var rev = new string('a', 40);
var data = Encoding.UTF8.GetBytes("NOX-TEST-WEIGHT-BYTES");
var digest = Convert.ToHexString(SHA256.HashData(data));
var model = new MediaWeightPackage("wan22","wan22-ti2v-5b",
    "Wan-AI/Wan2.2-TI2V-5B",rev,"https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B",
    [new MediaWeightFile("weights/model.safetensors",data.Length,digest)],true);
var modelB = model with { ModelId="flux2", VariantId="flux2-klein4b-fp8",
    HuggingFaceRepo="black-forest-labs/FLUX.2-klein-4b-fp8" };
Check(model.IsApproved(),"exact model manifest approved");
Check(modelB.IsApproved(),"second variant approved");
Check(!(model with { ImmutableRevision="main" }).IsApproved(),"unpinned revision refused");
Check(!(model with { Files=[new("../escape",data.Length,digest)] }).IsApproved(),"path traversal refused");
Check(!(model with { Files=[new("weights/model.safetensors",data.Length,"nope")] }).IsApproved(),"unverified digest refused");
Check(!MediaWeightPackage.SafeRelativePath("C:\\temp\\weight"),"Windows path refused");
Check(!MediaWeightPackage.SafeRelativePath("x/../other"),"parent traversal refused");
Check(!MediaWeightPackage.SafeRelativePath("https://example.com/weight"),"URL-as-file refused");
var approved = new Dictionary<string,MediaWeightPackage>(StringComparer.Ordinal)
    { [model.VariantId]=model,[modelB.VariantId]=modelB };
static string Command(string action, string model, string variant, bool ack=true, string? job=null) =>
    JsonSerializer.Serialize(new {
        type="p03.media.command.v1",
        commandId="cmd-001",action,modelId=model,variantId=variant,
        licenseAcknowledged=ack,jobId=job
    });
Check(MediaWeightCommandContract.TryParse(
    Command("download",model.ModelId,model.VariantId),approved,true,false,out var command)
    && command?.VariantId==model.VariantId,"first variant independent download");
Check(MediaWeightCommandContract.TryParse(
    Command("download",modelB.ModelId,modelB.VariantId),approved,true,false,out var commandB)
    && commandB?.VariantId==modelB.VariantId,"second variant independent download");
Check(!MediaWeightCommandContract.TryParse(
    Command("download","wan22",modelB.VariantId),approved,true,false,out _),"cross-family variant rejected");
Check(!MediaWeightCommandContract.TryParse(
    Command("download",model.ModelId,model.VariantId,false),approved,true,false,out _),"rights unconfirmed blocked");
Check(!MediaWeightCommandContract.TryParse(
    Command("download",model.ModelId,model.VariantId),approved,false,false,out _),"host capability disabled");
var job=Guid.NewGuid();
Check(MediaWeightCommandContract.TryParse(
    Command("cancel",model.ModelId,model.VariantId,false,job.ToString()),approved,false,true,out var cancel)
    && cancel?.JobId==job,"variant-specific cancellation parsed");
var uri=new Uri("https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B/resolve/"+rev+"/weights/model.safetensors");
Check(MediaWeightTransfer.IsApprovedSource(uri),"official pinned HTTPS accepted");
Check(!MediaWeightTransfer.IsApprovedSource(new Uri("https://huggingface.co.evil.example/x")),"lookalike domain refused");
Check(!MediaWeightTransfer.IsApprovedSource(new Uri("http://huggingface.co/x")),"plaintext refused");
var fake=new ByteHandler(data);
using var client=new HttpClient(fake);
var worker=new MediaWeightTransfer(client);
string root=Path.Combine(Path.GetTempPath(),"nox-p03-media-test-"+Guid.NewGuid().ToString("N"));
try {
    var progress=new List<MediaWeightProgress>();
    var receipt=await worker.DownloadAsync(model,root,new Progress<MediaWeightProgress>(p=>{}),CancellationToken.None);
    Check(receipt.Status=="INSTALLED_VERIFIED"&&receipt.TotalBytes==data.Length,"real local byte transfer, SHA attested");
    var installed=Path.Combine(root,"wan22","wan22-ti2v-5b","weights","model.safetensors");
    Check(File.Exists(installed),"pin stored at exact variant directory");
    Check(Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(installed)))==digest,"installed bytes match pinned SHA");
    Check(fake.Calls==1,"one HTTP request via host supplied client");
    var repeat=await worker.DownloadAsync(model,root,null,CancellationToken.None);
    Check(fake.Calls==1&&repeat.Status=="INSTALLED_VERIFIED","re-verified existing file, no extra download");
    await File.WriteAllTextAsync(installed,"CORRUPTED");
    try { await worker.DownloadAsync(model,root,null,CancellationToken.None);
        throw new Exception("Corrupt weights wrongly accepted"); }
    catch(InvalidDataException){Check(true,"corrupt existing weights fail closed");}
} finally {try{Directory.Delete(root,true);}catch{}}
Console.WriteLine("P03_MEDIA_WEIGHT_CHECKS_PASS");

sealed class ByteHandler(byte[] content):HttpMessageHandler {
 public int Calls;
 protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage req,CancellationToken ct){
    Calls++;
    if(req.RequestUri is null || !MediaWeightTransfer.IsApprovedSource(req.RequestUri))
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.Forbidden));
    return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) {
        Content=new ByteArrayContent(content)
    });
 }
}

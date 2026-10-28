using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Nox.P01.AutoUpdate;

static void Ensure(bool ok,string label) {
    if(!ok)throw new Exception("FAIL "+label);
    Console.WriteLine("PASS "+label);
}
using var key=ECDsa.Create(ECCurve.NamedCurves.nistP256);
var pem=key.ExportSubjectPublicKeyInfoPem();
var feed=new Uri("https://updates.nox.example/releases/stable.json");
var update=new SignedReleaseManifest(
    "NOX_SIGNED_RELEASE_V1","stable","2.1.0","NOX-V16-BUILD-002",
    "https://updates.nox.example/releases/NOX-HELION-2.1.exe",
    new string('a',64),73_000_000,
    DateTimeOffset.UtcNow.AddMinutes(-5).ToString("O"),
    DateTimeOffset.UtcNow.AddDays(2).ToString("O"),"");
var signed=update with {Signature=Convert.ToBase64String(key.SignData(update.SignedBytes,HashAlgorithmName.SHA256))};
var handler=new FakeHandler(signed);
using var http=new HttpClient(handler);
var checker=new NoxUpdateDiscovery(http);
var cfg=new UpdateConfiguration(feed,pem,"2.0.0","stable",TimeSpan.FromHours(6));
var result=await checker.CheckAsync(cfg);
Ensure(result.Status=="UPDATE_AVAILABLE_VERIFIED"&&result.HasUpdate,"signed newer version accepted");
Ensure(result.InstallerUrl?.Host=="updates.nox.example","installer origin held to manifest origin");
Ensure(handler.Calls==1,"one HTTPS read-only check");
Ensure(!result.HasUpdate || result.Bytes == 73_000_000,"byte size verified from signed data");
result=await checker.CheckAsync(cfg with {CurrentVersion="2.1.0"});
Ensure(result.Status=="UP_TO_DATE","same version not advertised");
handler.Value=signed with {Version="4.0.0"};
result=await checker.CheckAsync(cfg);
Ensure(result.Reason=="INVALID_SIGNATURE","tampered version rejected");
handler.Value=signed with {InstallerUrl="https://evil.example/payload.exe"};
result=await checker.CheckAsync(cfg);
Ensure(result.Reason=="UNSAFE_INSTALLER_URL","redirected third-party release host forbidden");
handler.Value=signed;
result=await checker.CheckAsync(cfg with {FeedUri=null});
Ensure(result.Reason=="NO_SIGNED_FEED_CONFIGURED","no configured feed is HOLD not fictional update");
result=await checker.CheckAsync(cfg with {PinnedP256PublicKeyPem=null});
Ensure(result.Reason=="NO_SIGNED_FEED_CONFIGURED","unsigned release never offered");
result=await checker.CheckAsync(cfg with {FeedUri=new Uri("http://updates.nox.example/stable")});
Ensure(result.Reason=="UNSAFE_FEED_URL","plaintext update denied");
handler.Value=signed with {ExpiresUtc=DateTimeOffset.UtcNow.AddMinutes(-1).ToString("O")};
result=await checker.CheckAsync(cfg);
Ensure(result.Reason=="INVALID_MANIFEST_FIELDS","expired feed refused");
handler.Value=signed;
using var cancelled=new CancellationTokenSource();
var results=new List<VerifiedUpdate>();
await checker.RunSearchLoopAsync(cfg, item=> {
    results.Add(item);cancelled.Cancel();return Task.CompletedTask;
},cancelled.Token).ContinueWith(t=> {
    if(t.IsFaulted && t.Exception!.InnerException is not OperationCanceledException)throw t.Exception;
});
Ensure(results.Count==1&&results[0].HasUpdate,"startup must check immediately, never auto-download");
Ensure(cfg.SafeInterval==TimeSpan.FromHours(6),"default periodic cadence");
Ensure((cfg with {Interval=TimeSpan.FromSeconds(1)}).SafeInterval==TimeSpan.FromHours(6),"reject tight update polling");
Console.WriteLine("P01_AUTO_UPDATE_CHECKS_PASS");

sealed class FakeHandler(SignedReleaseManifest value):HttpMessageHandler {
    public SignedReleaseManifest Value=value;
    public int Calls;
    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage req,CancellationToken ct){
        Calls++;
        if(req.Method!=HttpMethod.Get||req.RequestUri is null ||
           req.RequestUri.Host!="updates.nox.example")
            throw new Exception("UNSAFE_TEST_REQUEST");
        var raw=JsonSerializer.Serialize(Value);
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK){
            RequestMessage=req,Content=new StringContent(raw,Encoding.UTF8,"application/json")
        });
    }
}

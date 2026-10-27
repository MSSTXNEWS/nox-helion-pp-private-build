using Nox.P03;
using Nox.Pack01;

sealed class SilentSink : IModelLifecycleEventSink
{
    public ValueTask PublishToP01Async(ModelLifecycleEvent e, CancellationToken ct) => ValueTask.CompletedTask;
    public ValueTask PublishToP05Async(ModelLifecycleEvent e, CancellationToken ct) => ValueTask.CompletedTask;
}

static class Program
{
    static async Task Main()
    {
        var directory=Path.Combine(Path.GetTempPath(),"nox-pack01-p03-"+Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            using var http=new HttpClient(new HttpClientHandler {UseProxy=false,AllowAutoRedirect=false})
                {BaseAddress=new Uri("http://127.0.0.1:11434/"),Timeout=TimeSpan.FromSeconds(2)};
            var queue=new ModelDownloadQueueStore(directory);
            var ollama=new OllamaModelAdapter(http,directory);
            var worker=new ModelDownloadQueueWorker(queue,ollama,new ModelLifecyclePublisher(new SilentSink()));
            var facade=new ModelCenterFacade(queue,worker,http);
            var adapter=new P03OwnerPack(facade,queue,new WindowsComponentAdapter());
            if(P03OwnerPack.Supported.Count!=9)throw new Exception("Nine owner routes required");
            var choices=(IReadOnlyList<QuickModelChoice>)await adapter.ExecuteAsync(new("models.catalog"));
            if(choices.Count!=20)throw new Exception("Expected 20 original quick model choices");
            var q=(IReadOnlyList<ModelJob>)await adapter.ExecuteAsync(new("models.queue"));
            if(q.Count!=0)throw new Exception("Queue must start empty");
            var denied=false;
            try{await adapter.ExecuteAsync(new("models.pull",ChoiceId:"08",
                ReviewedLicenseUrl:"https://example.test/license",NativeLicenseConsent:false));}
            catch(UnauthorizedAccessException){denied=true;}
            if(!denied)throw new Exception("Pull without native consent must be rejected");
            denied=false;
            try{await adapter.ExecuteAsync(new("models.gguf.import",ModelTag:"test",
                SelectedGgufPath:"a.gguf",ReviewedLicenseUrl:"https://example.test/license",
                NativeLicenseConsent:true,NativeFilePickerConfirmed:false));}
            catch(UnauthorizedAccessException){denied=true;}
            if(!denied)throw new Exception("GGUF import without verified picker must be rejected");
            denied=false;
            try{await adapter.ExecuteAsync(new("models.licenses"));}
            catch(NotSupportedException){denied=true;}
            if(!denied)throw new Exception("Unverified model licenses must HOLD");
            var preflight=(IReadOnlyList<ComponentStatus>)await adapter.ExecuteAsync(new("models.preflight"));
            if(preflight.Count!=4)throw new Exception("Expected real OS preflight results");
            Console.WriteLine("NOX_P03_OWNER_PACK_PASS: original 20 tags, queue, 9 bindings, consent/picker/permissions and actual Windows preflight");
        }
        finally { try{Directory.Delete(directory,recursive:true);}catch{} }
    }
}

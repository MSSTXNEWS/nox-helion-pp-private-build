using Nox.Pack01;
using NoxHelion.E05;

static class Program
{
    static async Task Main()
    {
        using var client=E05SafeFeedClient.Production();
        var pack=new E05OwnerPack(client,new Dictionary<string,NativeFeedBinding>(),
            new ISensorProvider[]{new WindowsCpuSensor(),new NvidiaNvmlSensor()});
        if(E05OwnerPack.Supported.Count!=6)throw new Exception("Expected six real E05 ports");
        if(!E05OwnerPack.Supported.Contains("space.weather"))throw new Exception("Weather route missing");
        if(!E05OwnerPack.Supported.Contains("space.news"))throw new Exception("News route missing");
        var actual=(IReadOnlyList<SensorPoint>)await pack.ExecuteAsync("system.telemetry");
        if(actual.Count<4)throw new Exception("Native telemetry response missing");
        if(actual.Any(x=>x.Value is not null && (x.Status!="LIVE" || x.ObservedAtUtc is null)))
            throw new Exception("Sensor values must be grounded in dated native samples");
        bool held=false;
        try{await pack.ExecuteAsync("space.weather");}
        catch(InvalidOperationException){held=true;}
        if(!held)throw new Exception("No approved URL/license cannot claim live weather");
        held=false;
        try{await pack.ExecuteAsync("images.generate");}
        catch(NotSupportedException){held=true;}
        if(!held)throw new Exception("Unknown source owner route must HOLD");
        Console.WriteLine("NOX_E05_OWNER_PACK_PASS: six real source methods, truthful CPU/GPU sensors, no fake weather quote");
    }
}

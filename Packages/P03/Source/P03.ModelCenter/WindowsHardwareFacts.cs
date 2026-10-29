using System.Runtime.InteropServices;
namespace Nox.P03;
public sealed record WindowsHardwareReadiness(long? PhysicalMemoryBytes,long? AvailableMemoryBytes,
    long? SystemDiskFreeBytes,int LogicalCpuCount,string? DiagnosticError);
public static class WindowsHardwareFacts
{
    [StructLayout(LayoutKind.Sequential)]
    private struct MemoryStatusEx
    {
        public uint Length; public uint MemoryLoad;
        public ulong TotalPhysical, AvailablePhysical, TotalPageFile, AvailablePageFile;
        public ulong TotalVirtual, AvailableVirtual, AvailableExtendedVirtual;
    }
    [DllImport("kernel32.dll", EntryPoint="GlobalMemoryStatusEx", SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetMemoryStatus(ref MemoryStatusEx status);
    public static WindowsHardwareReadiness Capture()
    {
        long? total=null,available=null,disk=null;
        var error=new List<string>();
        if (OperatingSystem.IsWindows())
        {
            try { var status=new MemoryStatusEx {Length=(uint)Marshal.SizeOf<MemoryStatusEx>()};
                if (GetMemoryStatus(ref status) &&
                    status.TotalPhysical > 0 && status.AvailablePhysical <= status.TotalPhysical)
                {
                    total=checked((long)status.TotalPhysical);
                    available=checked((long)status.AvailablePhysical);
                }
                else error.Add("RAM_SENSOR_FAILED"); }
            catch(Exception ex) when (ex is DllNotFoundException or EntryPointNotFoundException or OverflowException)
            {error.Add("RAM_SENSOR_UNAVAILABLE");}
            try {var root=Path.GetPathRoot(Environment.SystemDirectory);
                if (!string.IsNullOrWhiteSpace(root))
                {
                    var drive=new DriveInfo(root);
                    if (drive.IsReady) disk=drive.AvailableFreeSpace;
                    else error.Add("SYSTEM_DISK_UNAVAILABLE");
                }
                else error.Add("SYSTEM_DISK_UNAVAILABLE");
            } catch(Exception ex) when (ex is IOException or UnauthorizedAccessException or ArgumentException)
            {error.Add("SYSTEM_DISK_UNAVAILABLE");}
        }
        else error.Add("WINDOWS_ONLY");
        return new(total,available,disk,Environment.ProcessorCount,
            error.Count==0?null:string.Join(";",error));
    }
}
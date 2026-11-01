// E-FINAL I0: existing WPF user-session only; native ACL and user consent mandatory.
using System;
using System.IO;
using Microsoft.Win32;
namespace NoxP01;
internal static class NoXAutostart
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string Entry = "NOX HELION";
    private static string CheckedExecutable(string? executable)
    {
        if (string.IsNullOrWhiteSpace(executable) || executable.Contains('"') ||
            !Path.IsPathFullyQualified(executable))
            throw new ArgumentException("NOX_AUTOSTART_ABSOLUTE_EXE_REQUIRED");
        var path = Path.GetFullPath(executable);
        if (!path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) || !File.Exists(path))
            throw new FileNotFoundException("NOX_AUTOSTART_OWNER_EXE_NOT_FOUND", path);
        FileSystemInfo? item = new FileInfo(path);
        while (item is not null) {
            if ((item.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new UnauthorizedAccessException("NOX_AUTOSTART_REPARSE_DENIED");
            item = item is DirectoryInfo d ? d.Parent : (item as FileInfo)?.Directory;
        }
        return path;
    }
    private static string Quoted(string path) => "\"" + path + "\"";
    internal static bool IsEnabled(string executable)
    {
        var command = Quoted(CheckedExecutable(executable));
        using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable:false);
        return key?.GetValue(Entry) is string stored &&
            string.Equals(stored, command, StringComparison.OrdinalIgnoreCase);
    }
    internal static bool SetEnabled(string executable, bool enabled, bool nativeConsent)
    {
        if (!nativeConsent) throw new UnauthorizedAccessException("NOX_AUTOSTART_OWNER_CONSENT_REQUIRED");
        var expected = Quoted(CheckedExecutable(executable));
        using var key = Registry.CurrentUser.CreateSubKey(RunKey, writable:true)
            ?? throw new IOException("NOX_AUTOSTART_HKCU_UNAVAILABLE");
        var old = key.GetValue(Entry) as string;
        if (old is not null && !string.Equals(old, expected, StringComparison.OrdinalIgnoreCase))
            throw new UnauthorizedAccessException("NOX_AUTOSTART_FOREIGN_ENTRY_HOLD");
        if (enabled) key.SetValue(Entry, expected, RegistryValueKind.String);
        else key.DeleteValue(Entry, throwOnMissingValue:false);
        return IsEnabled(executable);
    }
    // Original NSIS uninstaller should invoke only for a matching installed path.
    internal static void RemoveOnUninstall(string executable)
    {
        var expected = Quoted(CheckedExecutable(executable));
        using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable:true);
        if (key?.GetValue(Entry) is string existing &&
            string.Equals(existing, expected, StringComparison.OrdinalIgnoreCase))
            key.DeleteValue(Entry, throwOnMissingValue:false);
    }
}

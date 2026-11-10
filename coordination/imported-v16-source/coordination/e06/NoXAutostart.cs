// E-FINAL I0: existing WPF user-session only; native ACL and user consent mandatory.
using System;
using System.IO;
using Microsoft.Win32;
namespace NoxP01;
internal static class NoXAutostart
{
    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string Entry = "NOX HELION";
    private static string CheckedExecutable(string? executable, bool allowDeletedOnUninstall = false)
    {
        if (string.IsNullOrWhiteSpace(executable) || executable.Contains('"') ||
            !Path.IsPathFullyQualified(executable))
            throw new ArgumentException("NOX_AUTOSTART_ABSOLUTE_EXE_REQUIRED");
        var path = Path.GetFullPath(executable);
        if (!path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) ||
            (!allowDeletedOnUninstall && !File.Exists(path)))
            throw new FileNotFoundException("NOX_AUTOSTART_OWNER_EXE_NOT_FOUND", path);
        // NSIS may have already removed its own EXE before removing the HKCU Run value.
        // The missing leaf is allowed only for exact-match uninstall cleanup;
        // every surviving parent must still pass the original reparse gate.
        FileSystemInfo? item = File.Exists(path) ? new FileInfo(path)
            : new DirectoryInfo(Path.GetDirectoryName(path)!);
        while (item is not null) {
            if (item.Exists && (item.Attributes & FileAttributes.ReparsePoint) != 0)
                throw new UnauthorizedAccessException("NOX_AUTOSTART_REPARSE_DENIED");
            item = item is DirectoryInfo d ? d.Parent : (item as FileInfo)?.Directory;
        }
        return path;
    }
    private static string Quoted(string path) => "\"" + path + "\"";
    internal static bool IsEnabled(string executable)
    {
        // Legacy status callers must share the strict owner-only reader.
        // A foreign same-name HKCU value is HOLD, never silently OFF.
        return ReadOwnedState(executable);
    }
    // Owner-only, read-only durable HKCU proof after process restart.
    // A foreign value under the same name is never reported as NOX disabled.
    internal static bool ReadOwnedState(string executable)
    {
        var command = Quoted(CheckedExecutable(executable));
        using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable:false);
        if (key is null) return false;
        var hasEntry = Array.Exists(key.GetValueNames(), name =>
            string.Equals(name, Entry, StringComparison.OrdinalIgnoreCase));
        if (!hasEntry) return false;
        if (key.GetValueKind(Entry) != RegistryValueKind.String ||
            key.GetValue(Entry) is not string stored ||
            !string.Equals(stored, command, StringComparison.OrdinalIgnoreCase))
            throw new UnauthorizedAccessException("NOX_AUTOSTART_FOREIGN_ENTRY_HOLD");
        return true;
    }
    internal static bool SetEnabled(string executable, bool enabled, bool nativeConsent)
    {
        if (!nativeConsent) throw new UnauthorizedAccessException("NOX_AUTOSTART_OWNER_CONSENT_REQUIRED");
        var expected = Quoted(CheckedExecutable(executable));
        // Owner consent and path verification precede a read-only no-op.
        // A foreign entry is rejected by ReadOwnedState, not overwritten.
        // A mutation is checked again below under the writable handle.
        var observed = ReadOwnedState(executable);
        if (observed == enabled)
        {
            // A single no-op observation is not a durable SETTINGS receipt:
            // another process may replace this Run value before we respond.
            // Re-read using the same strict owner-only HKCU reader. A foreign
            // value throws HOLD; changed ON/OFF must never be reported saved.
            if (ReadOwnedState(executable) != enabled)
                throw new IOException("NOX_AUTOSTART_NOOP_READBACK_CHANGED_HOLD");
            return enabled;
        }
        // Disabling a missing Run entry must not create HKCU keys as a side effect.
        // The owner still validates consent, the original executable and path.
        using var key = enabled
            ? Registry.CurrentUser.CreateSubKey(RunKey, writable:true)
            : Registry.CurrentUser.OpenSubKey(RunKey, writable:true);
        if (key is null) {
            // Prove absence using the existing owner-only reader, not a guessed OFF.
            if (!enabled && !ReadOwnedState(executable)) return false;
            throw new IOException("NOX_AUTOSTART_HKCU_UNAVAILABLE");
        }
        // A foreign Run entry can be REG_DWORD/REG_BINARY/REG_NONE (or an
        // expandable string). "as string" silently treated it as absent and
        // overwrote unrelated HKCU owner data. Preserve every foreign kind.
        var hasEntry = Array.Exists(key.GetValueNames(), name =>
            string.Equals(name, Entry, StringComparison.OrdinalIgnoreCase));
        if (hasEntry && (key.GetValueKind(Entry) != RegistryValueKind.String ||
            key.GetValue(Entry) is not string old ||
            !string.Equals(old, expected, StringComparison.OrdinalIgnoreCase)))
            throw new UnauthorizedAccessException("NOX_AUTOSTART_FOREIGN_ENTRY_HOLD");
        // Idempotent ON/OFF must never rewrite or delete an unchanged owned value.
        // Readback still proves persistence; a foreign value was rejected above.
        if (hasEntry == enabled) {
            var unchanged = ReadOwnedState(executable);
            if (unchanged != enabled) throw new IOException("NOX_AUTOSTART_PERSISTENCE_UNVERIFIED");
            return unchanged;
        }
        if (enabled) key.SetValue(Entry, expected, RegistryValueKind.String);
        else key.DeleteValue(Entry, throwOnMissingValue:false);
        // A transport success is not evidence that HKCU persisted the value.
        // A mismatch (including enabled=false on a requested enable) is HOLD.
        var persisted = ReadOwnedState(executable);
        if (persisted != enabled) throw new IOException("NOX_AUTOSTART_PERSISTENCE_UNVERIFIED");
        return persisted;
    }
    // Original NSIS uninstaller should invoke only for a matching installed path.
    internal static void RemoveOnUninstall(string executable)
    {
        var expected = Quoted(CheckedExecutable(executable, allowDeletedOnUninstall:true));
        // Do not demand write permission for an absent or foreign Run value.
        // Exact ownership is rechecked under the writable handle before delete.
        using var probe = Registry.CurrentUser.OpenSubKey(RunKey, writable:false);
        if (probe is null || !Array.Exists(probe.GetValueNames(), name =>
            string.Equals(name, Entry, StringComparison.OrdinalIgnoreCase)))
            return; // Exact absence is a successful no-op; do not request HKCU write.
        // A foreign same-name value (including REG_DWORD/REG_EXPAND_SZ) is not
        // proof of successful NOX cleanup. Preserve it without requesting write.
        if (probe.GetValueKind(Entry) != RegistryValueKind.String ||
            probe.GetValue(Entry) is not string candidate ||
            !string.Equals(candidate, expected, StringComparison.OrdinalIgnoreCase))
            throw new UnauthorizedAccessException("NOX_AUTOSTART_UNINSTALL_FOREIGN_ENTRY_HOLD");
        using var key = Registry.CurrentUser.OpenSubKey(RunKey, writable:true);
        // A read-only owner preflight must not silently become a successful
        // uninstall when HKCU can no longer be opened for deletion.
        if (key is null)
            throw new IOException("NOX_AUTOSTART_UNINSTALL_HKCU_WRITE_UNAVAILABLE");
        if (key.GetValue(Entry) is string existing &&
            key.GetValueKind(Entry) == RegistryValueKind.String &&
            string.Equals(existing, expected, StringComparison.OrdinalIgnoreCase))
        {
            key.DeleteValue(Entry, throwOnMissingValue:false);
            // Verify the owned startup value actually disappeared. A foreign
            // value written concurrently remains untouched; never delete it.
            using var verify = Registry.CurrentUser.OpenSubKey(RunKey, writable:false);
            if (verify is not null &&
                Array.Exists(verify.GetValueNames(), name =>
                    string.Equals(name, Entry, StringComparison.OrdinalIgnoreCase))) {
                // A concurrent foreign replacement is preserved, never deleted
                // and never considered a successful uninstall receipt.
                if (verify.GetValueKind(Entry) == RegistryValueKind.String &&
                    verify.GetValue(Entry) is string remaining &&
                    string.Equals(remaining, expected, StringComparison.OrdinalIgnoreCase))
                    throw new IOException("NOX_AUTOSTART_UNINSTALL_PERSISTENCE_UNVERIFIED");
                throw new UnauthorizedAccessException("NOX_AUTOSTART_UNINSTALL_CONCURRENT_FOREIGN_ENTRY_HOLD");
            }
        }
        else if (Array.Exists(key.GetValueNames(), name =>
            string.Equals(name, Entry, StringComparison.OrdinalIgnoreCase)))
            // Ownership changed between read-only probe and writable check:
            // preserve foreign data, but do not issue false cleanup success.
            throw new UnauthorizedAccessException("NOX_AUTOSTART_UNINSTALL_OWNER_CHANGED_HOLD");
    }
}

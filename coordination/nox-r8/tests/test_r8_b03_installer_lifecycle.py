"""NOX R8 B03 NSIS lifecycle SOURCE_ONLY contract (not a Windows test)."""
from pathlib import Path
root = Path(__file__).resolve().parent.parent
ps = (root/"installer"/"NOX_R8_Lifecycle.ps1").read_text(encoding="utf-8")
ns = (root/"installer"/"NOX_R8_Lifecycle.nsi").read_text(encoding="utf-8")
for k in ("NOX_INSTALL_REPARSE_HOLD","NOX_INSTALL_UNMANAGED_OWNER_BINARY_HOLD",
          "NOX_INSTALL_CONCURRENT_HOLD","NOX_INSTALL_RUNNING_PROCESS_HOLD",
          "NOX_INSTALL_PAYLOAD_HASH_HOLD","NOX_INSTALL_STAGED_HASH_HOLD",
          "NOX_INSTALL_ACTIVATED_HASH_HOLD","NOX_INSTALL_ROLLBACK_HASH_HOLD",
          "NOX_INSTALL_ROLLBACK_READBACK_HOLD","NOX_INSTALL_RECEIPT_READBACK_HOLD",
          "owner_data_preserved=$true","real_qwen_e2e='NOT_TESTED_BY_INSTALLER'",
          "[IO.File]::Replace($temp,$p,$old,$true)","[IO.File]::Move($target,$oldPath)",
          "[IO.File]::Move($incoming,$target)"):
    assert k in ps, "NOX_B03_NSIS_GUARD_MISSING:"+k
for k in ("RequestExecutionLevel user",'InstallDir "$LOCALAPPDATA\\Programs\\NOX_HELION"',
          "!ifndef NOX_EXE_PATH","!ifndef NOX_EXE_SHA256","-Mode Install",
          "-Mode Uninstall",'StrCmp $0 "0" accepted','StrCmp $0 "0" accepted_uninstall'):
    assert k in ns, "NOX_B03_NSIS_WRAPPER_MISSING:"+k
# Regression for NSIS-hosted Windows PowerShell: do not depend on
# optional cmdlet autoload; hash the exact opened file via .NET.
assert "Get-FileHash -LiteralPath" not in ps
assert "$hasher.ComputeHash($stream)" in ps
assert "$hasher.Dispose()" in ps and "$stream.Dispose()" in ps
assert "[IO.FileShare]::Read" in ps
assert ps.index("GuardPath $p") < ps.index("$hasher.ComputeHash($stream)")
# Successful rollback must retain the displaced trusted version as a
# receipt-addressed candidate for another reversible rollback; never orphan it.
assert "SaveReceipt 'installed' $receipt.previous_sha256 '' ''" not in ps
assert "SaveReceipt 'installed' $receipt.previous_sha256 ([IO.Path]::GetFileName($displaced)) $receipt.current_sha256" in ps
assert "if ([IO.File]::Exists($target) -and" in ps
assert "-not [IO.File]::Exists($old) -and" in ps
assert "[IO.File]::Move($target,$old)" in ps
assert "[IO.File]::Move($displaced,$target)" in ps
assert ps.index("HashFile $old") < ps.index("[IO.File]::Move($target,$displaced)") < ps.index("SaveReceipt 'installed' $receipt.previous_sha256")
assert ps.index("HashFile $incoming") < ps.index("[IO.File]::Move($target,$oldPath)")
assert ps.index("GuardManaged $receipt") < ps.index("[IO.File]::Delete($target)")
for bad in ("Remove-Item -Recurse","RMDir /r","rmdir /s","NOX_R8_INSTALL_NATIVE_PASS"):
    assert bad not in ps+ns
print("B03_R8_NSIS_SOURCE_ONLY_PASS; native makensis/install/rollback pending")

"""T06: activate existing WPF MainWindow on disposable R11 source, never archive."""
from pathlib import Path
import hashlib,sys,re,os,tempfile
MAIN_SHA="6fc49544f77ec6ce2e7b2e8f3ab86c9a2a64c25d0eb3eb29547c5677851ef210"
ADDON_SHA="a4d6d981aca0d53cf6b8c0f2550e46a4313642e8"
def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def run(source,addon,backend_sha256=None):
    main=source/"MainWindow.xaml.cs"
    output=source/"Integration/MainWindow.NativeP02.cs"
    if not main.is_file() or main.is_symlink() or output.exists() or output.is_symlink():
        raise ValueError("T06_ORIGINAL_MAINWINDOW_COLLISION_OR_MISSING")
    data=main.read_bytes()
    if hashlib.sha256(data).hexdigest()!=MAIN_SHA:
        raise ValueError("T06_ORIGINAL_MAINWINDOW_SHA_HOLD")
    # Accept only the identical canonical Git blob despite Windows CRLF checkout.
    if addon.is_symlink():
        raise ValueError("T06_NATIVE_ADDON_GIT_BLOB_HOLD")
    extra=addon.read_bytes()
    if blob(extra)!=ADDON_SHA:
        if b"\r\n" not in extra or b"\r" in extra.replace(b"\r\n",b""):
            raise ValueError("T06_NATIVE_ADDON_GIT_BLOB_HOLD")
        canonical=extra.replace(b"\r\n",b"\n")
        if blob(canonical)!=ADDON_SHA:
            raise ValueError("T06_NATIVE_ADDON_GIT_BLOB_HOLD")
        extra=canonical
    # Pin the trusted, successfully IPC-tested Python EXE only in a
    # disposable staged MainWindow. The committed original addon stays exact.
    if backend_sha256 is not None:
        if type(backend_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}",backend_sha256):
            raise ValueError("T06_NATIVE_EXE_SHA_INVALID")
        marker='private const string NativePythonSha = "4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3";'
        decoded=extra.decode("utf-8")
        if decoded.count(marker)!=1:
            raise ValueError("T06_NATIVE_ORIGINAL_SHA_MARKER_HOLD")
        extra=decoded.replace(marker,
              'private const string NativePythonSha = "'+backend_sha256+'";').encode("utf-8")
    staged_blob=blob(extra)
    bom=data.startswith(b"\xef\xbb\xbf")
    text=data.decode("utf-8-sig")
    crlf="\r\n" in text
    text=text.replace("\r\n","\n")
    anchor='            core.SetVirtualHostNameToFolderMapping("nox.local", assets, CoreWebView2HostResourceAccessKind.DenyCors);\n            _initialized = true;'
    next_anchor='            core.SetVirtualHostNameToFolderMapping("nox.local", assets, CoreWebView2HostResourceAccessKind.DenyCors);\n            await InitializeNativeP02Async(core);\n            _initialized = true;'
    close='        Closing += (_, _) => WriteLog("CLOSE");'
    if text.count(anchor)!=1 or text.count(close)!=1:
        raise ValueError("T06_ORIGINAL_MAINWINDOW_WEBVIEW2_ANCHOR_HOLD")
    text=text.replace(anchor,next_anchor).replace(close,close+'\n        Closing += (_, _) => ShutdownNativeP02();')
    # Keep the original provider code and controls, but route local entrypoints
    # through the same native Python/P03 services. This prevents old WebView
    # messages from creating an independent chat transport or model queue.
    dispatch='            switch (type)'
    if text.count(dispatch)!=1:
        raise ValueError("K01_LEGACY_WEBVIEW_DISPATCH_ANCHOR_HOLD")
    text=text.replace(dispatch,
        '            if (TryDispatchLegacyNative(json.RootElement, e.Source)) return;\n'+dispatch,1)
    rewritten=text.replace("\n","\r\n") if crlf else text
    final=(b"\xef\xbb\xbf" if bom else b"")+rewritten.encode("utf-8")
    # One checked staged copy. Original committed donor bytes remain immutable.
    # The R11 staging directory is disposable, but never corrupt an original
    # MainWindow or strand the addon if a write/fsync/commit fails midway.
    output.parent.mkdir(parents=True,exist_ok=True)
    fd,temporary_name=tempfile.mkstemp(prefix=".nox-native-stage-",suffix=".tmp",dir=main.parent)
    temporary=Path(temporary_name)
    created_addon=False
    try:
        with os.fdopen(fd,"wb") as staged_main:
            staged_main.write(final)
            staged_main.flush()
            os.fsync(staged_main.fileno())
        if output.exists() or output.is_symlink():
            raise ValueError("T06_ORIGINAL_MAINWINDOW_COLLISION_OR_MISSING")
        with output.open("xb") as staged_addon:
            created_addon=True
            staged_addon.write(extra)
            staged_addon.flush()
            os.fsync(staged_addon.fileno())
        if blob(output.read_bytes())!=staged_blob:
            raise ValueError("T06_NATIVE_ADDON_STAGE_READBACK_HOLD")
        # Publish the fully durable main source in one final atomic operation.
        os.replace(temporary,main)
    except BaseException:
        temporary.unlink(missing_ok=True)
        if created_addon:
            output.unlink(missing_ok=True)
        raise
    print("T06_SHA_PINNED_ORIGINAL_MAINWINDOW_P02_SOURCE_WIRED")
if __name__=="__main__":
    if len(sys.argv) not in (3,4):raise SystemExit("USAGE: stage_native_p02.py R11 ADDON [PINNED_NATIVE_EXE_SHA256]")
    run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),
        sys.argv[3] if len(sys.argv)==4 else None)

"""T06: activate existing WPF MainWindow on disposable R11 source, never archive."""
from pathlib import Path
import hashlib,sys
MAIN_SHA="6fc49544f77ec6ce2e7b2e8f3ab86c9a2a64c25d0eb3eb29547c5677851ef210"
ADDON_SHA="0b65fc5ca62788dbde01e669e98769a23ac5e8a9"
def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def run(source,addon):
    main=source/"MainWindow.xaml.cs"
    output=source/"Integration/MainWindow.NativeP02.cs"
    if not main.is_file() or main.is_symlink() or output.exists() or output.is_symlink():
        raise ValueError("T06_ORIGINAL_MAINWINDOW_COLLISION_OR_MISSING")
    data=main.read_bytes()
    if hashlib.sha256(data).hexdigest()!=MAIN_SHA:
        raise ValueError("T06_ORIGINAL_MAINWINDOW_SHA_HOLD")
    extra=addon.read_bytes()
    if addon.is_symlink() or blob(extra)!=ADDON_SHA:
        raise ValueError("T06_NATIVE_ADDON_GIT_BLOB_HOLD")
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
    rewritten=text.replace("\n","\r\n") if crlf else text
    final=(b"\xef\xbb\xbf" if bom else b"")+rewritten.encode("utf-8")
    # One checked staged copy. Original committed donor bytes remain immutable.
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(extra);main.write_bytes(final)
    if blob(output.read_bytes())!=ADDON_SHA:
        raise ValueError("T06_NATIVE_ADDON_STAGE_READBACK_HOLD")
    print("T06_SHA_PINNED_ORIGINAL_MAINWINDOW_P02_SOURCE_WIRED")
if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("USAGE: stage_native_p02.py R11 ADDON")
    run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())

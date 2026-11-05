"""T06 · exact-no-loss repairs for six compiler diagnostics in the ORIGINAL R11.

Only the disposable, SHA-verified 94-file WPF stage is modified.
Duplicate P03 method bodies/properties MUST be literally identical, otherwise
fail closed rather than choosing an owner implementation.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import sys

PINS={
 "Packages/P03/module/ModelCenterEvent.cs":
 "94e15e68c6bdefc709121ab0b23a8379ffb84bc5d70e9ea40c284b7812a7f3fb",
 "Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs":
 "ccd0fb325eb8a250323f5aa17c8e7bdad0d281eb681ad381c96ee3a99498814e",
}
GLOBAL_USINGS="global using System.IO;\nglobal using System.Net.Http;\n"

def _read(path:Path,sha:str)->tuple[str,bool,bool]:
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("T06_ORIGINAL_OWNER_FILE_HOLD:"+str(path))
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:
        raise RuntimeError("T06_ORIGINAL_OWNER_SOURCE_SHA_HOLD:"+str(path))
    bom=raw.startswith(b"\xef\xbb\xbf")
    text=raw.decode("utf-8-sig")
    crlf="\r\n" in text
    return text.replace("\r\n","\n"),bom,crlf

def _write(path:Path,text:str,bom:bool,crlf:bool)->None:
    body=text.replace("\n","\r\n") if crlf else text
    content=(b"\xef\xbb\xbf" if bom else b"")+body.encode("utf-8")
    path.write_bytes(content)
    if path.read_bytes()!=content:
        raise RuntimeError("T06_WPF_STAGE_WRITE_READBACK_HOLD")

def main(root:Path)->None:
    root=root.resolve(strict=True)
    p03_event=root/"Packages/P03/module/ModelCenterEvent.cs"
    p03_window=root/"Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs"
    mainwindow=root/"MainWindow.xaml.cs"
    gl=root/"Integration/T06GlobalUsings.cs"
    if not mainwindow.is_file() or mainwindow.is_symlink() or gl.exists():
        raise RuntimeError("T06_WPF_STAGE_ORIGINAL_SOURCE_COLLISION")
    event,bom1,crlf1=_read(p03_event,PINS["Packages/P03/module/ModelCenterEvent.cs"])
    win,bom2,crlf2=_read(p03_window,PINS["Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs"])
    # Duplicate member is identical, not a second owner/API implementation.
    member="    public string? OperationId { get; init; }\n"
    if event.count(member)!=2 or member*2 not in event:
        raise RuntimeError("T06_P03_OPERATION_MEMBER_DUPLICATE_DRIFT")
    corrected_event=event.replace(member*2,member,1)
    start="    private void RefreshComponentActions()\n"
    first=win.find(start)
    second=win.find(start,first+len(start))
    if first<0 or second<0 or win.find(start,second+len(start))>=0:
        raise RuntimeError("T06_P03_COMPONENT_METHOD_COUNT_DRIFT")
    first_end=win.find("    private void ComponentOperationCombo_SelectionChanged(",first)
    second_end=win.find("    private static bool IsHttps(",second)
    if first_end<0 or second_end<0 or win[first:first_end].strip()!=win[second:second_end].strip():
        raise RuntimeError("T06_P03_DUPLICATE_METHODS_NOT_IDENTICAL")
    corrected_win=win[:second]+win[second_end:]
    original=mainwindow.read_bytes()
    has_bom=original.startswith(b"\xef\xbb\xbf")
    main=original.decode("utf-8-sig")
    has_crlf="\r\n" in main
    norm=main.replace("\r\n","\n")
    wrong="using NOX.P01.Packages.P02.OpenAI;"
    correct="using NoxP01.Packages.P02.OpenAI;"
    if norm.count(wrong)!=1 or norm.count(correct)!=0 or \
            norm.count("await InitializeNativeP02Async(core);")!=1:
        raise RuntimeError("T06_P02_OPENAI_NAMESPACE_OR_MAINWINDOW_ANCHOR_HOLD")
    fixed_main=norm.replace(wrong,correct,1)
    # Validate all four intended changes BEFORE writing any disposable source.
    if corrected_event==event or corrected_win==win or fixed_main==norm or \
            "private ComponentOperation ReadComponentOperation()" not in corrected_win or \
            corrected_win.count(start)!=1:
        raise RuntimeError("T06_WPF_NOLOSS_CHANGE_SET_HOLD")
    gl.parent.mkdir(parents=True,exist_ok=True)
    _write(p03_event,corrected_event,bom1,crlf1)
    _write(p03_window,corrected_win,bom2,crlf2)
    _write(mainwindow,fixed_main,has_bom,has_crlf)
    with gl.open("x",encoding="utf-8") as f:f.write(GLOBAL_USINGS)
    if gl.read_text("utf-8")!=GLOBAL_USINGS:
        raise RuntimeError("T06_WPF_GLOBAL_USINGS_READBACK_HOLD")
    print("T06_WPF_COMPAT_NOLOSS_STAGED",
          "P03_IDENTICAL_DUPLICATES","OPENAI_NAMESPACE","IO_HTTP_USINGS",flush=True)

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("USAGE: stage_wpf_compat_no_loss.py DISPOSABLE_R11")
    main(Path(sys.argv[1]))

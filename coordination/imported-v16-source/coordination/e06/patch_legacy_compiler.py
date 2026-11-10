"""E06 stage-only C# compatibility repair of pre-existing compiler errors.

Restores compileability without replacing approved D02, GUI, model, RAG or
installer sources. Applies only over pinned P01 C07 byte-identical preimages.
No canonical foreign-owner file is changed; #1/#3/#5 approval still required.
"""
import difflib
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
STAGE=ROOT/"work/e06/staged"
HOST=STAGE/"R11"
RUN="NOX-V16-E06-P01-STAGE-20261028-R03"
EXPECT={
    "MainWindow.xaml.cs":"6fc49544f77ec6ce2e7b2e8f3ab86c9a2a64c25d0eb3eb29547c5677851ef210",
    "Packages/P02/OpenAI/OpenAiResponsesProvider.cs":"968860590cb112b76b6399ad72d868269eebe6daec545bfead94fecd3e161449",
    "Packages/P05/InstallerRunReport.cs":"361b22e13af63427e0c53d67bd347571f78efedf9f5f1513e99401c63a49e85f",
    "Packages/P03/module/ComponentInstaller.cs":"2ae39faf5a19dd42a9787e1f3b98aaeb8d6efb2cd5165a9c6e59183daef07bf3",
    "Packages/P03/module/ModelCenterEvent.cs":"94e15e68c6bdefc709121ab0b23a8379ffb84bc5d70e9ea40c284b7812a7f3fb",
    "Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs":"ccd0fb325eb8a250323f5aa17c8e7bdad0d281eb681ad381c96ee3a99498814e"
}
OWNERS={"MainWindow.xaml.cs":6,"Packages/P02/OpenAI/OpenAiResponsesProvider.cs":2,
        "Packages/P05/InstallerRunReport.cs":5,
        "Packages/P03/module/ComponentInstaller.cs":3,
        "Packages/P03/module/ModelCenterEvent.cs":3,
        "Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs":3}
def digest(b):return hashlib.sha256(b).hexdigest()
def unique(old,token,replacement):
    if old.count(token)!=1:raise RuntimeError("DIAGNOSTIC_PATCH_UNEXPECTED_TOKEN:"+token)
    return old.replace(token,replacement,1)
def extract_span(src,token):
    start=src.index(token)
    brace=src.index("{",start)
    n=0
    for i in range(brace,len(src)):
        if src[i]=="{":n+=1
        if src[i]=="}":n-=1
        if n==0:return start,i+1,src[start:i+1]
    raise ValueError("METHOD_NOT_BALANCED")
def fix(path,src):
    if path=="MainWindow.xaml.cs":
        return unique(src,"using NOX.P01.Packages.P02.OpenAI;","using NoxP01.Packages.P02.OpenAI;")
    if path=="Packages/P02/OpenAI/OpenAiResponsesProvider.cs":
        if src.startswith("using System.Collections.Concurrent;"):
            return "using System.Net.Http;\nusing System.IO;\n"+src
        raise RuntimeError("P02_HEADER_DRIFT")
    if path=="Packages/P05/InstallerRunReport.cs":
        if src.startswith("using System.Globalization;"):return "using System.IO;\n"+src
        raise RuntimeError("P05_HEADER_DRIFT")
    if path=="Packages/P03/module/ComponentInstaller.cs":
        if src.startswith("using System.Diagnostics;"):return "using System.IO;\n"+src
        raise RuntimeError("P03_HEADER_DRIFT")
    if path=="Packages/P03/module/ModelCenterEvent.cs":
        duplicate="    public string? OperationId { get; init; }\n"
        if src.count(duplicate)!=2 or (duplicate+duplicate) not in src:
            raise RuntimeError("P03_OPERATION_ID_NOT_IDENTICAL")
        return src.replace(duplicate+duplicate,duplicate,1)
    if path=="Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs":
        result=src
        for method in ("private ComponentOperation ReadComponentOperation()",
                       "private void RefreshComponentActions()"):
            if result.count(method)!=2:raise RuntimeError("P03_DUPLICATE_METHOD_COUNT")
            first,_,first_body=extract_span(result,method)
            second_pos=result.index(method,first+len(first_body))
            second_start,second_end,second_body=extract_span(result[second_pos:],method)
            second_start+=second_pos;second_end+=second_pos
            if first_body!=second_body:raise RuntimeError("P03_METHOD_CONTENT_DIFFERS")
            result=result[:second_start]+result[second_end:]
        return result
    raise RuntimeError("UNREGISTERED_DIAGNOSTIC_OWNER_PATH")
def main():
    receipts=[]
    for name,expected in EXPECT.items():
        file=HOST/name
        source=file.read_bytes()
        if digest(source)!=expected:raise SystemExit("E06_PREIMAGE_HOLD:"+name)
        revised=fix(name,source.decode("utf-8")).encode("utf-8")
        if source==revised:raise SystemExit("E06_NOOP_PATCH:"+name)
        backup=STAGE/"original-owners"/name
        backup.parent.mkdir(parents=True,exist_ok=True)
        backup.write_bytes(source)
        file.write_bytes(revised)
        if backup.read_bytes()!=source or file.read_bytes()!=revised:
            raise SystemExit("E06_STAGE_READBACK_FAILED:"+name)
        diff="".join(difflib.unified_diff(source.decode().splitlines(keepends=True),
                revised.decode().splitlines(keepends=True),fromfile=name+":before",tofile=name+":after"))
        receipts.append({"path":"R11/"+name,"content_owner":OWNERS[name],
                         "e06_stage_owner":6,"run_id":RUN,"preimage_sha256":digest(source),
                         "postimage_sha256":digest(revised),
                         "patch_sha256":digest(diff.encode()),"patch_bytes":len(diff.encode()),
                         "stage_only":True,"owner_acceptance":"HOLD"})
    file=STAGE/"legacy-compiler-repair-receipts.json"
    file.write_text(json.dumps({"schema":"E06-STAGE-ONLY-PATCH-v1","run_id":RUN,
             "build_type":"DIAGNOSTIC_ONLY","release_accepted":False,"files":receipts},
             indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("E06_STAGED_COMPILER_PATCHES",len(receipts),"all originals retained")
if __name__=="__main__":main()

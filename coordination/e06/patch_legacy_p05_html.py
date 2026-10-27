"""E06 isolated diagnostic P05 raw-string repair. No repository owner file edited.

Historical P01 donor has a malformed C# raw string in InstallerRunReport.BuildHtml.
The safe fix transforms only that HTML literal to a C# 12 interpolated raw
string in the temporary Windows CI stage, with exact preimage SHA and receipt.
#5 must review/accept before any canonical owner-source merge.
"""
import difflib
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/"work/e06/staged/R11/Packages/P05/InstallerRunReport.cs"
EXPECTED="7a3056d025aeedc3117e5245ac9f84fe76ea4d4afd75e9d9570b31cbfc4e1c1d"
RUN="NOX-V16-E06-P01-STAGE-20261028-R03"
def sha(value):return hashlib.sha256(value).hexdigest()
def convert(match):
    value=match.group(1)
    out=[]
    for expression in value.split(" + "):
        if expression.startswith('"') and expression.endswith('"'):
            out.append(expression[1:-1])
        else:out.append("{{"+expression+"}}")
    return "".join(out)
def main():
    old=PATH.read_bytes()
    if sha(old)!=EXPECTED:raise SystemExit("P05_PREIMAGE_SHA_MISMATCH_DIAGNOSTIC_HOLD")
    source=old.decode("utf-8")
    begin=source.index('        return """<!doctype html>')
    end=source.index('</main></body></html>""";',begin)+len('</main></body></html>""";')
    original=source[begin:end]
    if "{{" in original:raise SystemExit("P05_TEMPLATE_ALREADY_INTERPOLATED")
    body=original[len('        return """'):-len('""";')]
    rewritten,count=re.subn(r'""" \+ (.*?) \+ """',convert,body,flags=re.S)
    if count!=16 or '"""' in rewritten or rewritten.count("{{")!=20:
        raise SystemExit("P05_HTML_EXPRESSION_MAP_CHANGED")
    content='        return $$"""\n'+"\n".join("        "+x for x in rewritten.splitlines())+'\n        """;'
    repaired=source[:begin]+content+source[end:]
    new=repaired.encode("utf-8")
    if not all(x.encode("utf-8") in new for x in ("<h1>INSTALLER RUN</h1>","Readback ACK","{{eventRows}}","{{roleProgressBars}}","{{readinessBars}}","{{E(snapshot.RunId)}}")):
        raise SystemExit("P05_HTML_CONTENT_PRESERVATION_FAILED")
    original_copy=ROOT/"work/e06/staged/P05_original_InstallerRunReport.cs.txt"
    original_copy.write_bytes(old)
    PATH.write_bytes(new)
    if original_copy.read_bytes()!=old or PATH.read_bytes()!=new:
        raise SystemExit("P05_BYTE_READBACK_FAILURE")
    diff="".join(difflib.unified_diff(source.splitlines(keepends=True),repaired.splitlines(keepends=True),fromfile="P05.original",tofile="P05.e06-diagnostic"))
    receipt={"schema":"NOX-E06-P05-STAGED-COMPILER-REPAIR-v1","run_id":RUN,"owner":6,
             "source_owner_review_required":5,"path":"R11/Packages/P05/InstallerRunReport.cs",
             "preimage_sha256":sha(old),"postimage_sha256":sha(new),
             "patch_sha256":sha(diff.encode("utf-8")),
             "replacement_count":count,"stage_only":True,"main_unchanged":True,
             "original_copy_sha256":sha(original_copy.read_bytes()),"release_accepted":False}
    result=ROOT/"work/e06/staged/P05-diagnostic-repair-receipt.json"
    result.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("E06_P05_BUILD_COMPAT_PATCH",json.dumps(receipt))
if __name__=="__main__":main()

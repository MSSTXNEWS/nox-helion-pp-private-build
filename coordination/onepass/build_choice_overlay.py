"""Create a derived full WEB V29.3 bundle, preserving frozen original bytes.

Only five owner-approved PC page HTML files gain a bootstrapped, functional
button-group enhancement. The 1,089-entry original ZIP is never overwritten.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile
from .frozen_web_contract import ZIP_SHA256, ZIP_FILES, sha256_file

ORIGINAL_SELECTS = {
    "site/pc/pages/cinema/index.html":1,
    "site/pc/pages/games/index.html":3,
    "site/pc/pages/graph/index.html":1,
    "site/pc/pages/music/index.html":2,
    "site/pc/pages/voice/index.html":6,
}
NEW_SCRIPT = "site/pc/nox-choice-buttons-v293.js"
SCRIPT_REF = '<script src="../../nox-choice-buttons-v293.js" defer></script>'
OVERLAY_VERSION = "NOX_WEB_V293_ONEPASS_REAL_CHOICE_BUTTONS_V1"


def build(source_zip: Path, target_zip: Path, script_file: Path) -> dict:
    if sha256_file(source_zip)!=ZIP_SHA256:
        raise ValueError("HOLD_FROZEN_ORIGINAL_SHA")
    if source_zip.resolve()==target_zip.resolve():
        raise ValueError("HOLD_CANNOT_REPLACE_FROZEN_ORIGINAL")
    script=script_file.read_bytes()
    if not 3500 <= len(script) <= 20000:
        raise ValueError("HOLD_CHOICE_SCRIPT_BYTES")
    raw=script.decode("utf-8")
    for required in ("MutationObserver","dispatchEvent(new Event('change'","aria-pressed",
                     "select.selectedIndex=index","prefers-reduced-motion"):
        if required not in raw:
            raise ValueError("HOLD_LIVE_BUTTON_EVENT_" + required[:25])
    if target_zip.exists():
        raise ValueError("HOLD_DERIVED_OUTPUT_ALREADY_EXISTS")
    temp=target_zip.with_suffix(target_zip.suffix+".part")
    if temp.exists():
        raise ValueError("HOLD_UNFINISHED_OUTPUT_EXISTS")
    changed={}
    total_selects=0
    try:
        with zipfile.ZipFile(source_zip,"r") as original,zipfile.ZipFile(temp,"w") as patched:
            items=original.infolist()
            if len(items)!=ZIP_FILES or original.testzip() is not None:
                raise ValueError("HOLD_ORIGINAL_ZIP_CRC")
            if NEW_SCRIPT in original.namelist():
                raise ValueError("HOLD_SCRIPT_ALREADY_IN_SOURCE")
            if not set(ORIGINAL_SELECTS).issubset(original.namelist()):
                raise ValueError("HOLD_REQUIRED_ORIGINAL_PC_PAGES")
            for info in items:
                before=original.read(info)
                after=before
                if info.filename in ORIGINAL_SELECTS:
                    html=before.decode("utf-8")
                    select_count=len(re.findall(r"<select\b",html,flags=re.I))
                    if select_count!=ORIGINAL_SELECTS[info.filename]:
                        raise ValueError("HOLD_FROZEN_SELECT_SOURCE_DRIFT")
                    if html.count("</body>")!=1 or SCRIPT_REF in html:
                        raise ValueError("HOLD_HTML_BODY_OR_SCRIPT_DRIFT")
                    html=html.replace("</body>",SCRIPT_REF+"\n</body>",1)
                    after=html.encode("utf-8")
                    changed[info.filename]={
                        "source_sha256":hashlib.sha256(before).hexdigest(),
                        "derived_sha256":hashlib.sha256(after).hexdigest(),
                        "selects_rebound":select_count,
                    }
                    total_selects+=select_count
                patched.writestr(info,after)
            patched.writestr(NEW_SCRIPT,script,compress_type=zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(temp) as checked:
            if len(checked.infolist())!=ZIP_FILES+1 or checked.testzip() is not None:
                raise ValueError("HOLD_DERIVED_ZIP_INTEGRITY")
            for filename in ORIGINAL_SELECTS:
                if SCRIPT_REF.encode("utf-8") not in checked.read(filename):
                    raise ValueError("HOLD_DERIVED_PAGE_MISSING_SCRIPT")
            if hashlib.sha256(checked.read(NEW_SCRIPT)).digest()!=hashlib.sha256(script).digest():
                raise ValueError("HOLD_DERIVED_SCRIPT_HASH")
        if total_selects!=13:
            raise ValueError("HOLD_13_SELECTS_SOURCE_DRIFT")
        os.replace(temp,target_zip)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return {
        "schema":OVERLAY_VERSION,
        "original_zip_sha256":ZIP_SHA256,
        "original_zip_entries":ZIP_FILES,
        "derived_zip_sha256":sha256_file(target_zip),
        "derived_zip_entries":ZIP_FILES+1,
        "script_sha256":hashlib.sha256(script).hexdigest(),
        "script_path":NEW_SCRIPT,
        "original_source_modified":False,
        "pages_modified":changed,
        "visible_dropdowns_replaced_by_live_buttons":total_selects,
        "method":"Original HTML select remains as event-bound hidden form control",
        "buttons_delegate_to_existing_change_handlers":True,
        "all_92_api_e2e_accepted":False,
        "windows_physical_qa_accepted":False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--script",type=Path,
                        default=Path("coordination/onepass/nox_choice_buttons_v293.js"))
    parser.add_argument("--manifest",type=Path)
    args=parser.parse_args()
    receipt=build(args.source,args.output,args.script)
    if args.manifest:
        args.manifest.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("NOX_ONEPASS_CHOICE_OVERLAY="+json.dumps(receipt,ensure_ascii=False,sort_keys=True))


if __name__=="__main__":
    main()

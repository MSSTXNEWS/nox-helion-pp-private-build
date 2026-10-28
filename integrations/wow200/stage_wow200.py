"""Add the exact, already-proven PR44 and PR38 WOW visual sources to R13 Creative.

No HOME rewrite, no replacement of owner-approved D02 or core routes.
Runs after stage_creative.py against a DISPOSABLE Windows R13 source tree.
"""
from __future__ import annotations
import hashlib, json, shutil, sys
from pathlib import Path

D02 = {
    "home.png":"382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a",
    "menu.png":"4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9",
    "core01.png":"343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97",
    "menu_sections.png":"7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4",
}

def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def gitsha(raw:bytes)->str:
    h=hashlib.sha1();h.update(f"blob {len(raw)}\0".encode());h.update(raw);return h.hexdigest()

def stage(root:Path, source:Path)->dict:
    root=root.resolve();source=source.resolve()
    if not (root/"NOX.P01.Shell.csproj").is_file():raise ValueError("R13_SOURCE_ROOT_HOLD")
    html=root/"Assets/creative/studio.html"
    if not html.is_file() or not (root/"Assets/creative/studio.js").is_file():raise ValueError("CREATIVE_NOT_STAGED_HOLD")
    if any(not (root/"Assets"/name).is_file() or digest(root/"Assets"/name)!=sha for name,sha in D02.items()):
        raise ValueError("CANONICAL_D02_SHA_HOLD")
    manifest=json.loads((source/"DONOR_BLOBS.json").read_text(encoding="utf-8"))
    if manifest.get("schema")!="NOX_WOW200_OWNER_BLOB_PIN_V1":raise ValueError("DONOR_MANIFEST_SCHEMA_HOLD")
    files=manifest["files"]
    if len(files)<45:raise ValueError("WOW_DONOR_INCOMPLETE_HOLD")
    dest=root/"Assets/creative/wow200"
    if dest.exists():raise ValueError("WOW200_ALREADY_INSTALLED_HOLD")
    plans=[]
    for rel, expected in files.items():
        if not rel.startswith(("proposals/", "legacy/")) or ".." in Path(rel).parts or Path(rel).is_absolute():
            raise ValueError("UNSAFE_WOW_SOURCE_PATH")
        origin=source/rel
        if not origin.is_file() or origin.is_symlink() or gitsha(origin.read_bytes())!=expected:
            raise ValueError("WOW_DONOR_BLOB_IDENTITY_HOLD:"+rel)
        plans.append((origin,dest/rel))
    # Do not modify approved art or any existing source file until all inputs pass.
    for rel in ["runtime/loader.mjs","runtime/stage.css"]:
        origin=source/rel
        if not origin.is_file() or origin.is_symlink():raise ValueError("WOW_RUNTIME_SOURCE_HOLD")
        plans.append((origin,dest/rel))
    old=html.read_text(encoding="utf-8-sig")
    if old.count("</head>")!=1 or old.count("</body>")!=1 or "wow200/runtime/loader.mjs" in old:
        raise ValueError("STUDIO_HTML_PREIMAGE_DRIFT")
    css_assets=[
        'wow200/proposals/NOX-PACK01-50/cinema50.css',
        'wow200/proposals/NOX-WOW51-100/wow51-100.css',
        'wow200/proposals/NOX-WOW101-150/director.css',
        'wow200/proposals/NOX-WOW151-200/finale.css',
        'wow200/proposals/NOX-WOW-UNIFIED-1-150/scene.css',
        'wow200/runtime/stage.css'
    ]
    new=old.replace('</head>', ''.join(f'<link rel="stylesheet" href="{rel}">' for rel in css_assets)+'</head>')
    new=new.replace("</body>",'<script type="module" src="wow200/runtime/loader.mjs"></script></body>')
    dest.mkdir(parents=True)
    copied=[]
    for origin,target in plans:
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(origin,target)
        copied.append({"path":str(target.relative_to(root)).replace("\\","/"),"sha256":digest(target),"bytes":target.stat().st_size})
    pre=digest(html)
    html.write_text(new,encoding="utf-8")
    copied.append({"path":"Assets/creative/studio.html","pre_sha256":pre,"sha256":digest(html)})
    for name,sha in D02.items():
        if digest(root/"Assets"/name)!=sha:raise ValueError("D02_POST_SHA_DRIFT")
    receipt={"schema":"NOX_V16_WOW200_ADDITIVE_R13_STAGE", "source":"PR44/PR38/PR14/PR15 immutable Git blobs", "files":copied,
      "count":len(copied),"D02_original_SHA256":D02,"same_EXE_QA":"NOT_RUN","GPU":"NOT_RUN",
      "source_only":True,"release_accepted":False}
    out=root.parent/"WOW200_STAGE_RECEIPT.json"
    out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return receipt

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("USAGE: stage_wow200.py STAGED_R11 WOW200_SOURCE")
    print("WOW200_ADDITIVE_STAGE",stage(Path(sys.argv[1]),Path(sys.argv[2]))["count"])
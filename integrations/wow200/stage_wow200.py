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

# Pinned Git blob of the owner-approved, 56-file exact donor source manifest.
# This prevents a fabricated 50-entry placeholder list passing as "WOW 1-200".
DONOR_MANIFEST_BLOB = "de7c6305c02023bd61c5acba3ffea5f62953a0d1"
DONOR_FILE_COUNT = 56
PACK01_CATALOG_BLOB = "c8c9b19e44d9b5ff3af00a38e8446d8c0507b69d"
# E01 PR144 HEAD f8bb7db02a5b01385d5d08329358be8c0936dfc2
# Source blobs verified identical in the frozen E06 PR162 candidate.
# Keep the old WOW200 donor *unchanged* as a separate legacy payload.
OWNER1_D02_ENGINE = {
    "proposals/NOX-CINEMA-FX/nox-cinema.mjs": {
        "active_blob": "7847ade31047b2534f929487ada9df02b14fb413",
        "legacy_blob": "f7724e99b37ccbc84f1756dc797980267d58ec4e",
    },
    "proposals/NOX-CINEMA-FX/nox-cinema.css": {
        "active_blob": "77417160147607f2d7350209b865d86bfe49abd0",
        "legacy_blob": "95b2562e8b6f5c07b785d3a381661d0dbfe5de83",
    },
}
REQUIRED_DONORS = frozenset({
    "proposals/NOX-WOW51-100/catalog.mjs",
    "proposals/NOX-WOW51-100/wow51-100.mjs",
    "proposals/NOX-WOW101-150/catalog.mjs",
    "proposals/NOX-WOW101-150/director.mjs",
    "proposals/NOX-WOW151-200/catalog.mjs",
    "proposals/NOX-WOW151-200/finale.mjs",
    "proposals/NOX-WOW-UNIFIED-1-150/gate.mjs",
    "proposals/NOX-CINEMA-FX/nox-cinema.mjs",
    "proposals/NOX-CINEMA-FX/nox-cinema.css",
    "proposals/NOX-PACK01-50/cinema50.mjs",
    "proposals/NOX-SUPER-CINEMA-3D/src/scene3d.mjs",
    "proposals/NOX-SUPER-CINEMA-3D/comfy_video_bridge.py",
})

# One immutable commit admits the R4 MENU module, matching CSS and native adapter.
# Keep all these pins together; a partial UI publication must fail before copy.
MENU_V2_SHA256 = {
    'ui/selfbuilder-menu-v2.mjs': '5b878f49a9e89bbdd56d153e44dabb130bf8c3031c20f24811451fdcad99f4f7',
    'ui/selfbuilder-menu-v2.css': '65979f2e8650adc097fc28352189f57aef8577654b534db5a9e9f20be89a3229',
    'ui/onehost-menu-bindings.mjs': '94e1cd2b6462ec3fec1016703bc8971ba782d34f366201f7bdf5cc2ff409f8b4',
    'ui/nox-r11-wow.mjs': '93455f888f0de964200a72ced4ee4cb309b407175ab180a1a0df39338904d5a8',
    'ui/nox-r11-wow.css': 'a05ed1e82d931940eeca0e92dd8f6880bb498f6176438949fecaf8fad8e28591',
    'ui/selfbuilder-wow-workbench.mjs': 'bd65520a6f349439fe2a2b2215520dcc84f3f4254b52aaa277201071423d6f17',
    'ui/selfbuilder-wow-workbench.css': 'a5ee4ea99ab109388f154e7ebd80c1524a6228be85b6d5a460bdce13b7e92eb1',
    'contracts/menu_v2_existing_routes.json': '7bb81852e3f28a170d94873d603253f89e5017f268d0af6942f4bcba3b55beea',
}

P01_OWNER_BLOBS = {
    "proposals/P01/WOW-MAX10/mount-p01.mjs": "e08be1d18f2760010e1b9e96dbe1f6f0da4203a9",
    "proposals/P01/WOW-MAX10/p01-cinematic-menu.mjs": "ddb33ae231b091c5be9a068a65db07c76e9c12b8",
    "proposals/P01/WOW-MAX10/p01-cinematic-menu.css": "7205f4b747ed6b95856e0207a9b52cce29f9d118",
    "proposals/P01/WOW-MAX10/scene-contract.mjs": "66e0dd2920fa98ce1af3d9d98d788c094daf945f",
    "proposals/P01/WOW-MAX10/route-dispatch.mjs": "6e1d24fe81211c19c9fefa14592753eab8235d41",
    "proposals/P01/WOW-MAX10/d02-native-events.mjs": "085fea4af1c0c8a0982abf4296cf21627e639516",
    "proposals/P01/WOW-MAX10/p01-visual-approval.mjs": "1f8a55ac2f579f544a9f00471aa187555c8e6dcd",
    "proposals/P01/WOW-MAX10/p01-mode-controller.mjs": "9301c32300cc64614fc8530b40bd3b3bd2cb1e65",
    "proposals/P01/WOW-MAX10/p01-responsive.mjs": "0f206239670272f2b026be8391622c3cc9a77db7",
}

def canonical_menu_bytes(path: Path) -> bytes:
    # Windows checkout may transcode LF to CRLF. Accept ONLY exact newline
    # normalization of SHA-pinned text; reject bare CR and ALL other drift.
    raw = path.read_bytes()
    if b'\r' in raw.replace(b'\r\n', b''):
        raise ValueError("MENU_V2_UNEXPECTED_CARRIAGE_RETURN")
    return raw.replace(b'\r\n', b'\n')

def menu_stage_plan(repo: Path, destination: Path) -> list:
    plans=[]
    for relative, expected in MENU_V2_SHA256.items():
        origin=repo/relative
        if (not origin.is_file() or origin.is_symlink() or
                any(parent.is_symlink() for parent in origin.parents if parent != repo) or
                hashlib.sha256(canonical_menu_bytes(origin)).hexdigest()!=expected):
            raise ValueError("MENU_V2_ATOMIC_SOURCE_PIN_HOLD:"+relative)
        plans.append((origin,destination/"ui"/origin.name))
    return plans

def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def gitsha(raw:bytes)->str:
    h=hashlib.sha1();h.update(f"blob {len(raw)}\0".encode());h.update(raw);return h.hexdigest()

def pinned_source_bytes(path: Path, expected: str):
    # Do NOT weaken source lock: accept raw bytes OR the exact approved
    # Git blob after normalizing checkout-only CRLF on text sources.
    raw = path.read_bytes()
    if gitsha(raw) == expected:
        return raw
    if b'\r\n' not in raw:
        return None
    try:
        raw.decode('utf-8', 'strict')  # never normalize arbitrary binary payloads
    except UnicodeDecodeError:
        return None
    try:
        canon = canonical_menu_bytes(path)
    except ValueError:
        return None
    return canon if gitsha(canon) == expected else None

def p01_owner_stage_plan(repo: Path, dest: Path) -> tuple[list, dict]:
    # Admit the ONE existing E01 P01 mount/route implementation as a complete,
    # path-pinned source unit. Not activated until a native host, eight approved
    # visual tiles and ten actual submenu DOM elements are attested.
    plans=[]
    content={}
    for relative, blob in P01_OWNER_BLOBS.items():
        origin=repo/relative
        if (not origin.is_file() or origin.is_symlink() or
                any(parent.is_symlink() for parent in origin.parents if parent != repo)):
            raise ValueError("P01_MENU10_SOURCE_PATH_HOLD:"+relative)
        verified=pinned_source_bytes(origin,blob)
        if verified is None:
            raise ValueError("P01_MENU10_SOURCE_BLOB_HOLD:"+relative)
        plans.append((origin,dest/relative))
        content[origin]=verified
    return plans, content

def stage(root:Path, source:Path)->dict:
    root=root.resolve();source=source.resolve()
    if not (root/"NOX.P01.Shell.csproj").is_file():raise ValueError("R13_SOURCE_ROOT_HOLD")
    html=root/"Assets/creative/studio.html"
    home_html=root/"Assets/index.html"
    if not home_html.is_file() or home_html.is_symlink():raise ValueError("ORIGINAL_D02_HTML_MISSING_HOLD")
    if not html.is_file() or not (root/"Assets/creative/studio.js").is_file():raise ValueError("CREATIVE_NOT_STAGED_HOLD")
    if any(not (root/"Assets"/name).is_file() or digest(root/"Assets"/name)!=sha for name,sha in D02.items()):
        raise ValueError("CANONICAL_D02_SHA_HOLD")
    manifest_path=source/"DONOR_BLOBS.json"
    if not manifest_path.is_file() or manifest_path.is_symlink() or pinned_source_bytes(manifest_path,DONOR_MANIFEST_BLOB) is None:
        raise ValueError("DONOR_MANIFEST_PIN_HOLD")
    manifest=json.loads(pinned_source_bytes(manifest_path,DONOR_MANIFEST_BLOB).decode("utf-8"))
    if manifest.get("schema")!="NOX_WOW200_OWNER_BLOB_PIN_V1":raise ValueError("DONOR_MANIFEST_SCHEMA_HOLD")
    files=manifest.get("files")
    if not isinstance(files,dict) or manifest.get("count")!=DONOR_FILE_COUNT or len(files)!=DONOR_FILE_COUNT:
        raise ValueError("WOW200_DONOR_COUNT_HOLD")
    if not REQUIRED_DONORS.issubset(set(files)):
        raise ValueError("WOW200_REQUIRED_ENGINE_MISSING_HOLD")
    # Verify both byte-identical immutable versions BEFORE touching the staged tree.
    # source is <repo>/integrations/wow200; owner1 source is <repo>/proposals/.
    owner1_root=source.parents[1]
    pack01_catalog=owner1_root/"proposals/NOX-PACK01-50/catalog.json"
    if (not pack01_catalog.is_file() or pack01_catalog.is_symlink() or
        pinned_source_bytes(pack01_catalog,PACK01_CATALOG_BLOB) is None):
        raise ValueError("PACK01_CATALOG_PIN_HOLD")
    catalog=json.loads(pinned_source_bytes(pack01_catalog,PACK01_CATALOG_BLOB).decode("utf-8"))
    actions=catalog.get("actions")
    if (catalog.get("status")!="SOURCE_CANDIDATE_NOT_INTEGRATED" or
        not isinstance(actions,list) or len(actions)!=50 or
        not all(isinstance(a,dict) and isinstance(a.get("routeId"),str) and
                isinstance(a.get("taskId"),str) and
                a.get("category") in {"chat","models","learning","voice","space"}
                for a in actions) or
        len({a["routeId"] for a in actions})!=50 or
        len({a["taskId"] for a in actions})!=50):
        raise ValueError("PACK01_CATALOG_50_ROUTES_HOLD")
    pinned_content={pack01_catalog:pinned_source_bytes(pack01_catalog,PACK01_CATALOG_BLOB)}
    for rel,pins in OWNER1_D02_ENGINE.items():
        archived=source/rel
        active=owner1_root/rel
        if (not archived.is_file() or archived.is_symlink() or
            pinned_source_bytes(archived,pins["legacy_blob"]) is None):
            raise ValueError("D02_LEGACY_ENGINE_SHA_HOLD:"+rel)
        if (not active.is_file() or active.is_symlink() or
            pinned_source_bytes(active,pins["active_blob"]) is None):
            raise ValueError("OWNER1_D02_ENGINE_SHA_HOLD:"+rel)
    dest=root/"Assets/creative/wow200"
    if dest.exists():raise ValueError("WOW200_ALREADY_INSTALLED_HOLD")
    for rel,pins in OWNER1_D02_ENGINE.items():
        pinned_content[source/rel]=pinned_source_bytes(source/rel,pins["legacy_blob"])
        pinned_content[owner1_root/rel]=pinned_source_bytes(owner1_root/rel,pins["active_blob"])
    plans=[(pack01_catalog,dest/"pack01-catalog.json")]
    menu_plans=menu_stage_plan(owner1_root,dest)
    plans.extend(menu_plans)
    p01_plans,p01_content=p01_owner_stage_plan(owner1_root,dest)
    plans.extend(p01_plans)
    pinned_content.update(p01_content)
    menu_origins={origin for origin,_ in menu_plans}
    for rel, expected in files.items():
        if not rel.startswith(("proposals/", "legacy/")) or ".." in Path(rel).parts or Path(rel).is_absolute():
            raise ValueError("UNSAFE_WOW_SOURCE_PATH")
        origin=source/rel
        if not origin.is_file() or origin.is_symlink() or pinned_source_bytes(origin,expected) is None:
            raise ValueError("WOW_DONOR_BLOB_IDENTITY_HOLD:"+rel)
        pinned_content[origin]=pinned_source_bytes(origin,expected)
        if rel in OWNER1_D02_ENGINE:
            # Active runtime import stays inside wow200/proposals/ and loads ONLY owner1.
            # Archive the original PR30 donor under a non-imported legacy directory.
            plans.append((origin,dest/"legacy/d02-pr30"/Path(rel).name))
            plans.append((owner1_root/rel,dest/rel))
        else:
            plans.append((origin,dest/rel))
    # Do not modify approved art or any existing source file until all inputs pass.
    for rel in ["runtime/loader.mjs","runtime/stage.css","runtime/home-scene.mjs","runtime/home-guard.css"]:
        origin=source/rel
        if not origin.is_file() or origin.is_symlink():raise ValueError("WOW_RUNTIME_SOURCE_HOLD")
        plans.append((origin,dest/rel))
    old=html.read_text(encoding="utf-8-sig")
    old_home=home_html.read_text(encoding="utf-8-sig")
    if old.count("</head>")!=1 or old.count("</body>")!=1 or "wow200/runtime/loader.mjs" in old:
        raise ValueError("STUDIO_HTML_PREIMAGE_DRIFT")
    # Actual D02 renderer only on the original central HELION+8 Core DOM.
    # Check the original source before injecting the PR30 mount; never rewrite HOME.
    if (old_home.count("</head>")!=1 or old_home.count("</body>")!=1 or
        any(marker not in old_home for marker in
           ("nox-orbit-stage", "nox-eclipse", "nox-orbit-core", "CONSCIOUSNESS", "FORGE")) or
        'creative/wow200/runtime/home-scene.mjs' in old_home):
        raise ValueError("D02_NINE_SPHERE_HTML_PREIMAGE_HOLD")
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
    new_home=old_home.replace('</head>',
        '<link rel="stylesheet" href="creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.css">'
        '<link rel="stylesheet" href="creative/wow200/runtime/home-guard.css">'
        '<link rel="stylesheet" href="creative/wow200/ui/selfbuilder-menu-v2.css">'
        '<link rel="stylesheet" href="creative/wow200/ui/selfbuilder-wow-workbench.css">'
        '<link rel="stylesheet" href="creative/wow200/ui/nox-r11-wow.css"><link rel="stylesheet" href="creative/wow200/proposals/P01/WOW-MAX10/p01-cinematic-menu.css"></head>')
    new_home=new_home.replace('</body>',
        '<script type="module" src="creative/wow200/runtime/home-scene.mjs"></script>'
        '<script type="module" src="creative/wow200/ui/onehost-menu-bindings.mjs"></script></body>')
    copied=[];out=root.parent/"WOW200_STAGE_RECEIPT.json"
    if out.exists():raise ValueError("WOW200_RECEIPT_CONFLICT_HOLD")
    try:
        dest.mkdir(parents=True)
        for origin,target in plans:
            target.parent.mkdir(parents=True,exist_ok=True)
            if origin in menu_origins:
                target.write_bytes(canonical_menu_bytes(origin))
            elif origin in pinned_content:
                target.write_bytes(pinned_content[origin])
            else:
                shutil.copyfile(origin,target)
            copied.append({"path":str(target.relative_to(root)).replace("\\","/"),
                           "sha256":digest(target),"bytes":target.stat().st_size})
        pre=digest(html);old_home_pre=digest(home_html)
        html.write_text(new,encoding="utf-8")
        copied.append({"path":"Assets/creative/studio.html","pre_sha256":pre,"sha256":digest(html)})
        home_html.write_text(new_home,encoding="utf-8")
        copied.append({"path":"Assets/index.html","pre_sha256":old_home_pre,"sha256":digest(home_html)})
        for name,sha in D02.items():
            if digest(root/"Assets"/name)!=sha:raise ValueError("D02_POST_SHA_DRIFT")
        receipt={"schema":"NOX_V16_WOW200_ADDITIVE_R13_STAGE", "source":"PR44/PR38/PR14/PR15 immutable Git blobs", "files":copied,
          "count":len(copied),"D02_original_SHA256":D02,"same_EXE_QA":"NOT_RUN","GPU":"NOT_RUN",
          "source_only":True,"release_accepted":False,"donor_file_count":DONOR_FILE_COUNT,
          "pack01_catalog_blob":PACK01_CATALOG_BLOB,"pack01_catalog_routes":50,
          "home_pr30_renderer_staged":True,
          "menu_v2_atomic_source_sha256":MENU_V2_SHA256,
          "menu_v2_native_ui_staged":True,"menu_v2_native_acceptance":"NOT_RUN",
          "p01_owner_source_staged":True,
          "p01_owner_source_git_blobs":P01_OWNER_BLOBS,
          "p01_owner_native_mount_activated":False,
          "p01_owner_native_route_e2e":"NOT_RUN",
          "active_d02_engine":"OWNER1_PR144_PINNED",
          "active_d02_git_blobs":{rel:p["active_blob"] for rel,p in OWNER1_D02_ENGINE.items()},
          "retained_legacy_d02_git_blobs":{rel:p["legacy_blob"] for rel,p in OWNER1_D02_ENGINE.items()},
          "active_d02_runtime_path":"Assets/creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.mjs",
          "legacy_d02_runtime_imported":False,
          "complete_200_runtime_verified":False}
        out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return receipt
    except BaseException:
        html.write_text(old,encoding="utf-8")
        home_html.write_text(old_home,encoding="utf-8")
        if dest.exists():shutil.rmtree(dest)
        raise

if __name__=="__main__":
    if len(sys.argv)!=3:raise SystemExit("USAGE: stage_wow200.py STAGED_R11 WOW200_SOURCE")
    print("WOW200_ADDITIVE_STAGE",stage(Path(sys.argv[1]),Path(sys.argv[2]))["count"])
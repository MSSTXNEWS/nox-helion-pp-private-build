#!/usr/bin/env python3
"""NOX WOW vendor fetch. Downloads sources as data only; never runs downloaded code."""
import concurrent.futures
import hashlib
import json
import os
import pathlib
import shutil
import time
import urllib.error
import urllib.request
import zipfile

REPOS = """
ColorlibHQ/gentelella
design-sparx/mantine-analytics-dashboard
Qualiora/shadboard
miskibin/chat-components
neikiri/neiki-assistant
assistant-ui/assistant-ui
assistant-ui/tool-ui
ibelick/prompt-kit
vercel/ai-elements
krisk/Fuse
pacocoursey/cmdk
missive/emoji-mart
joeattardi/picmo
SortableJS/Sortable
fullcalendar/fullcalendar
DayPilotCode/daypilot-javascript-scheduler-open-source
frappe/gantt
gridstack/gridstack.js
xyflow/xyflow
visjs/vis-timeline
maplibre/maplibre-gl-js
Leaflet/Leaflet
visgl/deck.gl
vasturiano/globe.gl
apache/echarts
leeoniya/uPlot
cytoscape/cytoscape.js
mermaid-js/mermaid
ecomfe/echarts-gl
mozilla/pdf.js
futurepress/epub.js
pqina/filepond
ueberdosis/tiptap
facebook/lexical
microsoft/monaco-editor
rtfpessoa/diff2html
excalidraw/excalidraw
xtermjs/xterm.js
sebhildebrandt/systeminformation
giampaolo/psutil
dexie/Dexie.js
ajv-validator/ajv
josdejong/jsoneditor
bradymholt/cronstrue
katspaugh/wavesurfer.js
sampotts/plyr
videojs/video.js
alphacep/vosk-api
lucide-icons/lucide
floating-ui/floating-ui
atomiks/tippyjs
kamranahmedse/driver.js
motiondivision/motion
iconify/iconify
sweetalert2/sweetalert2
Grsmto/simplebar
eclipsesource/jsonforms
rjsf-team/react-jsonschema-form
nanostores/nanostores
developit/mitt
golden-layout/golden-layout
haltu/muuri
nathancahill/split
caplin/FlexLayout
react-grid-layout/react-grid-layout
GoogleChromeLabs/container-query-polyfill
layoutit/grid
shadcn-ui/ui
radix-ui/primitives
shoelace-style/shoelace
ionic-team/ionic-framework
saadeghi/daisyui
tailwindlabs/tailwindcss
magicuidesign/magicui
TanStack/table
ag-grid/ag-grid
olifolkerd/tabulator
nhn/tui.calendar
nhn/tui.grid
nhn/tui.editor
recharts/recharts
d3/d3
jacomyal/sigma.js
visjs/vis-network
jaywcjlove/hotkeys-js
taye/interact.js
Pikaday/Pikaday
dropzone/dropzone
transloadit/uppy
ghosh/Micromodal
socketio/socket.io
ReactiveX/rxjs
yjs/yjs
shipshapecode/shepherd
usablica/intro.js
apvarun/toastify-js
lucaong/minisearch
nextapps-de/flexsearch
airbnb/lottie-web
rive-app/rive-web
mrdoob/three.js
tsparticles/tsparticles
jerosoler/Drawflow
retejs/rete
bpmn-io/bpmn-js
invoke-ai/InvokeAI
jtydhr88/ComfyArt
gpex-cloud/opengpex
fastlabai/design-editor
metiutek/editorimage-ai
comfyanonymous/ComfyUI
DenRakEiw/ComfyUI-InpaintCanvas
noah-thing/opentempl
DenRakEiw/scumble
fav-devs/stencil
ace-step/ACE-Step
facebookresearch/audiocraft
Stability-AI/stable-audio-tools
riffusion/riffusion-app-hobby
multimodal-art-projection/YuE
zhw2590582/ArtPlayer
thesysdev/open-intelligent-ui
tldraw/tldraw
flohoeller/affectui
honwee/mynah
""".strip().splitlines()
assert len(REPOS) == len(set(REPOS)) == 125
OUTPUT = pathlib.Path("nox_wow_vendor_out")
SOURCES = OUTPUT / "sources"
SOURCES.mkdir(parents=True, exist_ok=True)
TOKEN = os.environ.get("GITHUB_TOKEN", "")
USER_AGENT = "NOX-WOW-SourceVendor/2026-11-21"
def req(url, private=False):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if private and TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    return urllib.request.Request(url, headers=headers)
def download_one(repo):
    name = repo.replace("/", "__")
    record = {"repository": repo, "source_url":"https://github.com/"+repo, "status":"ERROR"}
    path = SOURCES / (name+".zip")
    try:
        with urllib.request.urlopen(req("https://api.github.com/repos/"+repo, True), timeout=40) as response:
            meta = json.load(response)
        commit = meta.get("default_branch")
        if not commit:
            raise RuntimeError("default_branch missing")
        with urllib.request.urlopen(req("https://api.github.com/repos/"+repo+"/commits/"+commit, True), timeout=40) as response:
            c = json.load(response)
        sha = c.get("sha")
        if not sha or len(sha)!=40: raise RuntimeError("invalid commit SHA")
        record.update({"commit_sha":sha,"default_branch":commit,"license_spdx":(meta.get("license") or {}).get("spdx_id"),"archived":meta.get("archived")})
        url = "https://codeload.github.com/"+repo+"/zip/"+sha
        record["download_url"] = url
        last_error = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req(url), timeout=180) as response, path.open("wb") as out:
                    shutil.copyfileobj(response,out,length=1024*1024)
                with zipfile.ZipFile(path) as archive:
                    members = archive.namelist()
                    if not members: raise RuntimeError("empty source ZIP")
                    if archive.testzip() is not None: raise RuntimeError("corrupt member")
                record.update({"status":"DOWNLOADED_VERIFIED","bytes":path.stat().st_size,"files":len(members),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"archive_path":"sources/"+path.name})
                return record
            except Exception as exc:
                last_error = str(exc)
                path.unlink(missing_ok=True)
                time.sleep(3*(attempt+1))
        raise RuntimeError(last_error)
    except Exception as exc:
        record["reason"] = str(exc)[:400]
        path.unlink(missing_ok=True)
        return record
def main():
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(download_one, REPOS))
    success = [r for r in results if r["status"] == "DOWNLOADED_VERIFIED"]
    OUTPUT.joinpath("manifest").mkdir(parents=True,exist_ok=True)
    summary = {"candidate_count":127,"github_repositories":len(REPOS),"downloaded":len(success),"failed":len(REPOS)-len(success),"exclusions":[{"name":"Aceternity UI","url":"https://ui.aceternity.com","reason":"gallery, no one authoritative upstream repository ZIP"},{"name":"tldraw starter kits","url":"https://tldraw.dev/starter-kits/overview","reason":"examples gallery; tldraw primary repository downloaded"}],"results":results,"note":"Source only. No model weights; no runtime installation; no license approval implied. Any failed downloads are listed explicitly."}
    OUTPUT.joinpath("manifest","FETCH_RESULTS.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    OUTPUT.joinpath("manifest","READ_ME_FIRST.md").write_text("# NOX WOW upstream sources\n\nAll vendor files here are original project ZIP source snapshots identified by commit SHA. Open the FETCH_RESULTS.json for per-repository integrity, provenance, exclusions, and failures. Nothing in the ZIP is automatically executed. Review licensing and version compatibility before integrating with existing NOX S03/STOP/owner routes.\n",encoding="utf-8")
    combined = pathlib.Path("NOX_WOW_UPSTREAM_SOURCES_20261121.zip")
    with zipfile.ZipFile(combined,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
        for f in sorted(OUTPUT.joinpath("manifest").glob("*")):
            z.write(f,arcname="manifest/"+f.name)
        for r in success:
            f = OUTPUT/r["archive_path"]
            z.write(f,arcname=r["archive_path"])
    digest = hashlib.sha256()
    with combined.open("rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b""):digest.update(chunk)
    print(json.dumps({"archive":combined.name,"archive_bytes":combined.stat().st_size,"archive_sha256":digest.hexdigest(),"repos":len(REPOS),"downloaded":len(success),"failed":len(REPOS)-len(success)}))
    if not success: raise SystemExit("no source downloads succeeded")
if __name__=="__main__":main()

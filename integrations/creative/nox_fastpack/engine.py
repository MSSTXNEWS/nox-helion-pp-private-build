"""NOX creative module. Optional Ollama/ComfyUI/FFmpeg/Blender/HF backends.

Public method dispatch() is the integration seam for existing NOX events.v3 and chat.
Never launches a heavy model, downloads weights, executes code, or changes PC state
without an explicit user action. The canonical HOME and its assets are untouched.
"""
from __future__ import annotations
import json
import hashlib
import re
import shutil
import subprocess
import threading
import time
import uuid
from .creative_extensions import CreativeExtensions
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MODEL_CATALOG = [
    ("wan22-ti2v-5b", "Wan 2.2 Text/Image→Video 5B", "video", "Wan-AI/Wan2.2-TI2V-5B", "24GB+ (official reference)"),
    ("wan22-t2v", "Wan 2.2 Text→Video A14B", "video", "Wan-AI/Wan2.2-T2V-A14B", "high VRAM"),
    ("wan22-i2v", "Wan 2.2 Image→Video A14B", "video", "Wan-AI/Wan2.2-I2V-A14B", "high VRAM"),
    ("wan22-animate", "Wan 2.2 Animate 14B", "anime", "Wan-AI/Wan2.2-Animate-14B", "high VRAM"),
    ("hunyuan15", "HunyuanVideo 1.5", "video", "tencent/HunyuanVideo-1.5", "14GB+ offload (Linux upstream); verify Windows"),
    ("sdxl-base", "SDXL Base 1.0", "photo", "stabilityai/stable-diffusion-xl-base-1.0", "varies"),
    ("flux-schnell", "FLUX.1 Schnell", "photo", "black-forest-labs/FLUX.1-schnell", "varies"),
    ("hunyuan3d-mini", "Hunyuan3D 2mini", "3d", "tencent/Hunyuan3D-2mini", "6 GB VRAM for shape per upstream; eligibility varies"),
    ("musicgen-small", "MusicGen Small", "sound", "facebook/musicgen-small", "varies"),
    ("kokoro-82m", "Kokoro 82M TTS", "voice", "hexgrad/Kokoro-82M", "varies"),
]
KINDS = ("movie", "cartoon2d", "cartoon3d", "anime", "adult18", "video", "photo", "3d", "voice", "sound", "slides", "site", "code", "memory", "learning")
TERMS = {"фильм":"movie", "кино":"movie", "мультик":"cartoon2d", "мультфильм":"cartoon2d", "аниме":"anime", "хентай":"adult18", "18+":"adult18", "видео":"video", "ролик":"video", "фото":"photo", "изображен":"photo", "картинк":"photo", "3д":"3d", "3d":"3d", "озвуч":"voice", "музык":"sound", "презентац":"slides", "сайт":"site", "код":"code", "программ":"code", "памят":"memory", "обучен":"learning"}

class StudioError(Exception):
    pass

def _get(url: str, *, payload=None, timeout=20):
    req = Request(url, data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
                  headers={"Content-Type":"application/json"} if payload is not None else {},
                  method="POST" if payload is not None else "GET")
    with urlopen(req, timeout=timeout) as res:
        return json.loads(res.read(8_000_000).decode("utf-8"))

class Studio(CreativeExtensions):
    """Local provider adapter; use through a trusted NOX host, not public internet."""
    def __init__(self, root: str | Path, ollama_model: str = ""):
        self.root=Path(root).expanduser().resolve()
        self.projects=self.root/"projects"; self.models=self.root/"models"; self.workflows=self.root/"workflows"
        self.projects.mkdir(parents=True,exist_ok=True)
        self.ollama_model=ollama_model
        self.ollama="http://127.0.0.1:11434"; self.comfy="http://127.0.0.1:8188"
        self._stop_event=threading.Event()
        self._process_lock=threading.Lock()
        self._active_process=None
        self._assemble_lock=threading.Lock()

    def _project(self, project_id: str):
        if not re.fullmatch(r"[a-z0-9_-]{1,48}",project_id,re.I): raise StudioError("Invalid project ID")
        p=self.projects/project_id; p.mkdir(parents=True,exist_ok=True); return p

    @staticmethod
    def _within(root:Path, path:Path):
        path=path.resolve();root=root.resolve()
        if not path.is_relative_to(root): raise StudioError("Path outside approved NOX directory")
        return path

    def status(self):
        def ping(url):
            try: return isinstance(_get(url,timeout=2),dict)
            except (URLError,OSError,ValueError):return False
        return {"status":"OK","engines":{"ollama":ping(self.ollama+"/api/tags"),"comfyui":ping(self.comfy+"/system_stats"),"ffmpeg":bool(shutil.which("ffmpeg")),"blender":bool(shutil.which("blender")),"trimesh":self._has_trimesh(),"tts":bool(shutil.which("espeak") or shutil.which("espeak-ng"))},"logo":"original NOX host asset (no fabricated replacement)","mobile":"client-responsive","projector":"user-gesture/fullscreen","integration":"ON_DEMAND_NATIVE_WORKER"}

    @staticmethod
    def _has_trimesh():
        try: import trimesh; return True
        except ImportError: return False

    @staticmethod
    def _digest_file(path):
        digest=hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(4*1024*1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _model_receipt_ok(self, model_id, repository, *, verify_hashes=False):
        # A standalone RECEIPT.json is NOT evidence of installed weights.
        # This only reads the existing Studio folder; it never downloads.
        root=self.models/model_id
        receipt=root/"RECEIPT.json"
        try:
            if root.is_symlink() or receipt.is_symlink() or not receipt.is_file():
                return False
            if receipt.stat().st_size > 65536:
                return False
            meta=json.loads(receipt.read_text(encoding="utf-8"))
            if (not isinstance(meta,dict) or meta.get("schema")!="NOX-CREATIVE-WEIGHTS-SHA256-V1"
                    or meta.get("model")!=model_id
                    or meta.get("repository")!=repository
                    or not isinstance(meta.get("revision"),str)
                    or not re.fullmatch(r"[0-9a-f]{40}",meta["revision"])):
                return False
            files=meta.get("files")
            if not isinstance(files,list) or not 1<=len(files)<=256:
                return False
            seen=set()
            for item in files:
                if not isinstance(item,dict):
                    return False
                name=item.get("filename")
                if (not isinstance(name,str) or len(name)>240 or name in seen
                        or "\\" in name or not re.search(r"\.(safetensors|gguf|ckpt|bin|pth)$",name,re.I)):
                    return False
                relative=Path(name)
                if relative.is_absolute() or not relative.parts or ".." in relative.parts:
                    return False
                seen.add(name)
                if (type(item.get("bytes")) is not int or item["bytes"]<=0
                        or not isinstance(item.get("sha256"),str)
                        or not re.fullmatch(r"[a-f0-9]{64}",item["sha256"])):
                    return False
                file=root/relative
                if file.is_symlink() or any(parent.is_symlink()
                    for parent in list(file.parents) if parent!=root and root in parent.parents):
                    return False
                if not file.is_file() or file.stat().st_size!=item["bytes"]:
                    return False
                if verify_hashes and self._digest_file(file)!=item["sha256"]:
                    return False
            return True
        except (OSError,ValueError,TypeError,UnicodeError):
            return False

    def catalog(self):
        return {"models":[{"id":a,"name":b,"category":c,"repository":d,"vram":e,
                          "url":"https://huggingface.co/"+d,
                          "installed":self._model_receipt_ok(a,d),
                          "checksum":"ON_DEMAND" if self._model_receipt_ok(a,d) else "HOLD"}
                          for a,b,c,d,e in MODEL_CATALOG],"categories":KINDS}

    def verify_model(self,model_id):
        model=self._model(model_id)
        if not self._model_receipt_ok(model_id,model[3],verify_hashes=True):
            raise StudioError("Installed model weights or SHA-256 receipt do not match")
        return {"status":"VERIFIED_LOCAL_SHA256","model":model_id,
                "note":"Local weight bytes match the receipt, not a remote publisher signature"}

    def _model(self, model_id):
        selected=next((m for m in MODEL_CATALOG if m[0]==model_id),None)
        if not selected: raise StudioError("Unknown allowlisted model")
        return selected

    def variants(self, model_id):
        model=self._model(model_id)
        try: from huggingface_hub import HfApi
        except ImportError as exc: raise StudioError("Install optional huggingface_hub for weight downloads") from exc
        data=HfApi().model_info(model[3],files_metadata=True)
        files=[{"path":s.rfilename,"bytes":getattr(s,"size",None)} for s in data.siblings or []
               if re.search(r"\.(safetensors|gguf|ckpt|bin|pth)$",s.rfilename,re.I)]
        return {"model":model_id,"files":files,"revision":data.sha,"license":(data.cardData or {}).get("license","CHECK_MODEL_CARD"),"url":"https://huggingface.co/"+model[3]}

    def download(self, model_id, filenames, revision, license_confirmed=False):
        model=self._model(model_id)
        if license_confirmed is not True:raise StudioError("Confirm license, size and storage before download")
        if not revision or not re.fullmatch(r"[0-9a-f]{40}",revision):raise StudioError("Pin a model revision from variants()")
        if not isinstance(filenames,list) or not 1<=len(filenames)<=256 or len(set(map(str,filenames)))!=len(filenames):
            raise StudioError("Choose unique exact weight files")
        try: from huggingface_hub import HfApi,snapshot_download
        except ImportError as exc:raise StudioError("Install optional huggingface_hub") from exc
        info=HfApi().model_info(model[3],revision=revision,files_metadata=True)
        valid={s.rfilename:s for s in info.siblings or []}
        if info.sha!=revision:
            raise StudioError("Pinned model repository revision changed")
        if any(not isinstance(x,str) or x not in valid or len(x)>240 or x.startswith("/")
               or ".." in Path(x).parts or "\\" in x
               or not re.search(r"\.(safetensors|gguf|ckpt|bin|pth)$",x,re.I)
               for x in filenames):
            raise StudioError("Unapproved weight filename")
        target=self.models/model_id;target.mkdir(parents=True,exist_ok=True)
        snapshot_download(repo_id=model[3],revision=revision,allow_patterns=filenames,local_dir=str(target),max_workers=2)
        files=[]
        for f in filenames:
            p=self._within(target,target/f)
            if not p.is_file() or p.is_symlink() or p.stat().st_size<=0:
                raise StudioError("Downloaded weight file missing or unsafe: "+f)
            expected=getattr(valid[f],"size",None)
            if expected is not None and p.stat().st_size!=expected:
                raise StudioError("Downloaded weight length mismatch: "+f)
            files.append({"filename":f,"bytes":p.stat().st_size,"sha256":self._digest_file(p)})
        receipt={"schema":"NOX-CREATIVE-WEIGHTS-SHA256-V1",
                 "model":model_id,"repository":model[3],"revision":revision,
                 "files":files,"source":"https://huggingface.co/"+model[3]}
        # No success receipt is published until every selected local file was
        # checked. Keep a previous approved receipt if the new write fails.
        tmp=target/("RECEIPT."+uuid.uuid4().hex+".tmp")
        try:
            tmp.write_text(json.dumps(receipt,indent=2),encoding="utf-8")
            tmp.replace(target/"RECEIPT.json")
        finally:
            if tmp.is_file():tmp.unlink()
        return {"status":"DOWNLOADED","receipt":receipt,
                "note":"Local weights SHA-256 recorded; model execution still requires an approved backend"}

    def _text(self, prompt, format_json=False):
        model=self.ollama_model
        if not model:
            try: tags=_get(self.ollama+"/api/tags",timeout=3).get("models",[])
            except (OSError,URLError,ValueError) as exc:raise StudioError("Ollama offline") from exc
            if not tags:raise StudioError("Select/download an Ollama chat model")
            model=tags[0].get("name","")
        try:
            result=_get(self.ollama+"/api/generate",{"model":model,"prompt":prompt,"stream":False,
                 **({"format":"json"} if format_json else {})},timeout=300)
        except (URLError,OSError,ValueError) as exc: raise StudioError("Ollama inference unavailable: "+str(exc)) from exc
        result=result.get("response","")
        if not result:raise StudioError("Empty model response")
        return result

    def storyboard(self, prompt,kind="movie",scenes=6,project_id=""):
        if kind not in KINDS[:6]:raise StudioError("Unsupported film type")
        if not 1<=int(scenes)<=30:raise StudioError("Scenes must be between 1 and 30")
        if not 4<=len(prompt)<=5000:raise StudioError("Story prompt must be 4..5000 chars")
        if kind=="adult18" and re.search(r"несовершеннолет|ребен|детск|minor|underage",prompt,re.I):
            raise StudioError("No sexual content involving minors")
        pid=project_id or uuid.uuid4().hex[:12];folder=self._project(pid)
        instruction=("Respond ONLY with valid JSON object: title, characters (array of objects containing name, "
                     "visual_identity, voice), scenes (array objects with scene_number, image_prompt, "
                     "video_prompt, dialogue, camera, duration_s, continuity_notes), soundtrack, subtitles. "
                     f"Exactly {scenes} scenes. Maintain character consistency across all scenes. "
                     f"Format: {kind}. User story: {prompt}")
        try: data=json.loads(self._text(instruction,True))
        except json.JSONDecodeError as exc:raise StudioError("Storyboard LLM returned invalid JSON") from exc
        if not isinstance(data,dict) or not isinstance(data.get("scenes"),list) or not data["scenes"]:raise StudioError("Invalid scenes")
        data["scenes"]=data["scenes"][:int(scenes)]
        (folder/"storyboard.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        # A real editable SRT timing draft, only from model-provided dialogue.
        def srt_stamp(seconds):
            t=max(0,int(seconds*1000)); h,r=divmod(t,3600000);m,r=divmod(r,60000);ss,ms=divmod(r,1000)
            return f"{h:02}:{m:02}:{ss:02},{ms:03}"
        cursor=0;lines=[]
        for i,scene in enumerate(data["scenes"],1):
            try: duration=max(1,min(180,int(float(scene.get("duration_s",6)))))
            except (ValueError,TypeError): duration=6
            dialogue=scene.get("dialogue","")
            if isinstance(dialogue,(list,dict)):dialogue=json.dumps(dialogue,ensure_ascii=False)
            if dialogue:
                lines.extend([str(i),f"{srt_stamp(cursor)} --> {srt_stamp(cursor+duration)}",str(dialogue).strip(),""])
            cursor+=duration
        (folder/"subtitles.srt").write_text("\n".join(lines),encoding="utf-8")
        return {"status":"STORYBOARD_READY","project_id":pid,"storyboard":data,
                "next":"Generate scenes with your approved installed workflow, then assemble clips"}


    def checkpoints(self):
        """Read actual installed ComfyUI checkpoint choices, not remote catalog names."""
        try:data=_get(self.comfy+"/object_info/CheckpointLoaderSimple",timeout=15)
        except (URLError,OSError,ValueError) as exc:raise StudioError("ComfyUI checkpoint catalog unavailable: "+str(exc)) from exc
        node=data.get("CheckpointLoaderSimple",{})
        names=node.get("input",{}).get("required",{}).get("ckpt_name",[[]])[0]
        if not isinstance(names,list):names=[]
        return {"checkpoints":[x for x in names if isinstance(x,str)],"status":"OK"}

    def basic_image_workflow(self,ckpt_name):
        """Install one editable stock-node ComfyUI image workflow for present checkpoint."""
        valid=self.checkpoints()["checkpoints"]
        if ckpt_name not in valid:raise StudioError("Checkpoint is not installed in ComfyUI")
        graph={
         "4":{"class_type":"CheckpointLoaderSimple","inputs":{"ckpt_name":ckpt_name}},
         "5":{"class_type":"EmptyLatentImage","inputs":{"width":768,"height":768,"batch_size":1}},
         "6":{"class_type":"CLIPTextEncode","inputs":{"text":"A cinematic obsidian sculpture, detailed light","clip":["4",1]}},
         "7":{"class_type":"CLIPTextEncode","inputs":{"text":"blurry, watermark, low quality","clip":["4",1]}},
         "8":{"class_type":"KSampler","inputs":{"seed":123456,"steps":20,"cfg":7.0,"sampler_name":"euler","scheduler":"normal","denoise":1.0,"model":["4",0],"positive":["6",0],"negative":["7",0],"latent_image":["5",0]}},
         "9":{"class_type":"VAEDecode","inputs":{"samples":["8",0],"vae":["4",2]}},
         "10":{"class_type":"SaveImage","inputs":{"filename_prefix":"NOX_Creative","images":["9",0]}}
        }
        self.workflows.mkdir(parents=True,exist_ok=True)
        path=self.workflows/"nox_basic_image_api.json"
        path.write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding="utf-8")
        return {"status":"WORKFLOW_READY","workflow":path.name,"text_node":"6","checkpoint":ckpt_name}

    def workflow(self,workflow_name,node_id,prompt):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,100}\.json",workflow_name):raise StudioError("Unsafe workflow name")
        path=self._within(self.workflows,self.workflows/workflow_name)
        if not path.is_file():raise StudioError("Install a ComfyUI API-format workflow first")
        graph=json.loads(path.read_text(encoding="utf-8"))
        node=graph.get(str(node_id))
        if not isinstance(node,dict) or not isinstance(node.get("inputs"),dict) or "text" not in node["inputs"]:
            raise StudioError("Explicit text node ID required")
        node["inputs"]["text"]=str(prompt)[:5000]
        try: data=_get(self.comfy+"/prompt",payload={"prompt":graph,"client_id":"nox_helion"},timeout=30)
        except (URLError,OSError,ValueError) as exc:raise StudioError("ComfyUI unavailable/rejected: "+str(exc)) from exc
        if not data.get("prompt_id"):raise StudioError("ComfyUI did not queue a job")
        return {"status":"QUEUED","prompt_id":data["prompt_id"],"workflow":workflow_name}

    def history(self,prompt_id):
        if not re.fullmatch(r"[a-fA-F0-9-]{10,64}",prompt_id):raise StudioError("Bad ComfyUI job ID")
        try: state=_get(self.comfy+"/history/"+prompt_id,timeout=20)
        except (URLError,OSError,ValueError) as exc:raise StudioError("ComfyUI history error: "+str(exc)) from exc
        if prompt_id not in state:return {"status":"RUNNING","prompt_id":prompt_id}
        job=state[prompt_id];outputs=[]
        for node in job.get("outputs",{}).values():
            for key in ("images","videos","gifs","audio","meshes"):
                for x in node.get(key,[]) if isinstance(node.get(key),list) else []:
                    if isinstance(x,dict) and x.get("filename"):
                        outputs.append({"filename":x["filename"],"subfolder":x.get("subfolder",""),"type":x.get("type","output"),"media":key})
        status=job.get("status",{}).get("status_str","")
        return {"status":"COMPLETE" if status=="success" else "FAILED" if status=="error" else "RUNNING", "prompt_id":prompt_id,"files":outputs,"engine_status":status}

    def import_asset(self,prompt_id,asset,project_id):
        state=self.history(prompt_id)
        if state["status"] != "COMPLETE" or asset not in state["files"]:
            raise StudioError("Only completed, reported ComfyUI assets may be imported")
        name=asset["filename"]
        if not re.fullmatch(r"[^/\\]{1,220}",name):raise StudioError("Bad output filename")
        folder=self._project(project_id)/"assets";folder.mkdir(parents=True,exist_ok=True)
        output=folder/(uuid.uuid4().hex[:8]+"_"+name)
        params=urlencode({"filename":name,"subfolder":asset["subfolder"],"type":asset["type"]})
        with urlopen(self.comfy+"/view?"+params,timeout=60) as inp,output.open("wb") as out:shutil.copyfileobj(inp,out)
        return {"status":"IMPORTED","file":str(output),"bytes":output.stat().st_size}

    def assemble(self,project_id,clips,soundtrack="",subtitle_file=""):
        with self._assemble_lock:
            self._stop_event.clear()
            return self._assemble_impl(project_id,clips,soundtrack,subtitle_file)

    def _assemble_impl(self,project_id,clips,soundtrack="",subtitle_file=""):
        folder=self._project(project_id)
        if not shutil.which("ffmpeg"):raise StudioError("FFmpeg unavailable")
        if not isinstance(clips,list) or not 1<=len(clips)<=100:raise StudioError("Choose 1..100 video clips")
        work=folder/"_normalized";work.mkdir(exist_ok=True)
        parts=[]
        for i,name in enumerate(clips):
            source=self._within(folder,folder/name)
            if not source.is_file():raise StudioError("Clip missing: "+name)
            dst=work/(f"clip_{i:03}.mp4")
            cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(source),"-vf",
                 "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24",
                 "-an","-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p",str(dst)]
            self._exec(cmd,1200);parts.append(dst)
        manifest=work/"concat.txt"
        manifest.write_text("".join("file '"+p.name+"'\n" for p in parts),encoding="utf-8")
        output=folder/"NOX_MOVIE_FINAL.mp4"
        cmd=["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",str(manifest)]
        if soundtrack:
            audio=self._within(folder,folder/soundtrack)
            if not audio.is_file():raise StudioError("Soundtrack missing")
            cmd += ["-i",str(audio)]
        if subtitle_file:
            sub=self._within(folder,folder/subtitle_file)
            if not sub.is_file() or sub.suffix.lower()!='.srt':raise StudioError("SRT subtitle file missing")
            cmd += ["-i",str(sub)]
        cmd += ["-map","0:v:0"]
        if soundtrack:cmd += ["-map","1:a:0"]
        if subtitle_file:cmd += ["-map",("2:s:0" if soundtrack else "1:s:0")]
        cmd += ["-c:v","copy"]
        if soundtrack:cmd += ["-c:a","aac","-shortest"]
        if subtitle_file:cmd += ["-c:s","mov_text"]
        cmd += ["-movflags","+faststart",str(output)]
        self._exec(cmd,3600)
        if not output.exists() or not output.stat().st_size:raise StudioError("Empty MP4 output")
        return {"status":"RENDERED","path":str(output),"bytes":output.stat().st_size,"clips":len(clips)}

    def _exec(self,argv,timeout):
        try:
            proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        except OSError as exc:raise StudioError(str(exc)) from exc
        with self._process_lock:self._active_process=proc
        try:
            deadline=time.monotonic()+timeout
            while proc.poll() is None:
                if self._stop_event.is_set():
                    proc.kill();proc.communicate(timeout=5)
                    raise StudioError('Render cancelled by STOP')
                if time.monotonic()>deadline:
                    proc.kill();proc.communicate(timeout=5)
                    raise StudioError('Render timed out')
                time.sleep(.08)
            _,stderr=proc.communicate(timeout=5)
            if proc.returncode:raise StudioError((stderr or b'FFmpeg failed').decode('utf-8','replace')[-1300:])
        finally:
            with self._process_lock:
                if self._active_process is proc:self._active_process=None

    def stop(self,interrupt_comfy=False):
        """Cancel this Studio's active FFmpeg; Comfy interruption separately consented."""
        self._stop_event.set()
        with self._process_lock:proc=self._active_process
        ffmpeg_running=bool(proc and proc.poll() is None)
        if ffmpeg_running:proc.kill()
        result={'status':'STOP_REQUESTED' if ffmpeg_running else 'NO_ACTIVE_LOCAL_RENDER',
                'ffmpeg_cancelled':ffmpeg_running,'comfy_interrupted':False}
        if interrupt_comfy:
            try:
                _get(self.comfy+'/interrupt',payload={},timeout=10)
                result['comfy_interrupted']=True
                result['warning']='ComfyUI /interrupt may stop other jobs on a shared instance'
            except (URLError,OSError,ValueError) as exc:
                result['comfy_error']=str(exc)
        return result

    def create_text(self,kind,prompt,project_id=""):
        rules={"slides":("Create a 10-slide Markdown presentation with titles and concise speaker notes.","md"),
               "site":("Create an original, accessible single HTML file containing CSS and JS; no external scripts.","html"),
               "code":("Write complete code with language and dependencies. Do not execute.","txt"),
               "voice":("Prepare voiceover dialogue with scene timestamps.","txt"),
               "sound":("Compose an original music/SFX production cue sheet; do not copy songs.","md"),
               "memory":("Propose sourced memory additions, distinguish observations from guesses.","md"),
               "learning":("Propose controlled improvement experiment, held-out test and rollback. Do not claim trained weights.","md")}
        if kind not in rules:raise StudioError("Unsupported text artifact")
        folder=self._project(project_id or uuid.uuid4().hex[:12]);guide,ext=rules[kind]
        content=self._text(guide+"\nUser: "+str(prompt)[:4000]);path=folder/(kind+"."+ext)
        path.write_text(content,encoding="utf-8")
        return {"status":"CREATED","kind":kind,"project_id":folder.name,"path":str(path),"bytes":path.stat().st_size}

    def chat_route(self,text):
        if not isinstance(text,str) or len(text)>6000:raise StudioError("Invalid chat text")
        normalized=text.lower().strip();match=next(((t,k) for t,k in TERMS.items() if t in normalized),None)
        if not match:return {"handled":False}
        kind=match[1]
        return {"handled":True,"kind":kind,"requested_action":"studio_open","prompt":text,
                "next":"Confirm generation in studio or explicitly request 'create_storyboard'/'create_text'"}

    def dispatch(self,request:dict):
        """NOX host-only dispatch; never use a public unauthenticated network endpoint."""
        if not isinstance(request,dict):raise StudioError("Expected request object")
        action=request.get("action","")
        if action=="status":return self.status()
        if action=="stop":return self.stop(request.get("interrupt_comfy",False))
        if action=="catalog":return self.catalog()
        if action=="verify_model":return self.verify_model(request.get("model_id",""))
        if action=="variants":return self.variants(request.get("model_id",""))
        if action=="download":return self.download(request.get("model_id",""),request.get("filenames",[]),request.get("revision",""),request.get("license_confirmed",False))
        if action=="route_chat":return self.chat_route(request.get("text",""))
        if action=="chat_execute":return self.chat_execute(request.get("text",""),request.get("project_id",""),request.get("scenes",6))
        if action=="project_files":return self.project_files(request.get("project_id",""))
        if action=="make_3d":return self.make_3d(request.get("project_id",""),request.get("form","sphere"),request.get("color","#b9753c"))
        if action=="speak":return self.speak(request.get("text",""),request.get("project_id",""),request.get("language","ru"))
        if action=="storyboard":return self.storyboard(request.get("prompt",""),request.get("kind","movie"),request.get("scenes",6),request.get("project_id",""))
        if action=="checkpoints":return self.checkpoints()
        if action=="basic_image_workflow":return self.basic_image_workflow(request.get("checkpoint",""))
        if action=="workflow":return self.workflow(request.get("workflow",""),request.get("text_node",""),request.get("prompt",""))
        if action=="history":return self.history(request.get("prompt_id",""))
        if action=="import_asset":return self.import_asset(request.get("prompt_id",""),request.get("asset",{}),request.get("project_id",""))
        if action=="assemble":return self.assemble(request.get("project_id",""),request.get("clips",[]),request.get("soundtrack",""),request.get("subtitle_file",""))
        if action=="create_text":return self.create_text(request.get("kind",""),request.get("prompt",""),request.get("project_id",""))
        raise StudioError("Unknown studio action")

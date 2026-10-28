"""NOX Film Studio: bounded FFmpeg offline assembly into a real MP4.
Runs only after the native host verifies all clip SHA256 receipts and user consent.
All input files must live in the approved media store, never a URL or untrusted path.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import re
import subprocess
import tempfile

from film_studio import FilmProject, Scene, validate, Hold, Denied, SHA, FILE

MAX_CLIP = 4 * 1024**3
CHUNK = 1 << 20

@dataclass(frozen=True)
class Clip:
    scene_id: str
    filename: str
    sha256: str

def safe_media(root: Path, filename: str, expected_sha256: str, *, suffixes: tuple[str,...]):
    if not isinstance(filename,str) or not re.fullmatch(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,170}$",filename) or filename.lower().endswith(suffixes) is False:
        raise Hold("FILM_INPUT_NAME_INVALID")
    if not SHA.fullmatch(expected_sha256 or ""):
        raise Hold("FILM_INPUT_SOURCE_HASH_REQUIRED")
    root = Path(root)
    if root.is_symlink():
        raise Hold("FILM_ROOT_SYMLINK_DENIED")
    file = root/filename
    if file.is_symlink() or not file.is_file() or not 0 < file.stat().st_size <= MAX_CLIP:
        raise Hold("FILM_INPUT_NOT_VALID")
    hasher=sha256()
    with file.open("rb") as f:
        while block:=f.read(CHUNK):
            hasher.update(block)
    if hasher.hexdigest()!=expected_sha256.lower():
        raise Hold("FILM_INPUT_SHA_MISMATCH")
    return file

def _run(args:list[str], *, cwd:Path, timeout:int,runner):
    # No shell, no user arguments merged into FFmpeg options or filter strings.
    result=runner(args,cwd=str(cwd),timeout=timeout,check=False,
                 stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode!=0:
        raise Hold("FFMPEG_RENDER_FAILED")
    return result

def srt_time(seconds:float)->str:
    ms=round(seconds*1000)
    return f"{ms//3600000:02}:{(ms//60000)%60:02}:{(ms//1000)%60:02},{ms%1000:03}"

def subtitles(project:FilmProject)->str:
    validate(project)
    lines=[];current=0;counter=0
    for scene in project.scenes:
        text=(scene.dialogue or scene.narration).replace("\r"," ").replace("\n"," ").strip()
        if text:
            counter+=1
            # User-provided dialogue is text only, not an FFmpeg command or filter expression.
            lines.extend([str(counter),srt_time(current)+" --> "+srt_time(current+scene.seconds),text,""])
        current+=scene.seconds
    return "\n".join(lines)

def export_movie(project:FilmProject, *, clip_root:Path, clips:list[Clip],
                 output_root:Path, ffmpeg_binary:str, user_approved:bool,
                 ffmpeg_host_attested:bool,runner=subprocess.run)->dict:
    validate(project,require_export_ready=True)
    if user_approved is not True or ffmpeg_host_attested is not True:
        raise Denied("NATIVE_EXPORT_APPROVAL_REQUIRED")
    # Host must attest and select its trusted ffmpeg binary, not accept an arbitrary
    # executable path from browser JS. No shell invocation.
    if not ffmpeg_binary or not Path(ffmpeg_binary).name.lower() in ("ffmpeg","ffmpeg.exe"):
        raise Hold("TRUSTED_FFMPEG_BINARY_REQUIRED")
    by_id={c.scene_id:c for c in clips}
    if len(by_id)!=len(clips) or len(by_id)!=len(project.scenes):
        raise Hold("FILM_CLIP_LIST_INCOMPLETE")
    for scene in project.scenes:
        clip=by_id.get(scene.id)
        if clip is None or clip.sha256!=scene.output_sha256 or clip.filename!=scene.output_filename:
            raise Hold("SCENE_RENDER_RECEIPT_MISMATCH")
        safe_media(clip_root,clip.filename,clip.sha256,suffixes=(".mp4",".webm"))
    output_root=Path(output_root)
    if output_root.is_symlink():
        raise Hold("OUTPUT_ROOT_SYMLINK_DENIED")
    output_root.mkdir(parents=True,exist_ok=True)
    # Never silently overwrite an earlier approved film.
    target=output_root/(project.project_id+".mp4")
    if target.exists() or target.is_symlink():
        raise Hold("FILM_OUTPUT_ALREADY_EXISTS")
    with tempfile.TemporaryDirectory(prefix="nox-film-",dir=output_root) as temp:
        work=Path(temp)
        normalized=[]
        for i,scene in enumerate(project.scenes):
            source=clip_root/by_id[scene.id].filename
            name=f"shot_{i:03}.mp4"
            dst=work/name
            _run([ffmpeg_binary,"-nostdin","-hide_banner","-loglevel","error",
             "-y","-i",str(source),
             "-map","0:v:0","-an","-vf",
             f"scale={project.width}:{project.height}:force_original_aspect_ratio=decrease,"
             f"pad={project.width}:{project.height}:(ow-iw)/2:(oh-ih)/2,fps={project.fps}",
             "-c:v","libx264","-preset","veryfast","-crf","20",
             "-pix_fmt","yuv420p","-t",str(scene.seconds),
             str(dst)],cwd=work,timeout=max(120,scene.seconds*120),runner=runner)
            if not dst.is_file() or dst.stat().st_size<8:
                raise Hold("NORMALIZED_SCENE_MISSING")
            normalized.append(name)
        # Relative sanitized names only; safe=1 as prescribed by FFmpeg.
        manifest=work/"concat.ffconcat"
        manifest.write_text("ffconcat version 1.0\n"+
            "".join("file '"+n+"'\n" for n in normalized),encoding="ascii")
        output=work/"movie.mp4"
        _run([ffmpeg_binary,"-nostdin","-hide_banner","-loglevel","error",
         "-y","-safe","1","-f","concat","-i",str(manifest),
         "-map","0:v:0","-an","-c","copy","-movflags","+faststart",
         str(output)],cwd=work,timeout=max(120,project_duration(project)*12),runner=runner)
        if not output.is_file() or output.stat().st_size<8:
            raise Hold("FILM_EXPORT_MISSING")
        srt=subtitles(project)
        captions=output_root/(project.project_id+".srt")
        if captions.exists() or captions.is_symlink():
            raise Hold("FILM_SUBTITLE_FILE_ALREADY_EXISTS")
        if srt:
            captions.write_text(srt,encoding="utf-8")
        # Atomic same-volume publish after all scene and assembly gates.
        os.replace(output,target)
        signature=sha256()
        with target.open("rb") as file:
            while block:=file.read(CHUNK): signature.update(block)
        return {"status":"FILE_EXPORTED_NOT_NATIVE_QA_ACCEPTED",
            "file":target.name,"sha256":signature.hexdigest(),
            "bytes":target.stat().st_size,"subtitle":captions.name if srt else None,
            "shots":len(project.scenes),"seconds":project_duration(project)}

def project_duration(p:FilmProject)->int:
    return sum(s.seconds for s in p.scenes)

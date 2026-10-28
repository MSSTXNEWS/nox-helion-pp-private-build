"""NOX HELION · Film Studio V16, canonical native-host planning and render receipts.
Source-level component; DOES NOT imply installed video checkpoints or a finished EXE.
Uses one existing ComfyUI queue through ComfyVideoPort, never a new AI backend.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import re

from comfy_video_bridge import ComfyVideoPort, NativeVideoPreflight, Denied, Hold

PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
SHOT_ID = re.compile(r"^s-[a-z0-9-]{2,60}$")
CHARACTER_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
SHA = re.compile(r"^[0-9a-f]{64}$", re.I)
FILE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,170}\.(mp4|webm)$", re.I)
STYLES = {
    "photoreal": "фотореалистичное кино",
    "anime": "аниме",
    "cartoon_2d": "2D-мультфильм",
    "cartoon_3d": "3D-мультфильм",
    "stop_motion": "покадровая анимация",
    "manga_motion": "ожившая манга",
    "noir": "нуар",
    "fantasy": "фэнтези",
    "sci_fi": "научная фантастика",
    "documentary": "документальное кино",
    "cinematic_3d": "объёмное кино",
    "adult_anime_18": "аниме для взрослых (18+)",
}
RATINGS = ("GENERAL", "TEEN", "ADULT_18")
MAX_SCENES = 250
MAX_SHOT_SECONDS = 20
MAX_PROJECT_SECONDS = 3600  # longer films are assembled from saved chapters.
DEFAULT_PROVIDER = "wan21-t2v-1.3b"

@dataclass(frozen=True)
class Character:
    id: str
    name: str
    description: str
    age: int | None = None
    visual_reference_sha256: str | None = None
    owner_rights_approved: bool = False
    adult_appearance_attested: bool = False

@dataclass(frozen=True)
class Scene:
    id: str
    title: str
    prompt: str
    seconds: int = 6
    operation: str = "t2v"
    provider_id: str = DEFAULT_PROVIDER
    character_ids: tuple[str, ...] = ()
    reference_sha256: str | None = None
    narration: str = ""
    dialogue: str = ""
    camera: str = "cinematic"
    status: str = "PLANNED"  # Never fake QUEUED or RENDERED.
    output_sha256: str | None = None
    output_filename: str | None = None

@dataclass(frozen=True)
class FilmProject:
    schema: str
    project_id: str
    title: str
    style: str
    rating: str
    user_is_adult: bool
    source_rights_approved: bool
    characters: tuple[Character, ...]
    scenes: tuple[Scene, ...]
    fps: int = 24
    width: int = 832
    height: int = 480
    locale: str = "ru"
    narrative_notes: str = ""

def validate(project: FilmProject, *, require_export_ready=False) -> None:
    if not isinstance(project, FilmProject) or project.schema != "NOX_FILM_PROJECT_V1":
        raise Hold("INVALID_FILM_SCHEMA")
    if not PROJECT_ID.fullmatch(project.project_id) or not 1 <= len(project.title) <= 120:
        raise Hold("INVALID_FILM_ID_OR_TITLE")
    if project.style not in STYLES or project.rating not in RATINGS:
        raise Hold("INVALID_FILM_STYLE_OR_RATING")
    if project.style == "adult_anime_18" and (project.rating != "ADULT_18" or
        project.user_is_adult is not True):
        raise Denied("ADULT_ANIMATION_AGE_GATE_REQUIRED")
    if project.rating == "ADULT_18" and project.user_is_adult is not True:
        raise Denied("ADULT_RATING_CONSENT_REQUIRED")
    if project.style == "adult_anime_18" and not project.characters:
        raise Denied("ADULT_CHARACTER_CAST_ATTESTATION_REQUIRED")
    if not project.source_rights_approved:
        raise Denied("FILM_SOURCE_RIGHTS_REQUIRED")
    if project.fps not in (12, 15, 24, 30) or project.width not in (512, 768, 832, 1024, 1280, 1920) or project.height not in (288, 432, 480, 576, 720, 1080):
        raise Hold("FILM_OUTPUT_PROFILE_INVALID")
    if not 0 <= len(project.scenes) <= MAX_SCENES:
        raise Hold("FILM_SHOT_QUOTA")
    if len(project.narrative_notes) > 6000:
        raise Hold("FILM_NOTES_TOO_LONG")
    char_ids = [c.id for c in project.characters]
    if len(char_ids) != len(set(char_ids)) or len(char_ids) > 50:
        raise Hold("FILM_CHARACTER_DUPLICATE_OR_QUOTA")
    for c in project.characters:
        if (not CHARACTER_ID.fullmatch(c.id) or len(c.name) not in range(1, 101)
            or len(c.description) > 1500 or c.owner_rights_approved is not True):
            raise Denied("FILM_CHARACTER_RIGHTS_OR_ID_REQUIRED")
        if c.visual_reference_sha256 and not SHA.fullmatch(c.visual_reference_sha256):
            raise Hold("FILM_CHARACTER_MASTER_HASH_INVALID")
        if project.rating == "ADULT_18":
            # All characters in an adult-rated production need verified adult
            # declarations, not an inferred age from an image or model.
            if c.age is None or c.age < 18 or c.adult_appearance_attested is not True:
                raise Denied("ADULT_PRODUCTION_CHARACTER_NOT_VERIFIED")
    scene_ids = [s.id for s in project.scenes]
    if len(scene_ids) != len(set(scene_ids)):
        raise Hold("DUPLICATE_SCENE_ID")
    if sum(s.seconds for s in project.scenes) > MAX_PROJECT_SECONDS:
        raise Hold("FILM_CHAPTER_DURATION_QUOTA")
    for s in project.scenes:
        if not SHOT_ID.fullmatch(s.id) or not 1 <= len(s.title) <= 120:
            raise Hold("INVALID_SCENE_ID_OR_TITLE")
        if not 1 <= s.seconds <= MAX_SHOT_SECONDS or s.operation not in ("t2v","i2v","v2v","extend"):
            raise Hold("SCENE_DURATION_OR_OPERATION_INVALID")
        if not 1 <= len(s.prompt) <= 3000 or len(s.narration) > 3000 or len(s.dialogue) > 3000:
            raise Hold("SCENE_PROMPT_INVALID")
        if len(s.camera) > 100 or s.provider_id not in VIDEO_PROVIDER_IDS:
            raise Hold("UNKNOWN_VIDEO_PROVIDER")
        if s.operation in ("i2v","v2v") and (not s.reference_sha256 or not SHA.fullmatch(s.reference_sha256)):
            raise Hold("SCENE_REFERENCE_REQUIRED")
        if any(cid not in char_ids for cid in s.character_ids):
            raise Hold("SCENE_MISSING_CHARACTER")
        if s.status not in ("PLANNED", "QUEUED", "RUNNING", "RENDERED", "HOLD", "FAILED"):
            raise Hold("SCENE_STATUS_INVALID")
        if s.status == "RENDERED":
            if not s.output_sha256 or not SHA.fullmatch(s.output_sha256) or not s.output_filename or not FILE.fullmatch(s.output_filename):
                raise Hold("RENDERED_SCENE_OUTPUT_RECEIPT_REQUIRED")
        elif s.output_sha256 or s.output_filename:
            raise Hold("SCENE_UNVERIFIED_OUTPUT")
    if require_export_ready and (not project.scenes or
       any(s.status != "RENDERED" for s in project.scenes)):
        raise Hold("NOT_ALL_SCENES_RENDERED")

# The full 12 upstream names originate from the existing ComfyVideoPort catalog.
VIDEO_PROVIDER_IDS = frozenset({
    "wan21-t2v-1.3b", "wan21-vace-1.3b", "wan22-ti2v-5b",
    "wan22-i2v-a14b", "hunyuan15-t2v", "hunyuan15-i2v",
    "mochi1-preview", "ltxv-2b-distilled", "ltx25-fast",
    "skyreels-v2-i2v-14b", "skyreels-v2-df-14b", "cogvideox-5b"
})

def new_project(project_id: str, title: str, *, style="anime", rating="GENERAL",
                user_is_adult=False, source_rights_approved=False) -> FilmProject:
    p = FilmProject("NOX_FILM_PROJECT_V1", project_id, title, style, rating,
                    user_is_adult, source_rights_approved, (), ())
    validate(p)
    return p

def style_prompt(project: FilmProject, scene: Scene) -> str:
    validate(project)
    cast = [c for c in project.characters if c.id in scene.character_ids]
    return "; ".join([
        scene.prompt,
        "visual style: "+STYLES[project.style],
        "camera: "+scene.camera,
        "consistent approved characters: "+", ".join(c.name for c in cast),
        "stable character appearance; coherent lighting; continuity of motion",
        "no captions burned into footage; export subtitles separately",
        "duration "+str(scene.seconds)+" seconds",
    ]).strip("; ")[:8000]

def storyboard(project: FilmProject) -> list[dict[str, Any]]:
    validate(project)
    elapsed = 0
    result = []
    for s in project.scenes:
        result.append({"sceneId":s.id,"title":s.title,"startSecond":elapsed,
            "endSecond":elapsed+s.seconds,"status":s.status,"operation":s.operation,
            "providerId":s.provider_id,"style":project.style,
            "prompt":style_prompt(project,s)})
        elapsed += s.seconds
    return result

def voice_timeline(project: FilmProject) -> list[dict[str, Any]]:
    """Prepare timed dialogue for existing NOX TTS. Does not fabricate audio."""
    validate(project)
    seconds=0
    tracks=[]
    for s in project.scenes:
        text=(s.dialogue or s.narration).strip()
        if text:
            tracks.append({"sceneId":s.id,"startSecond":seconds,
                           "durationSeconds":s.seconds,"text":text,
                           "status":"VOICE_NOT_GENERATED",
                           "requiredHostRoute":"voice.synthesize"})
        seconds+=s.seconds
    return tracks

def submit_scene(project: FilmProject, scene_id: str, *, port: ComfyVideoPort,
                 workflow: dict, workflow_sha256: str, prompt_node: str,
                 preflight: NativeVideoPreflight, client_id: str,
                 user_authorized: bool, fps: int | None = None) -> dict:
    validate(project)
    s = next((x for x in project.scenes if x.id == scene_id), None)
    if s is None:
        raise Hold("SCENE_NOT_FOUND")
    if s.status not in ("PLANNED","HOLD","FAILED"):
        raise Hold("SCENE_ALREADY_IN_QUEUE")
    if user_authorized is not True:
        raise Denied("FILM_GENERATION_APPROVAL_REQUIRED")
    if not isinstance(port, ComfyVideoPort):
        raise Hold("EXISTING_COMFY_VIDEO_PORT_REQUIRED")
    if s.provider_id != preflight.model_id:
        raise Hold("PRE_FLIGHT_MODEL_MISMATCH")
    frames = min(241, s.seconds * (fps or project.fps) + 1)
    entry = port.prepare_video(model_id=s.provider_id,operation=s.operation,
      workflow=workflow,workflow_digest=workflow_sha256,prompt_node=prompt_node,
      prompt=style_prompt(project,s),client_id=client_id,
      preflight=preflight,user_rights_confirmed=project.source_rights_approved,
      frames=frames,width=project.width,height=project.height)
    queued = port.queue_video(entry,native_authorized=user_authorized)
    return {"status":queued["status"],"promptId":queued["prompt_id"],
        "sceneId":scene_id,"modelId":queued["model_id"],
        "rendered":False}

def receive_scene_output(scene: Scene, *, output_sha256: str, output_filename: str,
                         native_host_verified: bool) -> Scene:
    if not native_host_verified:
        raise Denied("NATIVE_OUTPUT_ATTESTATION_REQUIRED")
    if not SHA.fullmatch(output_sha256 or "") or not FILE.fullmatch(output_filename or "") or ".." in output_filename:
        raise Hold("UNSAFE_OUTPUT_RECEIPT")
    from dataclasses import replace
    return replace(scene,status="RENDERED",output_sha256=output_sha256.lower(),
                   output_filename=output_filename)

def save_project(project: FilmProject, storage_root: Path) -> Path:
    validate(project)
    root = Path(storage_root)
    if root.is_symlink():
        raise Hold("FILM_STORAGE_SYMLINK_DENIED")
    root.mkdir(parents=True,exist_ok=True)
    target = root/(project.project_id+".json")
    if target.is_symlink():
        raise Hold("FILM_PROJECT_SYMLINK_DENIED")
    blob = json.dumps(asdict(project),sort_keys=True,ensure_ascii=False,indent=2)
    if len(blob.encode("utf-8")) > 2_000_000:
        raise Hold("FILM_PROJECT_TOO_LARGE")
    # Atomic replacement inside the approved project store; no arbitrary paths.
    import os
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile("w",encoding="utf-8",dir=root,
                            prefix=".nox-film-",suffix=".tmp",delete=False) as f:
        temp = Path(f.name)
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp,target)
    return target

def load_project(project_id: str, storage_root: Path) -> FilmProject:
    if not PROJECT_ID.fullmatch(project_id):
        raise Hold("INVALID_FILM_ID")
    root = Path(storage_root)
    target = root/(project_id+".json")
    if root.is_symlink() or target.is_symlink() or target.stat().st_size > 2_000_000:
        raise Hold("FILM_PROJECT_UNTRUSTED")
    d = json.loads(target.read_text(encoding="utf-8"))
    chars = tuple(Character(**c) for c in d["characters"])
    scenes = tuple(Scene(**{**s,"character_ids":tuple(s.get("character_ids",[]))}) for s in d["scenes"])
    project = FilmProject(**{**d,"characters":chars,"scenes":scenes})
    validate(project)
    return project

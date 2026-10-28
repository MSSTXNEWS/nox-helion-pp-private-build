"""Existing-NOX-LLM story writer for Film Studio: one human brief -> structured shot plan.
No second language-model host. No hypothetical "generated film" success.
"""
from __future__ import annotations
from dataclasses import replace
from typing import Protocol
import json
import re

from film_studio import (FilmProject, Scene, Hold, Denied, VIDEO_PROVIDER_IDS,
                         validate, STYLES)

class NativeScreenwriter(Protocol):
    def draft_film(self, prompt: str, *, max_output_chars: int) -> str: ...

def screenplay_prompt(project: FilmProject, idea: str, *, target_seconds: int = 90,
                      max_scenes: int = 24) -> str:
    validate(project)
    if not isinstance(idea,str) or not idea.strip() or len(idea)>2500 or "\0" in idea:
        raise Hold("INVALID_FILM_IDEA")
    if not isinstance(target_seconds,int) or target_seconds < 3 or target_seconds > 1200:
        raise Hold("INVALID_FILM_TARGET_DURATION")
    if not isinstance(max_scenes,int) or max_scenes < 1 or max_scenes > 48:
        raise Hold("INVALID_STORYBOARD_QUOTA")
    if project.style == "adult_anime_18" and project.rating != "ADULT_18":
        raise Denied("ADULT_STORYBOARD_GATING_REQUIRED")
    cast = ", ".join(c.id + ": " + c.name + " — " + c.description[:150]
                      for c in project.characters) or "нет персонажей"
    # LLM output is untrusted input. Host must validate against this strict schema.
    return (
      "Ты сценарист локального NOX HELION. Напиши оригинальную раскадровку по идее пользователя.\n"
      "Верни ТОЛЬКО валидный JSON-объект, без markdown и постороннего текста.\n"
      "Формат: {\"scenes\":[{\"title\":\"...\",\"prompt\":\"...\","
      "\"seconds\":6,\"dialogue\":\"...\",\"camera\":\"...\","
      "\"characterIds\":[\"...\"]}]}.\n"
      "Требования: до "+str(max_scenes)+" сцен, каждая от 1 до 20 секунд; общая длительность "
      "не более "+str(target_seconds)+" секунд. Сцены должны логично продолжать друг друга, "
      "сохранять утверждённую внешность персонажей. Используй только разрешённые CharacterID.\n"
      "Жанр: "+STYLES[project.style]+"; возрастная категория "+project.rating+".\n"
      "При 18+ допустимы только проверенные совершеннолетние персонажи; никаких несовершеннолетних "
      "в сексуализированных сценах, без имитации существующих защищённых произведений.\n"
      "Утверждённые персонажи: "+cast+"\n"
      "Сюжет: "+idea.strip()+"\n"
    )

def parse_storyboard_response(raw: str, project: FilmProject, *,
                              max_scenes=24, target_seconds=90,
                              provider_id="wan21-t2v-1.3b") -> FilmProject:
    validate(project)
    if not isinstance(raw,str) or len(raw)>80_000 or not raw.strip().startswith("{"):
        raise Hold("SCREENWRITER_JSON_REQUIRED")
    if provider_id not in VIDEO_PROVIDER_IDS:
        raise Hold("UNKNOWN_VIDEO_PROVIDER")
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise Hold("SCREENWRITER_JSON_INVALID") from exc
    if not isinstance(doc,dict) or set(doc)!={"scenes"} or not isinstance(doc["scenes"],list):
        raise Hold("SCREENWRITER_STRUCTURE_INVALID")
    if not 1<=len(doc["scenes"])<=max_scenes:
        raise Hold("SCREENWRITER_SCENE_COUNT_INVALID")
    allowed_cast = {c.id for c in project.characters}
    prepared=[]
    total=0
    for i,row in enumerate(doc["scenes"],1):
        if not isinstance(row,dict) or set(row)-{"title","prompt","seconds","dialogue","camera","characterIds"}:
            raise Hold("SCREENWRITER_UNEXPECTED_FIELD")
        title=row.get("title")
        prompt=row.get("prompt")
        seconds=row.get("seconds")
        if (not isinstance(title,str) or not 1<=len(title)<=120 or
            not isinstance(prompt,str) or not 1<=len(prompt)<=3000 or
            isinstance(seconds,bool) or not isinstance(seconds,int) or not 1<=seconds<=20):
            raise Hold("SCREENWRITER_SCENE_INVALID")
        chars=row.get("characterIds",[])
        if (not isinstance(chars,list) or len(chars)>12 or
            any(not isinstance(c,str) or c not in allowed_cast for c in chars)):
            raise Hold("SCREENWRITER_UNAPPROVED_CHARACTER")
        dlg=row.get("dialogue","")
        cam=row.get("camera","cinematic")
        if not isinstance(dlg,str) or len(dlg)>3000 or not isinstance(cam,str) or len(cam)>100:
            raise Hold("SCREENWRITER_DIALOGUE_INVALID")
        total+=seconds
        if total>target_seconds:
            raise Hold("SCREENWRITER_DURATION_EXCEEDED")
        # Never accept a model-supplied status, checkpoint path or generated output.
        prepared.append(Scene(id=f"s-draft-{i:03}",title=title,prompt=prompt,seconds=seconds,
            provider_id=provider_id,dialogue=dlg,camera=cam,character_ids=tuple(chars)))
    # Storyboard is planned, never "rendered" based on LLM output.
    result=replace(project,scenes=tuple(prepared))
    validate(result)
    return result

def draft_from_existing_nox_ai(project: FilmProject, idea: str, *,
                               native_host: NativeScreenwriter,
                               user_approved: bool,
                               max_scenes=24,target_seconds=90) -> FilmProject:
    if user_approved is not True:
        raise Denied("AI_SCREENWRITER_REQUIRES_USER_APPROVAL")
    if native_host is None or not callable(getattr(native_host,"draft_film",None)):
        raise Hold("EXISTING_NOX_LLM_NOT_CONNECTED")
    request=screenplay_prompt(project,idea,max_scenes=max_scenes,
                              target_seconds=target_seconds)
    raw=native_host.draft_film(request,max_output_chars=80_000)
    return parse_storyboard_response(raw,project,max_scenes=max_scenes,
                                    target_seconds=target_seconds)

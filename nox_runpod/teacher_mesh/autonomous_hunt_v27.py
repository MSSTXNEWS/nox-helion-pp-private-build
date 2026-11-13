#!/usr/bin/env python3
"""NOX HUNT V27: permissioned self-directed research and REAL trainer handoff.

Attach to the EXISTING OneHost boot/idle tick. No new daemon, database, model,
endpoint, GPU command, or auto-merge. 'Worms' are inexpensive virtual tasks,
not 20 LLMs or OS processes. Existing WormAutopilot/WormSwarm stay authoritative.

The NATIVE HOST supplies authenticated/verified callbacks. This module cannot
reach a local GPU from GitHub or fake an optimizer receipt. All side effects
are guarded by owner-pinned policy, current native STOP, existing queue quotas,
hardware/cost constraints, and current source SHA.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Callable, Any
import json
import math
import re

SCHEMA = "nox-hunt-v27-source-only"
LANES = ("core_forge","memory","soul","reasoning","tools","integration_qa")
WORM_KINDS = (
    "native_boot","autopilot","research_swarm","idea_loop",
    "initiative_bridge","forge_candidate","predator_hunt",
    "github_code","approved_feed","youtube_metadata","package_registry",
    "ollama_registry","gitlab_metadata","crawl4ai","trafilatura",
    "isolated_browser","restricted_social_api","huggingface_teacher",
    "local_scanner","local_intake",
)
assert len(WORM_KINDS) == 20 and len(set(WORM_KINDS)) == 20
# Provider wishes are never permissions. These need a separate host capability
# and native policy; an arbitrary model cannot author a new executable plugin.
HEAVY_OR_RESTRICTED = frozenset(("isolated_browser","restricted_social_api"))
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
REV_RE = re.compile(r"^[a-f0-9]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9._/-]{3,150}$")
SCOPE_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
LICENSE_RE = re.compile(r"^[A-Za-z0-9._+-]{2,50}$")

@dataclass(frozen=True)
class NativeCallbacks:
    signed_policy: Callable[[str], dict]
    native_stop: Callable[[], bool]
    source_head: Callable[[], str]
    owner_state: Callable[[str], dict]
    quota_claim: Callable[[str, str, str], bool]
    enqueue_existing: Callable[[str, dict], bool]
    existing_worm_tick: Callable[[str], dict]
    propose_nox_idea: Callable[[str, dict], dict]
    model_candidate: Callable[[str], dict | None]
    stage_model_existing: Callable[[str, dict], dict]
    train_candidate: Callable[[str], dict | None]
    launch_existing_trainer: Callable[[str, dict], dict]

class HuntDirector:
    def __init__(self, callbacks: NativeCallbacks):
        self.c = callbacks
        # Prevent in-process duplicate side effects. Durable quota/idempotency
        # belongs to existing native OneHost via quota_claim, not Python memory.
        self._booted_scope = None

    @staticmethod
    def _hold(reason, **other):
        return {"schema":SCHEMA,"state":"HOLD","reason":reason,
                "training_weight_updates_verified":0,"worms_are_os_processes":False,
                **other}

    def _stop_ok(self):
        try:return self.c.native_stop() is False
        except Exception:return False

    def _policy(self, scope:str, now:datetime):
        if not SCOPE_RE.fullmatch(scope or ""):
            return None,"INVALID_SCOPE"
        if not self._stop_ok():return None,"NATIVE_STOP_UNAVAILABLE_OR_ACTIVE"
        try:
            policy=self.c.signed_policy(scope)
            head=self.c.source_head()
        except Exception:return None,"POLICY_OR_HEAD_UNAVAILABLE"
        if (not isinstance(policy,dict) or policy.get("signed_by_native_owner") is not True
                or policy.get("scope")!=scope or policy.get("allow_autonomous_research") is not True):
            return None,"OWNER_SIGNED_AUTONOMY_POLICY_REQUIRED"
        if not isinstance(head,str) or not REV_RE.fullmatch(head):
            return None,"SOURCE_HEAD_NOT_VERIFIED"
        if policy.get("source_head")!=head:
            return None,"POLICY_SOURCE_HEAD_CHANGED"
        try:
            expiry=datetime.fromisoformat(policy["expires_utc"].replace("Z","+00:00"))
        except (KeyError,TypeError,ValueError,AttributeError):return None,"POLICY_EXPIRY_REQUIRED"
        if expiry.tzinfo is None or expiry<=now:return None,"POLICY_EXPIRED"
        return policy,None

    def _state(self, scope):
        try:data=self.c.owner_state(scope)
        except Exception:return None
        if not isinstance(data,dict) or data.get("origin")!="existing_onehost" or data.get("scope")!=scope:
            return None
        return data

    @staticmethod
    def hunger(last_verified_learning_utc, *, now:datetime, gap_score:float)->dict:
        """Purposeful scarcity metric, not emotional suffering or literal hunger."""
        try:
            if isinstance(gap_score,bool):raise ValueError()
            gap=float(gap_score)
            if not math.isfinite(gap) or not 0<=gap<=1:raise ValueError()
        except (TypeError,ValueError):
            return {"level":"HOLD_GAP_EVIDENCE","score":None}
        if not isinstance(last_verified_learning_utc,str):
            return {"level":"HOLD_LAST_VERIFIED_EVENT","score":None}
        try:
            ts=datetime.fromisoformat(last_verified_learning_utc.replace("Z","+00:00"))
            if ts.tzinfo is None or ts>now:raise ValueError()
            hours=(now-ts).total_seconds()/3600
        except (TypeError,ValueError):
            return {"level":"HOLD_LAST_VERIFIED_EVENT","score":None}
        # Highest activity for *measured gap*, never for time alone.
        score=round(0.75*gap+0.25*min(hours/168,1),4)
        level=("FED" if hours<1 else
               "HUNGRY" if hours<24 else
               "VERY_HUNGRY" if hours<168 else "STARVING")
        return {"level":level,"score":score,"hours_since_verified_learning":round(hours,2),
                "literal_emotion":False}

    def _guard_side_effect(self, scope, policy):
        if not self._stop_ok():return False
        try:
            head=self.c.source_head()
            current=self.c.signed_policy(scope)
            return head==policy["source_head"] and current==policy
        except Exception:return False

    def _claim(self, scope, action, key, policy):
        if not self._guard_side_effect(scope,policy):return False
        try:return self.c.quota_claim(scope,action,key) is True
        except Exception:return False

    @staticmethod
    def _valid_idea(raw):
        if not isinstance(raw,dict):return False
        kind,topic,lane=raw.get("worm_kind"),raw.get("topic"),raw.get("lane")
        return (kind in WORM_KINDS and kind not in HEAVY_OR_RESTRICTED
                and lane in LANES and isinstance(topic,str)
                and 5<=len(topic)<=160 and "\n" not in topic and "\r" not in topic
                and isinstance(raw.get("source_uri"),str)
                and raw["source_uri"].startswith(("s03://","github://","https://"))
                and len(raw["source_uri"])<=500
                and raw.get("execute_code") is not True)

    def tick(self, scope:str, *, now:datetime | None=None)->dict:
        """The EXISTING OneHost calls this on idle ticks. At most 1 new task/tick.

        Separate operations are low-frequency and deduped via native quota_claim;
        startup, wake or offline mode never runs trainer without device proof.
        """
        now=now or datetime.now(timezone.utc)
        if now.tzinfo is None:return self._hold("UTC_CLOCK_REQUIRED")
        policy,why=self._policy(scope,now)
        if why:return self._hold(why)
        state=self._state(scope)
        if state is None:return self._hold("EXISTING_ONEHOST_STATE_REQUIRED")
        if state.get("chat_busy") is True:
            return {"schema":SCHEMA,"state":"CHAT_PRIORITY_IDLE_DEFER",
                    "training_weight_updates_verified":0,"worms_are_os_processes":False}
        knowledge=self.hunger(state.get("last_verified_learning_utc"),now=now,
                              gap_score=state.get("verified_gap_score"))
        if knowledge["score"] is None:return self._hold("HUNGER_INPUTS_UNVERIFIED")
        # Reuse the real WormAutopilot and WormSwarm. No clone.
        try:w=self.c.existing_worm_tick(scope)
        except Exception:w={"state":"HOLD_EXISTING_WORMS_UNAVAILABLE"}
        if not self._guard_side_effect(scope,policy):
            return self._hold("NATIVE_STOP_OR_POLICY_REVOKED_AFTER_WORMS")
        response={"schema":SCHEMA,"state":"OBSERVING","hunger":knowledge,
                  "lane_count":6,"virtual_worm_types":20,"existing_worms":w,
                  "training_weight_updates_verified":0,"worms_are_os_processes":False}
        if knowledge["score"]<0.22:
            return response
        # Existing NOX proposes a *data-only* worm task, not executable source.
        try:idea=self.c.propose_nox_idea(scope,{"hunger":knowledge,"lanes":LANES,
                                                "worm_kinds":WORM_KINDS})
        except Exception:idea=None
        if self._valid_idea(idea) and self._claim(scope,"worm_create",sha256(
                json.dumps(idea,sort_keys=True).encode()).hexdigest(),policy):
            if not self._guard_side_effect(scope,policy):return self._hold("STOP_BEFORE_WORM")
            try:queued=self.c.enqueue_existing(scope,{"type":"existing_worm_research",
                "kind":idea["worm_kind"],"lane":idea["lane"],
                "topic":idea["topic"],"source_uri":idea["source_uri"],
                "requires_existing_owner_acl":True,"source_head":policy["source_head"]})
            except Exception:queued=False
            if queued is True:
                response["worm_created"]="EXISTING_QUEUE_ACCEPTED_DATA_ONLY"
        # Model acquisition and weights training: separate native operations,
        # require a time-limited explicitly owner-signed grant, source rights,
        # verified device and bounded hardware/cost budget.
        gpu=state.get("gpu")
        if not isinstance(gpu,dict):
            response["gpu"]="HOLD_NO_VERIFIED_DEVICE"
            return response
        if state.get("trainer_running") is True or gpu.get("chat_gpu_busy") is True:
            response["gpu"]="BUSY_NO_CONCURRENT_TRAINER"
            return response
        if gpu.get("telemetry_verified") is not True or gpu.get("gpu_owner")!="NOX":
            response["gpu"]="HOLD_DEVICE_OWNERSHIP_OR_TELEMETRY"
            return response
        if gpu.get("local_windows_gpu") is True:
            if (gpu.get("hotspot_valid") is not True or gpu.get("power_sensor_valid") is not True
                    or type(gpu.get("samples_hotspot_ge70")) is not int
                    or gpu["samples_hotspot_ge70"]>=3 or
                    gpu.get("safe70_active") is not True):
                response["gpu"]="HOLD_SAFE70_SENSOR_OR_THERMAL"
                return response
        if (type(gpu.get("free_disk_gb")) not in (int,float)
                or gpu["free_disk_gb"]<policy.get("min_free_disk_gb",25)
                or type(gpu.get("free_vram_mb")) not in (int,float)
                or gpu["free_vram_mb"]<policy.get("min_free_vram_mb",2048)):
            response["gpu"]="HOLD_DISK_OR_VRAM_BUDGET"
            return response
        if policy.get("allow_autonomous_model_download") is True:
            try:candidate=self.c.model_candidate(scope)
            except Exception:candidate=None
            if isinstance(candidate,dict) and self._eligible_model(candidate,policy):
                key="model-"+candidate["model_id"]+"@"+candidate["revision"]
                if self._claim(scope,"model_download",key,policy):
                    if not self._guard_side_effect(scope,policy):return self._hold("STOP_BEFORE_MODEL_DOWNLOAD")
                    try:download=self.c.stage_model_existing(scope,dict(candidate,staging_only=True))
                    except Exception:download=None
                    response["model_download"]=(
                        "VERIFIED_STAGING_ONLY" if isinstance(download,dict)
                        and download.get("sha256_verified") is True
                        and isinstance(download.get("bytes"),int)
                        and 0<download["bytes"]<=candidate["max_bytes"] and
                        isinstance(download.get("sha256"),str)
                        and SHA_RE.fullmatch(download["sha256"]) and
                        self._guard_side_effect(scope,policy)
                        else "HOLD_DOWNLOAD_NOT_VERIFIED")
        # A model download alone is NOT learning. Only call the installed
        # trainer if a separate vetted training dataset & holdout exist.
        if policy.get("allow_autonomous_gpu_training") is True:
            try:train=self.c.train_candidate(scope)
            except Exception:train=None
            if isinstance(train,dict) and self._eligible_train(train,state,policy):
                key="train-"+train["dataset_sha256"]+"@"+train["student_sha256"]
                if self._claim(scope,"gpu_train",key,policy):
                    if not self._guard_side_effect(scope,policy):return self._hold("STOP_BEFORE_TRAIN")
                    try:started=self.c.launch_existing_trainer(scope,dict(train,
                        staging_only=True,no_auto_promotion=True,fail_closed_stop=True))
                    except Exception:started=None
                    response["gpu_train"]=(
                        "EXISTING_TRAINER_JOB_ACCEPTED_NOT_OPTIMIZER_VERIFIED"
                        if isinstance(started,dict)
                        and started.get("accepted_by_existing_trainer") is True
                        and isinstance(started.get("job_id"),str) and len(started["job_id"])>=8
                        and self._guard_side_effect(scope,policy)
                        else "HOLD_TRAINER_NOT_ACCEPTED_OR_REVOKED")
        return response

    @staticmethod
    def _eligible_model(candidate,policy):
        return (candidate.get("type")=="frozen_teacher"
           and isinstance(candidate.get("model_id"),str)
           and bool(ID_RE.fullmatch(candidate["model_id"]))
           and candidate["model_id"] in policy.get("allowed_model_ids",[])
           and isinstance(candidate.get("revision"),str)
           and bool(REV_RE.fullmatch(candidate["revision"]))
           and candidate.get("license_verified_by_owner") is True
           and candidate.get("training_rights_verified") is True
           and bool(LICENSE_RE.fullmatch(candidate.get("license_id","")))
           and type(candidate.get("max_bytes")) is int
           and 1000<=candidate["max_bytes"]<=policy.get("max_model_bytes",8_000_000_000)
           and candidate.get("source_origin")=="trusted_model_registry")
    @staticmethod
    def _eligible_train(train,state,policy):
        return (train.get("training_rights_verified") is True
            and train.get("holdout_independent") is True
            and train.get("dataset_reviewed") is True
            and train.get("mode") in ("student_sft","student_preference_distillation")
            and isinstance(train.get("student_sha256"),str)
            and bool(SHA_RE.fullmatch(train["student_sha256"]))
            and train["student_sha256"]==state.get("active_student_sha256")
            and isinstance(train.get("dataset_sha256"),str)
            and bool(SHA_RE.fullmatch(train["dataset_sha256"]))
            and type(train.get("optimizer_steps_budget")) is int
            and 1<=train["optimizer_steps_budget"]<=policy.get("max_optimizer_steps_per_job",100))

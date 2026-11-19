#!/usr/bin/env python3
"""NOX Emotional Resonance V28 — calibrated style policy, no emotions fabricated.

The same NOX model produces speech. This module never generates a persona,
diagnoses a human or claims that the model has internal feelings. The approved
owner's S03 tone preferences take precedence over untrusted classifier output.
"""
from __future__ import annotations
from math import isfinite
SCHEMA="nox-emotional-resonance-v28"
LABELS=frozenset(("joy","sadness","fear","anger","surprise","interest","neutral","uncertain","disgust","shame"))
TONES=frozenset(("neutral","warm","calm","professional","concise"))
LANGUAGES=frozenset(("ru","es","en"))
def tone_plan(*,language:str,observation:dict|None,owner_s03_preference:dict|None,policy:dict)->dict:
    if not isinstance(policy,dict) or policy.get("scope_authorized") is not True:
        return {"schema":SCHEMA,"state":"HOLD_UNAUTHENTICATED_S03_SCOPE","tone":"neutral"}
    if language not in LANGUAGES:
        return {"schema":SCHEMA,"state":"HOLD_LANGUAGE_UNSUPPORTED","tone":"neutral"}
    if policy.get("native_stop") is not False:
        return {"schema":SCHEMA,"state":"HOLD_STOP","tone":"neutral"}
    prefs=owner_s03_preference
    tone="neutral"
    if (isinstance(prefs,dict) and prefs.get("owner_approved") is True and
        prefs.get("scope")==policy.get("scope") and
        prefs.get("tone") in TONES):
        tone=prefs["tone"]
    label="uncertain";confidence=0.0
    if isinstance(observation,dict) and observation.get("state")=="OBSERVED_TONE_NOT_DIAGNOSIS":
        v=observation.get("confidence")
        if (observation.get("label") in LABELS and type(v) in (float,int)
                and isfinite(v) and .65<=v<=1):
            label=observation["label"];confidence=round(v,3)
    # Tone observation can adjust a stylistic *suggestion*, never user facts.
    if tone=="neutral" and label in ("fear","sadness","shame","anger"):
        tone="calm"
    elif tone=="neutral" and label in ("joy","interest") and confidence>=.8:
        tone="warm"
    return {
        "schema":SCHEMA,"state":"STYLE_SUGGESTION_NOT_FEELING",
        "visible_model":"ONE_NOX_STUDENT_ONLY",
        "language":language,"tone":tone,
        "affect_label_observed":label,"affect_confidence":confidence,
        "voice_rate_min":0.88 if tone=="calm" else 0.96,
        "voice_rate_max":1.05,
        "no_psychological_diagnosis":True,
        "subjective_consciousness_claim":False,
        "neural_training_from_user_message":False,
        "do_not_log_sensitive_inferences":True,
        "owner_preference_used":isinstance(prefs,dict) and
            prefs.get("owner_approved") is True and
            prefs.get("scope")==policy.get("scope") and
            prefs.get("tone") in TONES
    }

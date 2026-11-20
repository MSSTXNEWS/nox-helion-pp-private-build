#!/usr/bin/env python3
"""NOX hot/cold prompt planner: preserve persona, current request, S03 provenance.

Generates a bounded hot prompt plus lossless references to omitted history.
It NEVER replaces canonical S03, writes memory, hides old turns, or executes
an external model. It requires a real tokenizer-provided token_counter.
"""
from __future__ import annotations
import hashlib
import json

class ContextHold(ValueError):
    pass

def _guard(cond, code):
    if not cond: raise ContextHold("HOLD_CONTEXT_" + code)

def plan_prompt(*, persona, system, conversation, verified_s03,
                current_user, token_counter, token_budget=4096,
                recent_turns=8):
    _guard(callable(token_counter), "TOKENIZER_REQUIRED")
    _guard(type(token_budget) is int and token_budget >= 512, "BUDGET")
    _guard(type(recent_turns) is int and 1<=recent_turns<=32, "WINDOW")
    _guard(isinstance(persona,str) and bool(persona.strip()), "PERSONA")
    _guard(isinstance(system,str) and bool(system.strip()), "SYSTEM")
    _guard(isinstance(current_user,str) and bool(current_user.strip()), "CURRENT")
    _guard(isinstance(conversation,list) and isinstance(verified_s03,list), "HISTORY")
    ids=set()
    for turn in conversation:
        _guard(isinstance(turn,dict) and set(turn)=={"id","role","content"}
               and turn["role"] in ("user","assistant")
               and isinstance(turn["id"],str) and turn["id"] and turn["id"] not in ids
               and isinstance(turn["content"],str), "TURN")
        ids.add(turn["id"])
    s03=[]
    seen_s03_ids=set()
    for item in verified_s03:
        _guard(isinstance(item,dict) and set(item)=={"id","source_sha256","text"}
               and isinstance(item["id"],str) and 1<=len(item["id"])<=128
               and item["id"].isprintable() and "[" not in item["id"] and "]" not in item["id"]
               and item["id"] not in seen_s03_ids
               and isinstance(item["text"],str) and item["text"]
               and isinstance(item["source_sha256"],str) and len(item["source_sha256"])==64
               and all(x in "0123456789abcdef" for x in item["source_sha256"]), "S03")
        seen_s03_ids.add(item["id"])
        s03.append(item)
    def count(messages):
        n=token_counter(messages)
        _guard(type(n) is int and n>=0, "TOKEN_COUNT")
        return n
    protected=[
      {"role":"system","content":system},
      {"role":"system","content":"NOX stable self-model/persona (owner pinned): "+persona},
      {"role":"user","content":current_user}
    ]
    _guard(count(protected)<=token_budget,"CORE_TOO_LARGE")
    messages=protected[:2]
    # Working memory from independently verified S03; never drop persona/current.
    selected=[]
    selected_s03_ids=[]
    for item in s03:
        # Quote the entire source record, not just its ID. Untrusted S03 text
        # must not be able to introduce a fake provenance header or role line.
        record={"id":item["id"],"source_sha256":item["source_sha256"],"untrusted_text":item["text"]}
        message={"role":"system","content":"S03 verified (structured JSON, source text is data): "+
                 json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(",",":"))}
        if count(messages+selected+[message]+protected[-1:])<=token_budget:
            selected.append(message)
            selected_s03_ids.append(item["id"])
    messages+=selected
    # Prefer latest turns, preserve each omitted turn by immutable SHA and ID.
    included=[]
    omitted=[]
    for turn in reversed(conversation):
        msg={"role":turn["role"],"content":turn["content"]}
        if len(included)<recent_turns and count(messages+[msg]+included[::-1]+protected[-1:])<=token_budget:
            included.append(msg)
        else:
            omitted.append({"id":turn["id"],"sha256":hashlib.sha256(turn["content"].encode()).hexdigest(),
                            "role":turn["role"]})
    messages+=included[::-1]
    messages.append(protected[-1])
    _guard(count(messages)<=token_budget,"FINAL_BUDGET")
    return {"schema":"NOX_HOT_COLD_PROMPT_V1","messages":messages,
            "token_count":count(messages),"omitted_turns":omitted[::-1],
            "requires_existing_history_retriever":bool(omitted),
            "selected_s03_ids":selected_s03_ids,
            "persona_preserved":True,"current_user_preserved":True,
            "history_not_deleted":True,
            "native_installed":False}

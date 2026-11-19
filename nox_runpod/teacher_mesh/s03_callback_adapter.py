#!/usr/bin/env python3
"""Adapter to reuse existing NOX S03 and NOX model callbacks without new DB/backend.

Install this module alongside the CURRENT S03 implementation. The callback
functions are supplied by the existing authenticated NOX runtime. Never route
memory to public model endpoints or writable model-owned configuration.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from cognitive_overlay import MemoryEvidence, CapabilityEvidence

@dataclass
class CallbackS03Adapter:
    search_fn: Callable
    capabilities_fn: Callable
    append_fn: Callable

    def search(self,*,query:str,scope:str,limit:int)->list[MemoryEvidence]:
        rows=self.search_fn(query=query,scope=scope,limit=min(60,max(1,limit)))
        if not isinstance(rows,list):
            raise TypeError("S03 search did not return a list")
        result=[]
        for row in rows[:60]:
            if isinstance(row,MemoryEvidence):
                result.append(row)
                continue
            if not isinstance(row,dict):continue
            try:
                result.append(MemoryEvidence(
                    id=str(row["id"]),
                    content=str(row["content"]),
                    segment=str(row["segment"]),
                    source_uri=str(row["source_uri"]),
                    timestamp_utc=str(row["timestamp_utc"]),
                    importance=float(row.get("importance",0.5)),
                    verified=row.get("verified") is True,
                    superseded=row.get("superseded") is True,
                    scope=str(row.get("scope","")),
                    source_kind=str(row.get("source_kind","event"))
                ))
            except (KeyError,ValueError,TypeError):continue
        return result

    def capabilities(self,*,scope:str)->list[CapabilityEvidence]:
        records=self.capabilities_fn(scope=scope)
        if not isinstance(records,list):
            raise TypeError("S03 capabilities did not return a list")
        results=[]
        for row in records[:60]:
            if isinstance(row,CapabilityEvidence):
                results.append(row);continue
            if not isinstance(row,dict):continue
            try:
                results.append(CapabilityEvidence(
                    id=str(row["id"]),capability=str(row["capability"]),
                    state=str(row["state"]),evidence_uri=str(row["evidence_uri"]),
                    timestamp_utc=str(row["timestamp_utc"]),
                    verified=row.get("verified") is True))
            except (KeyError,ValueError,TypeError):continue
        return results

    def append_approved(self,*,scope:str,event:dict)->str:
        receipt=self.append_fn(scope=scope,event=event)
        if not isinstance(receipt,str):raise TypeError("S03 did not verify receipt")
        return receipt

@dataclass
class CallbackNOXModelAdapter:
    generate_fn:Callable
    def generate(self,prompt:str,context:dict)->str:
        return self.generate_fn(prompt=prompt,context=context)

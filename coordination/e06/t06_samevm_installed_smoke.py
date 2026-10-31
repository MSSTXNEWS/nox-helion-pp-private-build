"""NOX HELION T06 Â· Same-VM installed candidate smoke, NOT independent E07.

Reuse original P01 NSIS silently on a disposable Windows GitLab runner.
No second VM, no download of artifacts or app assets, no source rewrite,
no paid service, and no changes to a pre-existing installed NOX.

The only route exercised is real model inventory over authenticated framed P02
IPC. Actual WPF GUI, Ollama chat/STOP, model downloads and E07 remain HOLD.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/"work/e06/onehost-r66"
BUILD=OUTPUT
CANDIDATE=BUILD/"ONEHOST_DIAGNOSTIC_RECEIPT.json"
SETUP=BUILD/"NOX-HELION-V16-DIAGNOSTIC-SETUP.exe"
PAYLOAD=BUILD/"payload"
NATIVE_ROOT=ROOT/"work/t06-manual-source-inspect/python-exe-candidate"
NATIVE_PROOF=ROOT/"work/e06/NATIVE_ONEHOST_SMOKE.json"
NSIS_PROOF=OUTPUT/"T06_INSTALLED_SMOKE.json"

def require(condition:bool,code:str)->None:
    if not condition: raise RuntimeError(code)

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def regular(path:Path)->bool:
    return path.is_file() and not path.is_symlink() and (
        not getattr(path,"is_junction",lambda:False)())

def plain_parents(path:Path,base:Path)->bool:
    try:
        c¶»§q«^
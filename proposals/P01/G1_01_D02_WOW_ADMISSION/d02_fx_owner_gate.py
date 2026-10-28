"""NOX V16 / E01 source-only WOW owner-boundary admission.

Read-only static evidence for an optional overlay, NOT a scene installer or a
replacement for E06 sealed 729-member SourceLock or Windows WebView2 QA.
"""
from __future__ import annotations

import re
from typing import Any

BASE_COMMIT = '0b3a7d435be735148d64171deb9027093a89646e'
BASE_TREE = 'f108d604c444f718b32aaecfd07b90b8f91b9a6f'


def _source(js: str) -> str:
    # Ignore comments; the test is intentionally conservative about strings.
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', js, flags=re.S)


def audit(js: Any, *, commit: str, tree: str,
          changed_paths: list[str] | None = None) -> dict[str, str]:
    """Ten fail-closed SOURCE gates. PASS never means integrated/installed."""
    s = _source(js) if isinstance(js, str) else ''
    c = re.sub(r'\s+', '', s)
    out: dict[str, str] = {}

    def gate(n: int, ok: bool) -> None:
        out[f'E01-R04-{n:02d}'] = 'SOURCE_CHECK_PASS' if ok else 'HOLD'

    gate(1, commit == BASE_COMMIT and tree == BASE_TREE)
    gate(2, bool(s) and 'export function installNoxCinemaFX' in s
         and 'validateScene(orbs);' in s)
    gate(3, ('orbs.length!==CORE_COUNT+1' in c and
             'newSet(ids).size!==CORE_COUNT+1' in c and
             'newSet(orbs.map(x=>x.element)).size!==CORE_COUNT+1' in c))

    # Never mutate host-owned runtime state (read access alone is allowed).
    native_dataset_write = re.search(
        r'(?:\.dataset\s*(?:\.noxState|\[\s*[\x27\x22]noxState[\x27\x22]\s*\])\s*(?:=(?!=)|\+\+|--|\+=|-=)|'
        r'delete\s+[^;\n]*\.dataset\s*(?:\.noxState|\[\s*[\x27\x22]noxState[\x27\x22]\s*\])|'
        r'\.(?:setAttribute|removeAttribute|toggleAttribute)\s*\(\s*[\x27\x22]data-nox-state[\x27\x22])',
        s)
    gate(4, not native_dataset_write and '.dataset.noxFxState' in s)
    gate(5, ('event.trusted!==true' in c and
             'pendingHostEvents.length<16' in c and
             'eventsReady=true' in c and
             'hostEvents.subscribe(applyHostEvent)' in c))
    gate(6, ('mounted.set(root,true)' in c and 'mounted.delete(root)' in c and
             'try{if(unsubscribe)unsubscribe();}catch(error)' in c and
             'deleteorb.element.dataset.noxFxState' in c and
             'deleteroot.dataset.noxFxState' in c))
    gate(7, ('!disposed&&!doc.hidden&&hostVisible&&intersectVisible' in c and
             'if(!isActive())return;' in c and
             'intersectVisible=items.some(x=>x.isIntersecting)' in c))
    gate(8, ('prefers-reduced-motion:reduce' in c and
             'if(preference)sleep();' in c and
             'particleCount>=policy.maxParticles' in c))
    gate(9, ('Math.sin(Math.PI*t)' in c and
             'done:t>=1' in c and 'radius=p.surfaceRadius+arc*p.reach' in c and
             'if(position.done)' in c))
    paths = changed_paths if isinstance(changed_paths, list) else []
    gate(10, bool(paths) and all(
        isinstance(p, str) and p.startswith('proposals/P01/G1_01_D02_WOW_ADMISSION/')
        and '..' not in p.split('/') and '\\' not in p
        and not p.lower().endswith(('.exe', '.zip', '.dll'))
        for p in paths))
    return out


def verdict(js: Any, *, commit: str, tree: str,
            changed_paths: list[str] | None = None) -> dict[str, Any]:
    checks = audit(js, commit=commit, tree=tree, changed_paths=changed_paths)
    return {
        'task_ledger': checks,
        'source_candidate': ('COMPONENT_SOURCE_GATE_PASS'
                             if all(x == 'SOURCE_CHECK_PASS' for x in checks.values())
                             else 'HOLD'),
        'source_lock_729': 'HOLD',
        'integrated': 'HOLD',
        'windows_accepted': 'NOT_RUN',
        'weighted_progress': 'N/D',
    }

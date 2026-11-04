"""Add five accessible EXPRESS primary actions to an immutable R11 HOME copy.

The original HOME, host, menu and backend are never rewritten. Caller stages
only a disposable NSIS payload and verifies the published digest separately.
No synthetic install/model/training ACKs or permission changes are permitted.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ORIGINAL_BYTES = 94908
ORIGINAL_SHA256 = "b57d58bb001c9826feb3bf7ff19510d047c7ec2926ee8b703538dfca886a960b"
MARKER = 'id="nox-express-primary"'

# Original controls are invoked only by a real user click. Unknown routes HOLD.
# MODELS delegates to the already installed original WPF bridge, which enforces
# native SID/ACL/consent and may legitimately return HOLD if offline.
INSERT = r'''<!-- NOX EXPRESS 5 original-home primary actions; no additional host -->
<style id="nox-express-primary-style">
#nox-express-primary{position:fixed;left:50%;bottom:12px;transform:translateX(-50%);z-index:990;display:flex;gap:7px;max-width:calc(100vw - 20px);width:max-content;flex-wrap:wrap;justify-content:center;padding:9px;border:1px solid rgba(115,207,255,.4);border-radius:18px;background:rgba(5,11,25,.94);box-shadow:0 0 28px rgba(60,140,225,.25);color:#eaf6ff;font:600 12px/1.3 system-ui,sans-serif}
#nox-express-primary button{--nox-planet:#4ba3f1;--nox-planet-light:#a7edff;appearance:none;cursor:pointer;min-height:70px;min-width:92px;display:flex;flex-direction:column;justify-content:center;align-items:cente¶»§q«^
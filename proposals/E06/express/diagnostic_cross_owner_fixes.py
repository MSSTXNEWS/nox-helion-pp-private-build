#!/usr/bin/env python3
"""E06 R08 diagnostic-only compiler repairs; original donor and owner PRs unchanged."""
from pathlib import Path
import hashlib, json, sys

ROOT = Path(sys.argv[1]) if len(sys.argv) == 2 else None
RUN = "NOX-V16-E06-EXPRESS-CROSS-OWNER-DIAG-20261028"
if ROOT is None:
    raise SystemExit("Source root required")

def sha(b):
    return hashlib.sha256(b).hexdigest()

receipts = []
def change(path, pre_sha, post_sha, correction):
    p = ROOT / path
    before = p.read_bytes()
    if sha(before) != pre_sha:
        raise RuntimeError("DIAG_PREIMAGE_HOLD " + path)
    s = before.decode("utf-8")
    out = correction(s)
    b = out.encode("utf-8")
    if sha(b) != post_sha:
        raise RuntimeError("DIAG_POSTIMAGE_HOLD " + path)
    p.write_bytes(b)
    receipts.append({
        "path": path, "run_id": RUN, "pre_sha256": pre_sha,
        "post_sha256": post_sha, "diagnostic_only": True,
        "source_original_preserved": True, "owner_approval": "HOLD"
    })
    print("DIAG_SHA_PASS", path, pre_sha, post_sha)

def single(s, old, new):
    if s.count(old) != 1:
        raise RuntimeError("DIAG_EXACT_OCCURRENCE_HOLD: " + old[:45])
    return s.replace(old, new, 1)

change("R11/MainWindow.xaml.cs",
    "b4c20c71380c63cec07c7ea4017c4f44f55077a985d2bfec42ecfe5f1a2b8825",
    "35670c5b6b04272b545459efce131f13e769bf283e4f19153b76d08e94c17e6f",
    lambda s: single(s,"using NOX.P01.Packages.P02.OpenAI;","using NoxP01.Packages.P02.OpenAI;"))

change("R11/Packages/P02/OpenAI/OpenAiResponsesProvider.cs",
    "968860590cb112b76b6399ad72d868269eebe6daec545bfead94fecd3e161449",
    "a5c30ca4e05a3d258d3af485c7694d698fdc0f71177dc018e3e4f37cc59c6692",
    lambda s: single(s, "using System.Collections.Concurrent;",
        "using System.IO;\nusing System.Net.Http;\nusing System.Collections.Concurrent;"))

change("R11/Packages/P05/InstallerRunReport.cs",
    "1a6fcfff72924260a9e913f8af26a7c1009482bbdef67b85e5c11c0709ca8a4e",
    "d15607f6465472dd0586a58eac5e598694ea78e57f2f464c604d5cf37dfd8f3f",
    lambda s: single(s, "using System.Globalization;",
        "using System.IO;\nusing System.Globalization;"))

change("R11/Packages/P03/module/ComponentInstaller.cs",
    "2ae39faf5a19dd42a9787e1f3b98aaeb8d6efb2cd5165a9c6e59183daef07bf3",
    "45842d6a5cbdd0940bd8f6d3b0d62e791c6de37994c784ca61e38cd4a2457af3",
    lambda s: single(s, "using System.Diagnostics;",
        "using System.IO;\nusing System.Diagnostics;"))

def event_fix(s):
    duplicate = "    public string? OperationId { get; init; }\n"
    if s.count(duplicate) != 2 or (duplicate * 2) not in s:
        raise RuntimeError("EVENT_OPERATION_ID_DUPLICATE_HOLD")
    return s.replace(duplicate * 2, duplicate, 1)

change("R11/Packages/P03/module/ModelCenterEvent.cs",
    "94e15e68c6bdefc709121ab0b23a8379ffb84bc5d70e9ea40c284b7812a7f3fb",
    "deb37e38b52f89d31dda19403b5dc60658150781f98732e45e5765bc37ca8ef8",
    event_fix)

def duplicate_methods(s):
    methods = [
        "    private void RefreshComponentActions()",
        "    private ComponentOperation ReadComponentOperation()",
    ]
    for token in methods:
        pairs = []
        start = 0
        while True:
            i = s.find(token, start)
            if i < 0:
                break
            brace = s.index("{", i)
            depth = 0
            end = None
            for pos in range(brace, len(s)):
                if s[pos] == "{":
                    depth += 1
                elif s[pos] == "}":
                    depth -= 1
                    if depth == 0:
                        end = pos + 1
                        break
            if end is None:
                raise RuntimeError("P03_METHOD_BRACE_HOLD")
            pairs.append((i, end, s[i:end]))
            start = end
        if len(pairs) != 2 or pairs[0][2] != pairs[1][2]:
            raise RuntimeError("P03_METHOD_DUPLICATE_NOT_IDENTICAL_HOLD")
        start, end, _ = pairs[1]
        s = s[:start] + s[end:]
    return s

change("R11/Packages/P03/worker-window/ModelDownloaderWindow.xaml.cs",
    "ccd0fb325eb8a250323f5aa17c8e7bdad0d281eb681ad381c96ee3a99498814e",
    "c2c7470d51ba3fc238517fd138666eee73a3d7c8a68cc8532d1585bd57c88166",
    duplicate_methods)

out = Path("ci-evidence")
out.mkdir(exist_ok=True)
(out / "r08-cross-owner-compile-fixes.json").write_text(
    json.dumps({
      "schema": "NOX_R08_DIAGNOSTIC_CROSS_OWNER_FIXES_V1",
      "run_id": RUN, "original_archive_unmodified": True,
      "p01_to_p05_components_removed": False,
      "integration_approved": False,
      "changes": receipts,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("DIAG_CROSS_OWNER_SOURCE_PASS", len(receipts))

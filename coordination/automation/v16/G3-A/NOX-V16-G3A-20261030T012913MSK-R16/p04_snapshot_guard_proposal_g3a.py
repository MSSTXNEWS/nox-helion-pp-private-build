#!/usr/bin/env python3
"""G3-A isolated, PRE-SHA-locked P04 proposal. Does not mutate the product source.
Owner: manual #3 P04 developer; only T06 may integrate into shared PR162.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SOURCE_PATH = "Packages/P04/model_snapshot_probe.py"
SOURCE_PRE_BLOB = "c0286fe58c020835ec1fd8c4a7b6d1345f115598"
SOURCE_PROPOSED_POST_BLOB = "11c447b6d22c4dde4bcd7aa9d311a8cd3ee2b200"
CHANGES = [
  [
    "import hashlib\nimport json\nimport os\n",
    "import hashlib\nimport json\nimport math\nimport os\n"
  ],
  [
    "    obj = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)\n    if not isinstance(obj, dict):\n        raise ValueError(\"MODEL_JSON_NOT_OBJECT\")\n    return obj\n",
    "    def strict_float(value):\n        number = float(value)\n        if not math.isfinite(number):\n            raise ValueError(\"MODEL_NONFINITE_JSON_NUMBER\")\n        return number\n\n    obj = json.loads(raw, object_pairs_hook=unique_pairs,\n                     parse_constant=reject_constant, parse_float=strict_float)\n    if not isinstance(obj, dict):\n        raise ValueError(\"MODEL_JSON_NOT_OBJECT\")\n    # Escaped lone UTF-16 surrogates parse in Python, but cannot round-trip to\n    # a valid native safetensors UTF-8 header. Check nested values and keys.\n    pending = [obj]\n    while pending:\n        value = pending.pop()\n        if isinstance(value, dict):\n            pending.extend(value.keys())\n            pending.extend(value.values())\n        elif isinstance(value, list):\n            pending.extend(value)\n        elif isinstance(value, str) and any(0xD800 <= ord(c) <= 0xDFFF for c in value):\n            raise ValueError(\"MODEL_INVALID_UNICODE\")\n    return obj\n"
  ],
  [
    "any(type(dim) is not int or dim < 0 for dim in shape)",
    "any(type(dim) is not int or dim < 0 or dim > (1 << 64) - 1 for dim in shape)"
  ]
]

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\\0" + data).hexdigest()

def propose(source: bytes) -> bytes:
    if git_blob(source) != SOURCE_PRE_BLOB:
        raise ValueError("G3A_STALE_SOURCE_PREIMAGE")
    text = source.decode("utf-8")
    for old, new in CHANGES:
        if text.count(old) != 1:
            raise ValueError("G3A_NONUNIQUE_OR_STALE_PATCH_HUNK")
        text = text.replace(old, new, 1)
    output = text.encode("utf-8")
    if git_blob(output) != SOURCE_PROPOSED_POST_BLOB:
        raise ValueError("G3A_POST_BLOB_MISMATCH")
    return output

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve() or args.output.exists():
        raise SystemExit("G3A_REFUSE_OVERWRITE_OR_PRODUCT_MUTATION")
    proposed = propose(args.source.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(proposed)
    print(json.dumps({"pre_git_blob": SOURCE_PRE_BLOB,
                      "candidate_post_git_blob": SOURCE_PROPOSED_POST_BLOB,
                      "candidate_path": str(args.output),
                      "product_file_unchanged": True}, sort_keys=True))

if __name__ == "__main__":
    main()

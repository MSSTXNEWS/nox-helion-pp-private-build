# RELAY35 4A02 · metadata-only split planning

Task spec SHA-256: `dcec8628dab49be9b85c52864df224f5a012fd6fda82b4ade0822ba2a525d463`.

This source-only helper accepts an owner-prepared metadata manifest, including Drive or Library origins. It does not call Google Drive, read example payloads, fetch weights, train a model, write a dataset, or enable a serving route.

## Input

The root JSON object has exactly these keys:

```json
{
  "schema": "nox.training.source-manifest.v1",
  "split_seed": "owner-chosen-safe-id",
  "examples": [
    {
      "example_id": "example-001",
      "goal_id": "goal-001",
      "language": "ru",
      "topic": "tools",
      "source_kind": "drive",
      "origin_sha256": "<64 lowercase hex characters>",
      "content_sha256": "<64 lowercase hex characters>",
      "license_id": "CC-BY-4.0"
    }
  ]
}
```

Rows are metadata only. The validator rejects extra fields, so sample text, direct Drive IDs, URLs, paths, credentials, and weight bytes cannot be included in this schema. The producer must hash the stable source reference into `origin_sha256` and the normalized sample into `content_sha256`.

Allowed topics are memory, speech, planning, tools, code, and behavior. Languages are RU and ES. Each row must name a source kind and license identifier.

## Output and limits

Run `python3 nox-control/nox_dataset_split_plan.py --manifest <metadata-only.json>`. The plan is JSON on stdout. It deduplicates identical content hashes (and rejects conflicting goal/language/topic/license labels), keeps all hashed origins, groups rows by source origin, then assigns stable 80/10/10 train/dev/holdout splits from the selected seed. It reports per-language/topic coverage and returns HOLD if an observed stratum lacks any split or has fewer than three independent source groups.

The program does not verify that a declared content hash matches a sample, validate license rights, or inspect Drive/Library permissions. It emits a candidate split plan, not a dataset or acceptance receipt. Independent source verification, native dataset materialization, and training authorization remain open.

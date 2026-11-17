# Final source and evidence publication handoff

This is a repository source/evidence commit only. The parent and base tree are fixed in the prepared publication manifest. Do not change the owner operator, its entrypoint, workflow, permissions, credentials, or native service as part of this commit. The existing operator remains the read-only diagnostic entry.

## Current evidence snapshot

- The five main project documents were published by root to the same Drive IDs and independently read back as exact bytes at2026-11-17T19:09:31.998157+00:00. Their contents are intentionally not copied here. `release/DRIVE_RUNTIME02_RAW_READBACK_RECEIPT.json` records their IDs/SHA256/lengths.
- Root's latest automation receipt at19:06:14UTC records15enabled tasks and15V3 policies. This source publication creates or reschedules none.
- Native runtime0.2 source stage run44154217772 installed12files/98385bytes with all12pins matching: SOURCE_INSTALLED_NOT_BOUND. It did not import/bind runtime, start workers, download models or invoke a model. The48source tests are26integration+20controller+2independent; they are not native Drive/model/trainer acceptance.
- The historical stage diagnostic run44153563662 saw0/12files and priority0775. The subsequent other-team O1 hardening and our successful source staging are separate outcomes. Keep their run/job/source identities distinct.
- Latest own-history reconciliation run44153064827 still returned422 INVALID_LIMIT. Authentication and exact HTML/CSS/JS passed; public-browser/visual acceptance and whole-chat acceptance were not established.
- O0/root verified the exact wrapper line under0a0165…: interpolating httpx.URL.query bytes yields a bytes representation and a trailing quote in limit. The local reproduction uses actual httpx0.28.1 with zero network calls. O0 owns the scoped ASCII-decode fix. Its native installation/postimage and successful read-only own-history acceptance are not claimed by this snapshot.

## Historical handoffs and dependencies

Source-stage handoffs and PREPARED/APPLIED_LOCAL_ONLY receipts are retained in their original bytes as chronological evidence. They do not request another staging attempt or operator change. The later root Drive readback supersedes the earlier local-only publication state.

The captured-request fixture requires the existing sibling `native_resonance_patch/native_acceptance.py` under this same source root. At the fixed base it is46684bytes, SHA2567b82ccbb235bd51c9a4782919aa6cfd484ad96e253ef0c2cebd9c61ca8e2ef9e and Git blob3f68bf18e9d5483d0d7c052e883f0218947db7a8; the prepared publication does not alter it. The exact-line query fixture requires httpx0.28.1. Stage review dependencies already exist at this base; no native preimage is added.

The delta program deliberately requires the five canonical document inputs with the recorded BASE_SHA256 pins. They remain on Drive and are excluded from this code publication. No candidate full native preimages, encrypted exports, keys, main document copies, ZIPs or duplicate journals are included.

## Parent's next action

Verify the publication branch still points to the exact expected parent commit. Use the prepared `tree_elements` with the fixed base tree for one commit, preserving every unrelated path. If the parent moved, reconcile it rather than force-update. Verify the resulting paths/blob identities. This publishes evidence only; O0 retains ownership of the query fix, and host binding remains separate. Do not issue another model POST or reactivate the superseded runtime as part of publication.

# NOX WEB Converged V14 — staging handoff (2026-11-18)
instructions_version: 0.0.6

**STATUS: SOURCE_CANDIDATE_ONLY / NO NATIVE ACCEPTANCE.**
Canonical NOX Task Control and original A/B task IDs remain intact. This document maps integration gates; it does not reset counts or supersede unique sources.

## Source and build lineage
- Latest full WEB source examined: [WEB WOW MAX V13, 1271 paths](https://drive.google.com/file/d/1goyd4rTLYEJFA80dMl_A-zpYLxQnASXQ/view), original SHA256 `f12a6f36e9718ee483e0d9d2e3f16aa41c3911ec9ef6e2bc03502a5da0d62fe4`.
- Historical WEB V29.3 is **not** the final release baseline. Separate V133 preserved 1089 ancestor paths; newer V13 has 43 active routes, 5 worlds, 6 palettes, and later layers.
- Local assembled V14 staging ZIP SHA256 `dd74f6378c34d0203f8d27e6ad10537b9019232a290649f605ca161cbffbfc87`, 1266 members. This is not uploaded to this repository and not installed on OneHost.
- 8 source `.bak_*` paths excluded from **candidate only**, retained in original V13 archive. No Drive/server deletion.
- Source code change: status chip timeout bound to its own AbortController, stale async HTTP response cannot overwrite newer state. `node --check` PASS; full native tests NOT RUN.
- Related [original PR #256](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/256) remains draft; no merge or forced server restart.

## Unified execution gates
1. Read exact recent receipts, source SHA, owner STOP, installed SHA, model identity, PID/start ticks x2, available disk/VRAM. No unowned mutation.
2. One claim per TaskID/path; safe prepare→source patch→test→same-branch commit→authorized install→readback→live acceptance→checkpoint→next READY. SOURCE_TESTED never equals DONE.
3. Preserve S03/persona ACL, owner STOP, weights, optimizer/scaler/RNG, all unique logs and native receipts.
4. Only clean exact duplicate bytes after independent SHA backup+restore, last-use check, and owner write lease. No blanket deletion.
5. A/B/D automation schedules and existing work IDs remain untouched. If 3–6 actual worker IDs are unavailable, show BLOCKED, never simulate workers.

## Task bridges (never add these to 295)
| Bridge ID | Area | Concrete deliverable | Existing IDs |
|---|---|---|---|
| CV14-01 | Owner/OneHost | installed SHA/PID x2 / lease / STOP | 0A01,0A02 |
| CV14-02 | Owner/OneHost | reconcile four legacy inflight, no replay | 0A03,0B05 |
| CV14-03 | Coordination | crosswalk 295/240/65/54 ID namespaces | 0A04,6A01 |
| CV14-04 | Web | exact served WEB SHA, source identity | 5A02,1A01 |
| CV14-05 | Web | 43-page single HOME/D02 and unified navigation | 5A02,I-16 |
| CV14-06 | Chat | served model, real live stream | 1A01,0B05 |
| CV14-07 | Chat | STOP generation and owner lease revoke | 0A01,1V14-01 |
| CV14-08 | Memory | S03 durable round trip, restart, persona isolation | 3A01,0B05 |
| CV14-09 | Resources | GPU0/GPU1/VRAM/RAM/SSD status and chat priority | 2A02,2A03,4A02 |
| CV14-10 | Resources | offsite backup/restore and optimizer/scaler/RNG | 2A04,4A02 |
| CV14-11 | Web | race-safe OneHost status read-only indicator | 5A02 |
| CV14-12 | Dispatcher | one atomic task/file/owner claim, fenced writer | 0A03,6A01 |
| CV14-13 | Dispatcher | native NORMAL3, FORSAZH6 only with admission | 6A01,3B05 |
| CV14-14 | Dispatcher | handoff after terminal states without idle churn | 0A04,6A01 |
| CV14-15 | Memory | C01-C08, M0-M7, retrieval into one S03 | 3A01,3B05 |
| CV14-16 | Chat | context/TTFT p50/p95 and meaningful output | 1A01,1B03 |
| CV14-17 | Training | gated FP16/QLoRA optimizer steps and checkpoint | 4A02,2A04 |
| CV14-18 | Knowledge | document ingestion/dedup/license/provenance | 3A01,4A03 |
| CV14-19 | Self repair | reproduce failure, repair, verify, rollback | 3B05,6B04 |
| CV14-20 | Voice | RU/ES ASR/TTS/STOP | 0B05,1A01 |
| CV14-21 | Media | job→asset edit/export/reload and cancellation | 0B05,5A02 |
| CV14-22 | Web | 5 worlds 6 palettes, Reduced Motion/ECO | 5A02,I-16 |
| CV14-23 | Windows | WebView2/NSIS physical same-SHA install/uninstall | 0A02,5A02 |
| CV14-24 | PC | consent-scoped PC control and audit STOP | 1A01,6B04 |
| CV14-25 | Drive | 1360 inventory exact duplicates only after restore | 0A02,A4 |
| CV14-26 | Dashboard | evidence-only dashboard, no fake percentages | 6A01,5A02 |
| CV14-27 | Training | disjoint score of knowledge/skills/own weights | 4A03,6A01 |
| CV14-28 | Release | native single-WEB promotion after independent E2E | 0A01,5A02,6A01 |

Every bridge must record exact source commit or Drive ID; status SOURCE/INSTALLED/USED/ACCEPTED separately; owned process/lease and relevant QA; SHA before/after; rollback proof; no native PASS without independent live receipts.

## Primary sources
- [Current NOX unified concept](https://drive.google.com/file/d/1Ez0JSlLmb51GdzeV1-Nls0TF8dWczM_E/view)
- [V13 WEB specification](https://drive.google.com/file/d/1J8mbi_7ooTCmYl3cBqB34Uus7GzA8Vwz/view)
- [GitLab 230-task JSON at pinned SHA](https://gitlab.com/s-grouptwet/nox-helion-pp-private-build/-/blob/81b4f5def11095c933761d37418c9bdb5b1d317d/handoff/20261117/nox-v15-kit/server/work_tasks.json)
- [Canonical Notion task control](https://app.notion.com/p/2d2e318b2a0a4d2eae388653aae1952d)

**Next native step:** owner read-only reconciliation then OneHost functional canary; do not promote source zip blindly.

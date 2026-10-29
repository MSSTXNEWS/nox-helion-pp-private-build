/* NOX V16 coordination snapshot, never live. T02 sole-writer Git CAS. */
window.NOX_CONTROL_DATA={
  "schema": "NOX_CONTROL_CENTER_R26_SNAPSHOT_V1",
  "observed_at": "2026-10-29T22:42:33.070Z",
  "source": "PINNED SNAPSHOT: authenticated GitHub PR162 HEAD/tree, shared error Git blob, R29 owner roster, authenticated Automations.peek 25 IDs + per-ID current run readback; owner receipts issue #177",
  "source_mode": "SNAPSHOT_NOT_LIVE",
  "repository": "MSSTXNEWS/nox-helion-pp-private-build",
  "pr": 162,
  "head": "1cda912558c8636cc85dd4a08c65efcd19a11905",
  "commit_count": 355,
  "pr_draft": true,
  "source_ready": false,
  "release_ready": false,
  "manuals": [
    {
      "id": "1",
      "role": "SOURCE INTEGRATOR",
      "name": "Главный интегратор",
      "blocks": [
        "P01",
        "P02",
        "P03",
        "P04",
        "P05"
      ],
      "phase": "SOURCE_INTEGRATED_QA_PENDING",
      "gate": {
        "done": null,
        "total": null
      },
      "approaches": {
        "done": null,
        "total": 10
      },
      "description": "PR162 pinned HEAD advanced; Host50 source bound 40/50, native 14 pending; P01 route policy SOURCE ONLY. Owner 10 approaches N/D; no current-HEAD signed Windows QA.",
      "source_head": "1cda912558c8636cc85dd4a08c65efcd19a11905",
      "run_id": null,
      "last_manual_run_id": null,
      "last_run_evidence_status": "OWNER_RECEIPTS_ON_PRIOR_SHA; LATEST_HEAD_NOT_MANUAL_CYCLE_PROOF",
      "latest_source_support_commit": "1cda912558c8636cc85dd4a08c65efcd19a11905",
      "latest_source_support_evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/1cda912558c8636cc85dd4a08c65efcd19a11905",
      "report_gates": {
        "A": null,
        "B": null,
        "C": null,
        "D": null,
        "E": null
      }
    },
    {
      "id": "3",
      "role": "P04/P05 DEVELOPER",
      "name": "Разработчик моделей и SPACE",
      "blocks": [
        "P04",
        "P05"
      ],
      "phase": "OWNER_DONOR_PREPARED",
      "gate": {
        "done": null,
        "total": null
      },
      "approaches": {
        "done": null,
        "total": 10
      },
      "description": "P05 SPACE donor source+smoke patch PR221, full .NET/native QA NOT_RUN; most recent activation is read-only, not a 10-approach work cycle.",
      "source_head": "fabc3f35de9242498f55f0dd2416c34cd0bf1eb7",
      "run_id": "NOX-V16-MANUAL03-R26-ACTIVATION-20261030",
      "last_run_evidence_status": "PRESTART_ONLY_NOT_10_APPROACH_CYCLE",
      "last_owner_physical_receipt": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177#issuecomment-6508215492",
      "report_gates": {
        "A": null,
        "B": null,
        "C": null,
        "D": null,
        "E": null
      }
    },
    {
      "id": "2",
      "role": "INDEPENDENT QA",
      "name": "Независимый контролёр",
      "blocks": [
        "P01",
        "P02",
        "P03",
        "P04",
        "P05"
      ],
      "phase": "SOURCE_QA_LIMITED_STALE_HEAD",
      "gate": {
        "done": null,
        "total": null
      },
      "approaches": {
        "done": null,
        "total": 10
      },
      "description": "Manual #2 R33 isolated donor PR223 and source-level QA only; no independent current-HEAD native acceptance. No 10-approach proof from this run.",
      "source_head": "1cda912558c8636cc85dd4a08c65efcd19a11905",
      "run_id": null,
      "last_manual_run_id": null,
      "last_run_evidence_status": "N/D structured current-HEAD manual report",
      "last_source_qa_evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177#issuecomment-6510084060",
      "report_gates": {
        "A": null,
        "B": null,
        "C": null,
        "D": null,
        "E": null
      }
    }
  ],
  "blocks": [
    {
      "id": "P01",
      "name": "Основа и безопасность",
      "weight": 20,
      "accepted": null
    },
    {
      "id": "P02",
      "name": "Voice / интеграции",
      "weight": 25,
      "accepted": null
    },
    {
      "id": "P03",
      "name": "ModelCenter / Queue",
      "weight": 20,
      "accepted": null
    },
    {
      "id": "P04",
      "name": "GPU / RAG / модели",
      "weight": 25,
      "accepted": null
    },
    {
      "id": "P05",
      "name": "Events / SPACE",
      "weight": 10,
      "accepted": null
    }
  ],
  "automations": [
    {
      "id": "6ae2af4f6c448191932f01b35fa364c1",
      "title": "NOX V16 G5-A T02 журнал",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "in_progress",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "a39bbf36-cd7c-8332-9ee3-3c4dc3644ebf",
      "last_run_started_at": "2026-10-29T22:35:03.471465Z",
      "last_run_completed_at": null,
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2aef78ba881919e6022c1103959a2",
      "title": "NOX V16 G3-C T06 интегратор",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "failed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "7c83ca61-7c98-8320-ab52-49660ca305aa",
      "last_run_started_at": "2026-10-29T21:42:13.744075Z",
      "last_run_completed_at": "2026-10-29T21:48:20.206662Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2aefe3c248191a7131fc9876611e6",
      "title": "NOX V16 G2-C P03 Queue",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "23e18e91-e5ec-832f-b34d-c2ea6c420f09",
      "last_run_started_at": "2026-10-29T22:09:50.344527Z",
      "last_run_completed_at": "2026-10-29T22:18:49.468270Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2af2b1bcc8191a4d15cb8f6f9d25b",
      "title": "NOX V16 G5-C T11 GitLab READY",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "c08e0e9d-cddc-8321-8b12-ee66f8883af3",
      "last_run_started_at": "2026-10-29T21:31:35.547863Z",
      "last_run_completed_at": "2026-10-29T21:40:29.528803Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2aef4bbc081918693b0552743bd0d",
      "title": "NOX V16 G5-B T10 SOURCE_READY",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "fe6fcc1a-2518-8326-9676-94d8d196dc0e",
      "last_run_started_at": "2026-10-29T22:16:12.791283Z",
      "last_run_completed_at": "2026-10-29T22:27:13.206933Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2af2f84088191ba04843861edf73b",
      "title": "NOX V16 G4-C T09 freeze",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "a89eb080-c6c4-8330-a295-ed6674e9ec6c",
      "last_run_started_at": "2026-10-29T22:03:43.025859Z",
      "last_run_completed_at": "2026-10-29T22:11:35.030122Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2af2d4f8c81919951564c5eb2ddf6",
      "title": "NOX V16 G4-A T07 NOLOSS",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "a4cd03a2-af88-832a-ba7e-25e0cfb892aa",
      "last_run_started_at": "2026-10-29T21:50:56.926222Z",
      "last_run_completed_at": "2026-10-29T21:58:04.742167Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2af347fbc81918ddafed356511243",
      "title": "NOX V16 G3-B PACK02",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "in_progress",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "aaf629f0-f180-8323-9b35-f3e3c15f3f79",
      "last_run_started_at": "2026-10-29T22:25:54.228037Z",
      "last_run_completed_at": null,
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2af008eac8191a03526f290b801c6",
      "title": "NOX V16 G3-A P04 GPU/RAG",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "6abbee6d-1f04-8322-8831-15e8caf004ec",
      "last_run_started_at": "2026-10-29T22:21:54.304631Z",
      "last_run_completed_at": "2026-10-29T22:33:17.285235Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2aef9c3fc81918fd4c4b0041207ef",
      "title": "NOX V16 G2-B P02 Voice",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "be676090-75b8-8333-9252-db3a7e77aff1",
      "last_run_started_at": "2026-10-29T22:12:59.257585Z",
      "last_run_completed_at": "2026-10-29T22:24:20.880178Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2af31f2988191902bae4aaec2635e",
      "title": "NOX V16 G2-A Host50",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "12e3e13a-3cdc-832d-a799-98d786d2b6e4",
      "last_run_started_at": "2026-10-29T22:36:41.695541Z",
      "last_run_completed_at": "2026-10-29T22:39:04.441341Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2aecc59f88191a10a9342f8a1930c",
      "title": "NOX V16 G1-B NSIS source",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "dfc005ba-ba9c-832c-ac6a-6d8dc6e449c2",
      "last_run_started_at": "2026-10-29T22:12:16.248031Z",
      "last_run_completed_at": "2026-10-29T22:22:47.983300Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2aefbde94819183730a2ed3cad78c",
      "title": "NOX V16 G1-C P04–P05",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "4313dd93-e9e8-8333-9a3e-67f2fb1fd333",
      "last_run_started_at": "2026-10-29T22:00:39.924121Z",
      "last_run_completed_at": "2026-10-29T22:11:35.981277Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2af28e4b8819192bbf6bb3857cc84",
      "title": "NOX V16 G1-A P01–P03",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "da6d5c1b-db50-8330-a685-9fea9cacaa35",
      "last_run_started_at": "2026-10-29T22:05:35.380204Z",
      "last_run_completed_at": "2026-10-29T22:19:25.545455Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae2af03ddd88191b39ad44b379cc3dc",
      "title": "NOX V16 G4-B T08 блокеры",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "in_progress",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z",
      "last_run_id": "56a9a9fe-33bc-8327-9b03-4354098ee883",
      "last_run_started_at": "2026-10-29T22:36:15.596316Z",
      "last_run_completed_at": null,
      "run_receipt_scope": "AUTHENTICATED_PEEK_SAME_RUN_PINNED"
    },
    {
      "id": "6ae342e4a0248191954f95217ebee33b",
      "title": "NOX V16 T13 E07 PAUSED",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    },
    {
      "id": "6ae342df73788191b8d8fb6b179dad46",
      "title": "NOX V16 T12 BUILD PAUSED",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    },
    {
      "id": "6ae342e74028819197da844e6468b640",
      "title": "NOX V16 T14 RELEASE FIX PAUSED",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    },
    {
      "id": "6ae342ea03d48191ad25ba7bcf4e5c8a",
      "title": "NOX V16 T15 RELEASE PAUSED",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    },
    {
      "id": "6ae16157f7388191a5d0634fb13d3d01",
      "title": "NOX W4·02 P05 Events SPACE",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    },
    {
      "id": "6ae1618c11908191b891c76f2ffa4238",
      "title": "NOX W4·03 SPACE Mobile Bridge",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    },
    {
      "id": "6ae161819d9481919f3dbb52cbfd9e62",
      "title": "NOX W1·01 SourceLock 729",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    },
    {
      "id": "6ae161b0c5f88191ada31d0e3b12364d",
      "title": "NOX W1·03 Security NO-LOSS",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    },
    {
      "id": "6ae1618459288191b6be333b6af9c89b",
      "title": "NOX W1·02 Native Host50",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    },
    {
      "id": "6ae1614c140881918783372458d52f29",
      "title": "NOX W2·01 D02 WOW E01",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "HISTORICAL",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T22:42:33.070Z"
    }
  ],
  "errors": {
    "OPEN": 5,
    "FIX_APPLIED_UNVERIFIED": 4,
    "VERIFIED_CLOSED": 2,
    "total": 11,
    "history_complete": false,
    "blob": "09ab4de165f0d921b4229a2dfb9115278b05749e"
  },
  "gates": [
    {
      "name": "T06",
      "done": 1,
      "total": 8
    },
    {
      "name": "T08",
      "done": 1,
      "total": 3
    },
    {
      "name": "T09",
      "done": 1,
      "total": 6
    },
    {
      "name": "T10",
      "done": 1,
      "total": 7
    },
    {
      "name": "T11",
      "done": 2,
      "total": 5
    }
  ],
  "gate_status": "HISTORICAL_NOT_REVALIDATED_ON_fc9182f519c64f5f4e54a52ded9b2575c0bcff9a",
  "notes": [
    "Ручные — главные владельцы. AUTO — поддержка.",
    "Количество ручных и AUTO выводится из данных, а не зашито в интерфейсе.",
    "Общий процент продукта Н/Д: нет полного доказанного frozen TaskID ledger.",
    "Прежние gate x/n исторические, не подтверждены на текущем HEAD.",
    "R27: PR162 fc9182f519c64f5f4e54a52ded9b2575c0bcff9a tree 5e0d9127f6b5a57f6bda47a6fd213866689d4fae at snapshot, not a live connection. Error register a8f71dd3e12906120fd6ee52386cbd549615a2eb, 11 entries 5/4/2, history incomplete.",
    "R27: 25 known NOX automations, 15 active supporting enabled, 10 archive/future disabled. T06 provider last run FAILED while existing Git source persists; no auto re-run.",
    "R27: Manual №1/№3/№2 approach bars N/D without per-approach independent receipts. QA_ACCEPTED delta=0. SOURCE_READY/BUILD NOT_AUTHORIZED.",
    "R33 SOURCE DELTA: Compared confirmed last CAS HEAD fc9182f5... to current pinned Git HEAD/tree; shared register R33 run_delta CAS 0451aa5c...; no QA_ACCEPTED. Scheduler 15 owner-roster current: 10 enabled/5 disabled; 10 historical disabled. Disabled current IDs left unchanged; source-host route 40/50 vs native acceptance N/D. This is NOT live UI."
  ],
  "tasks": [
    {
      "id": "P01/safe_path",
      "block": "P01",
      "owner": "1",
      "qa": "2",
      "stage": "INTEGRATED_P0_REJECTED",
      "evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177#issuecomment-6508082490",
      "note": "Git blob f839f2... still permits unsafe Windows colon/control paths. Same-head P0 security QA FAIL; T06 owner patch needed.",
      "qa_accepted": false
    },
    {
      "id": "P03/ModelCenter",
      "block": "P03",
      "owner": "1",
      "qa": "2",
      "stage": "INTEGRATED_SOURCE_ONLY",
      "evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/dbfd22340427e35440242f144aa1730833661695",
      "note": "P03 reviewedTag typeof id guard in blob 2e5830..., but separate consent snapshot invalidation still unverified; T08 independent current-head QA pending.",
      "qa_accepted": false
    },
    {
      "id": "P04/model_snapshot",
      "block": "P04",
      "owner": "3",
      "integrator": "1",
      "qa": "2",
      "stage": "INTEGRATED_UNVERIFIED",
      "evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/66f9f7812186ec1a3b1c8472d1792a854760ec7e",
      "note": "Model snapshot blob f5cf5... and tests 15a81... verified source, native rights/Host50 QA not accepted.",
      "qa_accepted": false
    },
    {
      "id": "P04/RAG",
      "block": "P04",
      "owner": "3",
      "integrator": "1",
      "qa": "2",
      "stage": "INTEGRATED_UNVERIFIED",
      "evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/d23956686fd9634225512f456b194fc723eda933",
      "note": "Исходники интегрированы, независимая QA не засчитана",
      "qa_accepted": false
    },
    {
      "id": "P05/SPACE",
      "block": "P05",
      "owner": "3",
      "integrator": "1",
      "qa": "2",
      "stage": "INTEGRATED_LEGACY_WITH_OWNER_DONOR_PENDING",
      "evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177#issuecomment-6508215492",
      "note": "Manual #3 PR221 HEAD fabc3f35de9242498f55f0dd2416c34cd0bf1eb7 source donor ready; 4-file source/test + .NET smoke still not integrated/accepted.",
      "qa_accepted": false
    },
    {
      "id": "P05/smoke",
      "block": "P05",
      "owner": "3",
      "qa": "2",
      "stage": "SOURCE_PREPARED",
      "evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177#issuecomment-6508215492",
      "note": "Donor source/test smoke only, targeted .NET and independent QA NOT_RUN.",
      "qa_accepted": false
    }
  ],
  "tasks_are_full_ledger": false,
  "tree": "e98ff3a9ccab56d81625b02cef9f5d721b79fd8c",
  "product_percent": null,
  "automation_counts": {
    "total": 25,
    "active_primary_support": 15,
    "active_enabled": 10,
    "active_disabled": 5,
    "all_enabled": 10,
    "all_disabled": 15,
    "archived_or_future": 10
  },
  "manual_count": 3,
  "manual_manifest_ref": "coordination/r25/R25_MANUAL_FIRST_OTCH1_CONTROL.md",
  "last_t02_journal": {
    "run_id": "NOX-V16-T02C-A39BBF36-20261030-R33-FINITE-SOURCE-DELTA",
    "commit": "0451aa5cfcebf5e4bfbf4e17088be8c38f346b9b",
    "blob": "09ab4de165f0d921b4229a2dfb9115278b05749e",
    "master": "NO_WRITE_R33",
    "lessons": "NO_WRITE_R33",
    "e06": "FAILED_PRECONDITION_PRIOR; NO_WRITE_R33",
    "receipt": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/0451aa5cfcebf5e4bfbf4e17088be8c38f346b9b/coordination/ops/NOX_V16_ACTIVE_ERROR_REGISTER.json",
    "accepted_delta": 0
  },
  "host50": {
    "historical_source_hold": 13,
    "source_unbound": 10,
    "native_pending": 14,
    "not_equivalent": true,
    "source_bound": 40
  },
  "accepted_delta_new": 0
};

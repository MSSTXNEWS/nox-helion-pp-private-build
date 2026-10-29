/* NOX V16 T02 coordination snapshot (not live). Source-only, no product acceptance. */
window.NOX_CONTROL_DATA={
  "schema": "NOX_CONTROL_CENTER_R26_SNAPSHOT_V1",
  "observed_at": "2026-10-29T23:50:00.602Z",
  "source": "R34 GitHub exact source SHA, full roster, authenticated scheduler list+peek (read earlier in same run); pinned snapshot NOT live",
  "source_mode": "SNAPSHOT_NOT_LIVE",
  "repository": "MSSTXNEWS/nox-helion-pp-private-build",
  "pr": 162,
  "head": "852ccc1611d99afaf48e7fc4c33a5509d385f9a9",
  "commit_count": 385,
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
      "phase": "INTEGRATED_SOURCE_QA_PENDING",
      "gate": {
        "done": null,
        "total": null
      },
      "approaches": {
        "done": null,
        "total": 10
      },
      "description": "PR162 pinned HEAD advanced; Host50 source bound 40/50, native 14 pending; P01 route policy SOURCE ONLY. Owner 10 approaches N/D; no current-HEAD signed Windows QA.",
      "source_head": "852ccc1611d99afaf48e7fc4c33a5509d385f9a9",
      "run_id": null,
      "last_manual_run_id": null,
      "last_run_evidence_status": "NO_AUTHENTICATED_CURRENT_MANUAL_RUNID",
      "latest_source_support_commit": "852ccc1611d99afaf48e7fc4c33a5509d385f9a9",
      "latest_source_support_evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/852ccc1611d99afaf48e7fc4c33a5509d385f9a9",
      "report_gates": {
        "A": null,
        "B": null,
        "C": null,
        "D": null,
        "E": null
      },
      "registry_scope": "current"
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
      },
      "registry_scope": "current"
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
      "source_head": "d5bb9d0628b634e359d38ce409d5063cb1b51573",
      "run_id": "NOX-V16-M2-R36-THREE-BLOCKS-20261030",
      "last_manual_run_id": "NOX-V16-M2-R36-THREE-BLOCKS-20261030",
      "last_run_evidence_status": "MANUAL_SOURCE_QA_STALE_AFTER_HEAD_DRIFT",
      "last_source_qa_evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177#issuecomment-6510971410",
      "report_gates": {
        "A": null,
        "B": null,
        "C": null,
        "D": null,
        "E": null
      },
      "registry_scope": "current"
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
      "id": "6ae2af347fbc81918ddafed356511243",
      "title": "NOX V16 G3-B PACK02",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "4609e8f3-4478-832e-88a2-63afc92da2ba",
      "last_run_started_at": "2026-10-29T23:30:31.411132Z",
      "last_run_completed_at": "2026-10-29T23:40:05.476334Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2af008eac8191a03526f290b801c6",
      "title": "NOX V16 G3-A P04 GPU/RAG",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "b2f7a51e-95c8-832d-add6-1abcbd92317d",
      "last_run_started_at": "2026-10-29T23:25:04.582050Z",
      "last_run_completed_at": "2026-10-29T23:35:41.555083Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2aef9c3fc81918fd4c4b0041207ef",
      "title": "NOX V16 G2-B P02 Voice",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "90037171-ed7c-832a-b1c9-c3052a0a2b8e",
      "last_run_started_at": "2026-10-29T23:10:33.294216Z",
      "last_run_completed_at": "2026-10-29T23:13:25.800342Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2aecc59f88191a10a9342f8a1930c",
      "title": "NOX V16 G1-B NSIS source",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "d02feff0-f568-8323-829a-0875d0c10674",
      "last_run_started_at": "2026-10-29T23:17:57.270091Z",
      "last_run_completed_at": "2026-10-29T23:22:46.921696Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2af03ddd88191b39ad44b379cc3dc",
      "title": "NOX V16 G4-B T08 блокеры",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "2237d416-612c-832b-99a2-2b327093c46e",
      "last_run_started_at": "2026-10-29T22:53:48.172487Z",
      "last_run_completed_at": "2026-10-29T23:00:12.272016Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2af4f6c448191932f01b35fa364c1",
      "title": "NOX V16 G5-A T02 журнал",
      "enabled": true,
      "kind": "source_support",
      "recorded_status": "in_progress",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "1848df49-67a4-8329-b3df-c947b699518b",
      "last_run_started_at": "2026-10-29T23:39:16.385732Z",
      "last_run_completed_at": null,
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2af31f2988191902bae4aaec2635e",
      "title": "NOX V16 G2-A Host50",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "51b0c6d2-6f50-832a-87c0-53605cc99b57",
      "last_run_started_at": "2026-10-29T23:17:21.029329Z",
      "last_run_completed_at": "2026-10-29T23:20:08.092436Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2aefe3c248191a7131fc9876611e6",
      "title": "NOX V16 G2-C P03 Queue",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "91b07992-5c50-8326-a640-c130b7ac9ba6",
      "last_run_started_at": "2026-10-29T23:12:18.264085Z",
      "last_run_completed_at": "2026-10-29T23:20:05.302500Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2af28e4b8819192bbf6bb3857cc84",
      "title": "NOX V16 G1-A P01–P03",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "7e0f826e-9670-8327-ba68-a1eb7c68e6af",
      "last_run_started_at": "2026-10-29T22:58:33.047229Z",
      "last_run_completed_at": "2026-10-29T23:01:53.384296Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2aefbde94819183730a2ed3cad78c",
      "title": "NOX V16 G1-C P04–P05",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "0bfbf14b-fdd0-832a-be13-b4c4f7be72b4",
      "last_run_started_at": "2026-10-29T22:57:33.366189Z",
      "last_run_completed_at": "2026-10-29T23:00:35.581614Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2aef4bbc081918693b0552743bd0d",
      "title": "NOX V16 G5-B T10 SOURCE_READY",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "fe6fcc1a-2518-8326-9676-94d8d196dc0e",
      "last_run_started_at": "2026-10-29T22:16:12.791283Z",
      "last_run_completed_at": "2026-10-29T22:27:13.206933Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2af2b1bcc8191a4d15cb8f6f9d25b",
      "title": "NOX V16 G5-C T11 GitLab READY",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "c08e0e9d-cddc-8321-8b12-ee66f8883af3",
      "last_run_started_at": "2026-10-29T21:31:35.547863Z",
      "last_run_completed_at": "2026-10-29T21:40:29.528803Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2af2f84088191ba04843861edf73b",
      "title": "NOX V16 G4-C T09 freeze",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "a89eb080-c6c4-8330-a295-ed6674e9ec6c",
      "last_run_started_at": "2026-10-29T22:03:43.025859Z",
      "last_run_completed_at": "2026-10-29T22:11:35.030122Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2af2d4f8c81919951564c5eb2ddf6",
      "title": "NOX V16 G4-A T07 NOLOSS",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "a4cd03a2-af88-832a-ba7e-25e0cfb892aa",
      "last_run_started_at": "2026-10-29T21:50:56.926222Z",
      "last_run_completed_at": "2026-10-29T21:58:04.742167Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae2aef78ba881919e6022c1103959a2",
      "title": "NOX V16 G3-C T06 интегратор",
      "enabled": false,
      "kind": "source_support",
      "recorded_status": "failed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "last_run_id": "7c83ca61-7c98-8320-ab52-49660ca305aa",
      "last_run_started_at": "2026-10-29T21:42:13.744075Z",
      "last_run_completed_at": "2026-10-29T21:48:20.206662Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA",
      "registry_scope": "current"
    },
    {
      "id": "6ae342e4a0248191954f95217ebee33b",
      "title": "NOX V16 T13 E07 PAUSED",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "3c340092-b638-8326-b8ab-acf94633b47b",
      "last_run_started_at": "2026-10-29T14:31:30.229533Z",
      "last_run_completed_at": "2026-10-29T14:32:13.180463Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    },
    {
      "id": "6ae342df73788191b8d8fb6b179dad46",
      "title": "NOX V16 T12 BUILD PAUSED",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "ac4ef882-92dc-8331-a8cc-a86154c59128",
      "last_run_started_at": "2026-10-29T14:30:42.254922Z",
      "last_run_completed_at": "2026-10-29T14:31:18.211941Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    },
    {
      "id": "6ae342e74028819197da844e6468b640",
      "title": "NOX V16 T14 RELEASE FIX PAUSED",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "8409fd9e-c1b4-832b-a3b7-a76e8a08d709",
      "last_run_started_at": "2026-10-29T14:27:49.862070Z",
      "last_run_completed_at": "2026-10-29T14:28:25.521499Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    },
    {
      "id": "6ae342ea03d48191ad25ba7bcf4e5c8a",
      "title": "NOX V16 T15 RELEASE PAUSED",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "019af9cf-4344-832d-89ce-7ded5b65a288",
      "last_run_started_at": "2026-10-29T14:26:56.322252Z",
      "last_run_completed_at": "2026-10-29T14:27:25.501720Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    },
    {
      "id": "6ae16157f7388191a5d0634fb13d3d01",
      "title": "NOX W4·02 P05 Events SPACE",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "8dd3c97f-cc98-832e-9055-1b0a6daa4b3d",
      "last_run_started_at": "2026-10-28T23:03:22.342308Z",
      "last_run_completed_at": "2026-10-28T23:11:08.953945Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    },
    {
      "id": "6ae1618c11908191b891c76f2ffa4238",
      "title": "NOX W4·03 SPACE Mobile Bridge",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "859890d8-d354-8332-9ee9-dade73b3dccb",
      "last_run_started_at": "2026-10-28T23:05:15.492936Z",
      "last_run_completed_at": "2026-10-28T23:10:52.626091Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    },
    {
      "id": "6ae161819d9481919f3dbb52cbfd9e62",
      "title": "NOX W1·01 SourceLock 729",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "f3e5b522-84a0-8333-8a3d-1f03fa69a215",
      "last_run_started_at": "2026-10-28T22:35:22.586837Z",
      "last_run_completed_at": "2026-10-28T22:42:43.443425Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    },
    {
      "id": "6ae161b0c5f88191ada31d0e3b12364d",
      "title": "NOX W1·03 Security NO-LOSS",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "67b208e4-0748-8328-acef-a2ddedc4ffd0",
      "last_run_started_at": "2026-10-28T22:30:05.631153Z",
      "last_run_completed_at": "2026-10-28T22:38:53.741620Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    },
    {
      "id": "6ae1618459288191b6be333b6af9c89b",
      "title": "NOX W1·02 Native Host50",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "879ede72-4b74-832e-927e-fa97551930a4",
      "last_run_started_at": "2026-10-28T22:30:04.889906Z",
      "last_run_completed_at": "2026-10-28T22:38:42.485867Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    },
    {
      "id": "6ae1614c140881918783372458d52f29",
      "title": "NOX W2·01 D02 WOW E01",
      "enabled": false,
      "kind": "legacy_or_future",
      "recorded_status": "completed",
      "status_scope": "SCHEDULER_RUN_NOT_QA_ACCEPTANCE",
      "scheduler_snapshot_at": "2026-10-29T23:50:00.602Z",
      "registry_scope": "historical",
      "last_run_id": "cd277714-0cec-8325-9843-714885db3dee",
      "last_run_started_at": "2026-10-28T22:46:49.591428Z",
      "last_run_completed_at": "2026-10-28T22:52:51.304022Z",
      "run_receipt_scope": "AUTHENTICATED_PEEK_NOT_PRODUCT_QA"
    }
  ],
  "errors": {
    "OPEN": 5,
    "FIX_APPLIED_UNVERIFIED": 4,
    "VERIFIED_CLOSED": 2,
    "total": 11,
    "history_complete": false,
    "blob": "45a684f905d4c7f1bd04266d6c080e69a3dacee1"
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
  "gate_status": "HISTORIC_GATES_NOT_REATTESTED_ON_852ccc1611d99afaf48e7fc4c33a5509d385f9a9",
  "notes": [
    "Ручные — главные владельцы. AUTO — поддержка.",
    "Количество ручных и AUTO выводится из данных, а не зашито в интерфейсе.",
    "Общий процент продукта Н/Д: нет полного доказанного frozen TaskID ledger.",
    "Прежние gate x/n исторические, не подтверждены на текущем HEAD.",
    "R27: PR162 fc9182f519c64f5f4e54a52ded9b2575c0bcff9a tree 5e0d9127f6b5a57f6bda47a6fd213866689d4fae at snapshot, not a live connection. Error register a8f71dd3e12906120fd6ee52386cbd549615a2eb, 11 entries 5/4/2, history incomplete.",
    "R27: 25 known NOX automations, 15 active supporting enabled, 10 archive/future disabled. T06 provider last run FAILED while existing Git source persists; no auto re-run.",
    "R27: Manual №1/№3/№2 approach bars N/D without per-approach independent receipts. QA_ACCEPTED delta=0. SOURCE_READY/BUILD NOT_AUTHORIZED.",
    "R33 SOURCE DELTA: Compared confirmed last CAS HEAD fc9182f5... to current pinned Git HEAD/tree; shared register R33 run_delta CAS 0451aa5c...; no QA_ACCEPTED. Scheduler 15 owner-roster current: 10 enabled/5 disabled; 10 historical disabled. Disabled current IDs left unchanged; source-host route 40/50 vs native acceptance N/D. This is NOT live UI.",
    "R34 2026-10-29T23:50:00.602Z: PR162 852ccc1611d99afaf48e7fc4c33a5509d385f9a9, tree 17bdb7db4ccf0138f5f41356009215dea37077f2, register 45a684f905d4c7f1bd04266d6c080e69a3dacee1. New source commits since R33; manual-2 R36 QA on older HEAD only, acceptance 0.",
    "R34 authenticated schedule 25: active roster 15 (6 on / 9 off), archive 10 off; no automatic re-enabling."
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
      "qa_accepted": false,
      "head_validation": "STALE_OR_UNVERIFIED_852ccc1611d99afaf48e7fc4c33a5509d385f9a9"
    },
    {
      "id": "P03/ModelCenter",
      "block": "P03",
      "owner": "1",
      "qa": "2",
      "stage": "INTEGRATED_SOURCE_ONLY",
      "evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/dbfd22340427e35440242f144aa1730833661695",
      "note": "P03 reviewedTag typeof id guard in blob 2e5830..., but separate consent snapshot invalidation still unverified; T08 independent current-head QA pending.",
      "qa_accepted": false,
      "head_validation": "STALE_OR_UNVERIFIED_852ccc1611d99afaf48e7fc4c33a5509d385f9a9"
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
      "qa_accepted": false,
      "head_validation": "STALE_OR_UNVERIFIED_852ccc1611d99afaf48e7fc4c33a5509d385f9a9"
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
      "qa_accepted": false,
      "head_validation": "STALE_OR_UNVERIFIED_852ccc1611d99afaf48e7fc4c33a5509d385f9a9"
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
      "qa_accepted": false,
      "head_validation": "STALE_OR_UNVERIFIED_852ccc1611d99afaf48e7fc4c33a5509d385f9a9"
    },
    {
      "id": "P05/smoke",
      "block": "P05",
      "owner": "3",
      "qa": "2",
      "stage": "SOURCE_PREPARED",
      "evidence": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177#issuecomment-6508215492",
      "note": "Donor source/test smoke only, targeted .NET and independent QA NOT_RUN.",
      "qa_accepted": false,
      "head_validation": "STALE_OR_UNVERIFIED_852ccc1611d99afaf48e7fc4c33a5509d385f9a9"
    }
  ],
  "tasks_are_full_ledger": false,
  "tree": "17bdb7db4ccf0138f5f41356009215dea37077f2",
  "product_percent": null,
  "automation_counts": {
    "total": 25,
    "defined_in_scheduler": 25,
    "current_roster": 15,
    "current_enabled_confirmed": 6,
    "current_disabled": 9,
    "historical": 10,
    "unassigned": 0,
    "missing_in_scheduler": 0,
    "active_primary_support": 15,
    "active_enabled": 6,
    "active_disabled": 9,
    "all_enabled": 6,
    "all_disabled": 19,
    "archived_or_future": 10
  },
  "manual_count": 3,
  "manual_manifest_ref": "coordination/r25/R25_MANUAL_FIRST_OTCH1_CONTROL.md",
  "last_t02_journal": {
    "run_id": "NOX-V16-T02C-G5A-20261030T023917MSK-R34-FINITE-JOURNAL",
    "commit": "b4dfcf3563cf705b598801fe29778a3db912d316",
    "blob": "45a684f905d4c7f1bd04266d6c080e69a3dacee1",
    "master": "NO_WRITE_R34",
    "lessons": "NO_WRITE_R34",
    "e06": "LAST_KNOWN_FAILED_PRECONDITION",
    "receipt": "https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/b4dfcf3563cf705b598801fe29778a3db912d316/coordination/ops/NOX_V16_ACTIVE_ERROR_REGISTER.json",
    "accepted_delta": 0
  },
  "host50": {
    "historical_source_hold": 13,
    "source_unbound": 10,
    "native_pending": 14,
    "not_equivalent": true,
    "source_bound": 40
  },
  "accepted_delta_new": 0,
  "executor_inventory_observed_at": "2026-10-29T23:50:00.602Z",
  "snapshot_type": "AUTHENTICATED_EXECUTOR_INVENTORY_ONLY_NOT_PRODUCT_QA",
  "executor_registry_notice": "The scheduler is authoritative for enabled and last run; independent T08 only can sign product QA."
};

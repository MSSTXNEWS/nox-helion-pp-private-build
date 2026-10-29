/* NOX R26 authenticated snapshot export; not a live API. Update by T02 with readback. */
window.NOX_CONTROL_DATA={
  "schema": "NOX_CONTROL_CENTER_R26_SNAPSHOT_V1",
  "observed_at": "2026-10-29",
  "source": "GitHub PR162 + Automations list + T02 Git register",
  "source_mode": "SNAPSHOT_NOT_LIVE",
  "repository": "MSSTXNEWS/nox-helion-pp-private-build",
  "pr": 162,
  "head": "1f5737bdb8d41019dd21cb1b0ec41118186fb8f9",
  "commit_count": 328,
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
      "phase": "INTEGRATED_UNVERIFIED",
      "gate": {
        "done": null,
        "total": null
      },
      "approaches": {
        "done": null,
        "total": 10
      },
      "description": "Все основные функции, общий HEAD и будущая разрешённая сборка"
    },
    {
      "id": "3",
      "role": "P04/P05 DEVELOPER",
      "name": "Разработчик моделей и SPACE",
      "blocks": [
        "P04",
        "P05"
      ],
      "phase": "PATCH_PREPARED",
      "gate": {
        "done": null,
        "total": null
      },
      "approaches": {
        "done": null,
        "total": 10
      },
      "description": "Основные исходники P04/P05 и подготовленные владельческие изменения"
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
      "phase": "QA_PENDING",
      "gate": {
        "done": null,
        "total": null
      },
      "approaches": {
        "done": null,
        "total": 10
      },
      "description": "Независимая исходная QA на точном HEAD; затем E07 после сборки"
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
      "kind": "source_support"
    },
    {
      "id": "6ae2aefe3c248191a7131fc9876611e6",
      "title": "NOX V16 G2-C P03 Queue",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2af2b1bcc8191a4d15cb8f6f9d25b",
      "title": "NOX V16 G5-C T11 GitLab READY",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2aef4bbc081918693b0552743bd0d",
      "title": "NOX V16 G5-B T10 SOURCE_READY",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2af2f84088191ba04843861edf73b",
      "title": "NOX V16 G4-C T09 freeze",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2af2d4f8c81919951564c5eb2ddf6",
      "title": "NOX V16 G4-A T07 NOLOSS",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2af347fbc81918ddafed356511243",
      "title": "NOX V16 G3-B PACK02",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2af008eac8191a03526f290b801c6",
      "title": "NOX V16 G3-A P04 GPU/RAG",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2aef9c3fc81918fd4c4b0041207ef",
      "title": "NOX V16 G2-B P02 Voice",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2af31f2988191902bae4aaec2635e",
      "title": "NOX V16 G2-A Host50",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2aecc59f88191a10a9342f8a1930c",
      "title": "NOX V16 G1-B NSIS source",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2aefbde94819183730a2ed3cad78c",
      "title": "NOX V16 G1-C P04–P05",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2af28e4b8819192bbf6bb3857cc84",
      "title": "NOX V16 G1-A P01–P03",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2af03ddd88191b39ad44b379cc3dc",
      "title": "NOX V16 G4-B T08 блокеры",
      "enabled": true,
      "kind": "source_support"
    },
    {
      "id": "6ae2aef78ba881919e6022c1103959a2",
      "title": "NOX V16 G3-C T06 интегратор",
      "enabled": false,
      "kind": "source_support"
    },
    {
      "id": "6ae342e4a0248191954f95217ebee33b",
      "title": "NOX V16 T13 E07 PAUSED",
      "enabled": false,
      "kind": "legacy_or_future"
    },
    {
      "id": "6ae342df73788191b8d8fb6b179dad46",
      "title": "NOX V16 T12 BUILD PAUSED",
      "enabled": false,
      "kind": "legacy_or_future"
    },
    {
      "id": "6ae342e74028819197da844e6468b640",
      "title": "NOX V16 T14 RELEASE FIX PAUSED",
      "enabled": false,
      "kind": "legacy_or_future"
    },
    {
      "id": "6ae342ea03d48191ad25ba7bcf4e5c8a",
      "title": "NOX V16 T15 RELEASE PAUSED",
      "enabled": false,
      "kind": "legacy_or_future"
    },
    {
      "id": "6ae16157f7388191a5d0634fb13d3d01",
      "title": "NOX W4·02 P05 Events SPACE",
      "enabled": false,
      "kind": "legacy_or_future"
    },
    {
      "id": "6ae1618c11908191b891c76f2ffa4238",
      "title": "NOX W4·03 SPACE Mobile Bridge",
      "enabled": false,
      "kind": "legacy_or_future"
    },
    {
      "id": "6ae161819d9481919f3dbb52cbfd9e62",
      "title": "NOX W1·01 SourceLock 729",
      "enabled": false,
      "kind": "legacy_or_future"
    },
    {
      "id": "6ae161b0c5f88191ada31d0e3b12364d",
      "title": "NOX W1·03 Security NO-LOSS",
      "enabled": false,
      "kind": "legacy_or_future"
    },
    {
      "id": "6ae1618459288191b6be333b6af9c89b",
      "title": "NOX W1·02 Native Host50",
      "enabled": false,
      "kind": "legacy_or_future"
    },
    {
      "id": "6ae1614c140881918783372458d52f29",
      "title": "NOX W2·01 D02 WOW E01",
      "enabled": false,
      "kind": "legacy_or_future"
    }
  ],
  "errors": {
    "OPEN": 5,
    "FIX_APPLIED_UNVERIFIED": 4,
    "VERIFIED_CLOSED": 2,
    "total": 11,
    "history_complete": false,
    "blob": "967932904afa9caa743fb33b29bbd807c59f714b"
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
  "gate_status": "HISTORICAL_NOT_REVALIDATED",
  "notes": [
    "Ручные — главные владельцы. AUTO — поддержка.",
    "Количество ручных и AUTO выводится из данных, а не зашито в интерфейсе.",
    "Общий процент продукта Н/Д: нет полного доказанного frozen TaskID ledger.",
    "Прежние gate x/n исторические, не подтверждены на текущем HEAD."
  ]
};

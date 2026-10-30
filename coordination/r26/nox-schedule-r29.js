/* NOX R29 authenticated scheduler status snapshot; last ACTUAL run first. */
window.NOX_SCHEDULE_SNAPSHOT={
  "schema": "NOX_R29_SCHEDULE_SNAPSHOT_V1",
  "observed_at": "2026-10-30T00:36:24Z",
  "last_run_observed_at": "2026-10-30T00:36:24Z",
  "complete": true,
  "missing_ids": [],
  "source": "authenticated individual Automations.peek for all 25 IDs matched to owner-approved roster; snapshot observed 2026-10-30T00:36:24Z, NOT LIVE",
  "tasks": [
    {
      "id": "6ae2af2b1bcc8191a4d15cb8f6f9d25b",
      "title": "NOX V16 G5-C T11 GitLab READY",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T232700\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=27;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T21:31:35.547863Z",
        "completed_at": "2026-10-29T21:40:29.528803Z",
        "run_id": "c08e0e9d-cddc-8321-8b12-ee66f8883af3"
      }
    },
    {
      "id": "6ae2aef4bbc081918693b0552743bd0d",
      "title": "NOX V16 G5-B T10 SOURCE_READY",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T231500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=15;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T22:16:12.791283Z",
        "completed_at": "2026-10-29T22:27:13.206933Z",
        "run_id": "fe6fcc1a-2518-8326-9676-94d8d196dc0e"
      }
    },
    {
      "id": "6ae2af4f6c448191932f01b35fa364c1",
      "title": "NOX V16 G5-A T02 журнал",
      "enabled": true,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T233900\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=39;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "in_progress",
        "started_at": "2026-10-30T00:36:23.910283Z",
        "completed_at": null,
        "run_id": "b7e5d839-bd18-8333-b282-f98a39a97a6a"
      }
    },
    {
      "id": "6ae2af2f84088191ba04843861edf73b",
      "title": "NOX V16 G4-C T09 freeze",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T230300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=3;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T22:03:43.025859Z",
        "completed_at": "2026-10-29T22:11:35.030122Z",
        "run_id": "a89eb080-c6c4-8330-a295-ed6674e9ec6c"
      }
    },
    {
      "id": "6ae2af03ddd88191b39ad44b379cc3dc",
      "title": "NOX V16 G4-B T08 блокеры",
      "enabled": true,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T225100\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=51;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T23:49:04.315575Z",
        "completed_at": "2026-10-29T23:55:59.191926Z",
        "run_id": "9aa3aba3-9f94-832c-ad6c-46ba6575c78c"
      }
    },
    {
      "id": "6ae2af2d4f8c81919951564c5eb2ddf6",
      "title": "NOX V16 G4-A T07 NOLOSS",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T224800\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=48;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T21:50:56.926222Z",
        "completed_at": "2026-10-29T21:58:04.742167Z",
        "run_id": "a4cd03a2-af88-832a-ba7e-25e0cfb892aa"
      }
    },
    {
      "id": "6ae2aef78ba881919e6022c1103959a2",
      "title": "NOX V16 G3-C T06 интегратор",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T223900\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=39;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "failed",
        "started_at": "2026-10-30T00:07:54.235418Z",
        "completed_at": "2026-10-30T00:28:02.895508Z",
        "run_id": "316cc06a-8dac-8330-a41b-0ac5b21c08eb"
      }
    },
    {
      "id": "6ae2af347fbc81918ddafed356511243",
      "title": "NOX V16 G3-B PACK02",
      "enabled": true,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T222600\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=26;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-30T00:28:00.986374Z",
        "completed_at": "2026-10-30T00:34:23.784828Z",
        "run_id": "b5222ebd-c64c-8324-b92e-cc6f4008b7ee"
      }
    },
    {
      "id": "6ae2af008eac8191a03526f290b801c6",
      "title": "NOX V16 G3-A P04 GPU/RAG",
      "enabled": true,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T222600\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=26;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-30T00:24:35.936078Z",
        "completed_at": "2026-10-30T00:33:14.251920Z",
        "run_id": "646644f9-e50c-8323-9c9f-ba8dfd65b63e"
      }
    },
    {
      "id": "6ae2aefe3c248191a7131fc9876611e6",
      "title": "NOX V16 G2-C P03 Queue",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T221300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=13;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T23:12:18.264085Z",
        "completed_at": "2026-10-29T23:20:05.302500Z",
        "run_id": "91b07992-5c50-8326-a640-c130b7ac9ba6"
      }
    },
    {
      "id": "6ae2aef9c3fc81918fd4c4b0041207ef",
      "title": "NOX V16 G2-B P02 Voice",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T221300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=13;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-30T00:14:26.028148Z",
        "completed_at": "2026-10-30T00:16:53.610599Z",
        "run_id": "a5a033b8-0280-8320-a74d-9d6cb59a652d"
      }
    },
    {
      "id": "6ae2af31f2988191902bae4aaec2635e",
      "title": "NOX V16 G2-A Host50",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T221300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=13;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T23:17:21.029329Z",
        "completed_at": "2026-10-29T23:20:08.092436Z",
        "run_id": "51b0c6d2-6f50-832a-87c0-53605cc99b57"
      }
    },
    {
      "id": "6ae2aefbde94819183730a2ed3cad78c",
      "title": "NOX V16 G1-C P04–P05",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T220100\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=1;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T22:57:33.366189Z",
        "completed_at": "2026-10-29T23:00:35.581614Z",
        "run_id": "0bfbf14b-fdd0-832a-be13-b4c4f7be72b4"
      }
    },
    {
      "id": "6ae2aecc59f88191a10a9342f8a1930c",
      "title": "NOX V16 G1-B NSIS source",
      "enabled": true,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T221300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=13;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-30T00:08:18.299390Z",
        "completed_at": "2026-10-30T00:10:40.776710Z",
        "run_id": "2ec3e97c-1a88-832d-969e-1f911eb54f72"
      }
    },
    {
      "id": "6ae2af28e4b8819192bbf6bb3857cc84",
      "title": "NOX V16 G1-A P01–P03",
      "enabled": false,
      "scope": "current",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T220100\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=1;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T22:58:33.047229Z",
        "completed_at": "2026-10-29T23:01:53.384296Z",
        "run_id": "7e0f826e-9670-8327-ba68-a1eb7c68e6af"
      }
    },
    {
      "id": "6ae342e4a0248191954f95217ebee33b",
      "title": "NOX V16 T13 E07 PAUSED",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART:20261029T173000\nRRULE:FREQ=HOURLY\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T14:31:30.229533Z",
        "completed_at": "2026-10-29T14:32:13.180463Z",
        "run_id": "3c340092-b638-8326-b8ab-acf94633b47b"
      }
    },
    {
      "id": "6ae342df73788191b8d8fb6b179dad46",
      "title": "NOX V16 T12 BUILD PAUSED",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART:20261029T173000\nRRULE:FREQ=HOURLY\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T14:30:42.254922Z",
        "completed_at": "2026-10-29T14:31:18.211941Z",
        "run_id": "ac4ef882-92dc-8331-a8cc-a86154c59128"
      }
    },
    {
      "id": "6ae342e74028819197da844e6468b640",
      "title": "NOX V16 T14 RELEASE FIX PAUSED",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART:20261029T173000\nRRULE:FREQ=HOURLY\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T14:27:49.862070Z",
        "completed_at": "2026-10-29T14:28:25.521499Z",
        "run_id": "8409fd9e-c1b4-832b-a3b7-a76e8a08d709"
      }
    },
    {
      "id": "6ae342ea03d48191ad25ba7bcf4e5c8a",
      "title": "NOX V16 T15 RELEASE PAUSED",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART:20261029T173000\nRRULE:FREQ=HOURLY\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-29T14:26:56.322252Z",
        "completed_at": "2026-10-29T14:27:25.501720Z",
        "run_id": "019af9cf-4344-832d-89ce-7ded5b65a288"
      }
    },
    {
      "id": "6ae16157f7388191a5d0634fb13d3d01",
      "title": "NOX W4·02 P05 Events SPACE",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T220500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=5;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-28T23:03:22.342308Z",
        "completed_at": "2026-10-28T23:11:08.953945Z",
        "run_id": "8dd3c97f-cc98-832e-9055-1b0a6daa4b3d"
      }
    },
    {
      "id": "6ae1618c11908191b891c76f2ffa4238",
      "title": "NOX W4·03 SPACE Mobile Bridge",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T220500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=5;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-28T23:05:15.492936Z",
        "completed_at": "2026-10-28T23:10:52.626091Z",
        "run_id": "859890d8-d354-8332-9ee9-dade73b3dccb"
      }
    },
    {
      "id": "6ae161819d9481919f3dbb52cbfd9e62",
      "title": "NOX W1·01 SourceLock 729",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T213500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=35;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-28T22:35:22.586837Z",
        "completed_at": "2026-10-28T22:42:43.443425Z",
        "run_id": "f3e5b522-84a0-8333-8a3d-1f03fa69a215"
      }
    },
    {
      "id": "6ae161b0c5f88191ada31d0e3b12364d",
      "title": "NOX W1·03 Security NO-LOSS",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T213500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=35;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-28T22:30:05.631153Z",
        "completed_at": "2026-10-28T22:38:53.741620Z",
        "run_id": "67b208e4-0748-8328-acef-a2ddedc4ffd0"
      }
    },
    {
      "id": "6ae1618459288191b6be333b6af9c89b",
      "title": "NOX W1·02 Native Host50",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T213500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=35;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-28T22:30:04.889906Z",
        "completed_at": "2026-10-28T22:38:42.485867Z",
        "run_id": "879ede72-4b74-832e-927e-fa97551930a4"
      }
    },
    {
      "id": "6ae1614c140881918783372458d52f29",
      "title": "NOX W2·01 D02 WOW E01",
      "enabled": false,
      "scope": "historical",
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T214500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=45;BYSECOND=0\nEND:VEVENT",
      "last_run": {
        "status": "completed",
        "started_at": "2026-10-28T22:46:49.591428Z",
        "completed_at": "2026-10-28T22:52:51.304022Z",
        "run_id": "cd277714-0cec-8325-9843-714885db3dee"
      }
    }
  ]
};

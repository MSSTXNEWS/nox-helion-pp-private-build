/* Observed actual run timestamps via authenticated Automations.peek, UTC. Last actual first, schedule secondary. Snapshot must be refreshed by T02. */
window.NOX_SCHEDULE_SNAPSHOT={
  "schema": "NOX_R29_SCHEDULE_SNAPSHOT_V1",
  "source": "authenticated Automations list; next run derived as plan when next_run_time is null",
  "observed_at": "2026-10-30",
  "tasks": [
    {
      "id": "6ae2af2b1bcc8191a4d15cb8f6f9d25b",
      "title": "NOX V16 G5-C T11 GitLab READY",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T232700\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=27;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T20:36:37.223313+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:31:35.547863Z",
        "completed_at": null,
        "status": "in_progress"
      }
    },
    {
      "id": "6ae2aef4bbc081918693b0552743bd0d",
      "title": "NOX V16 G5-B T10 SOURCE_READY",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T231500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=15;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:27:35.949072+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:16:04.213568Z",
        "completed_at": "2026-10-29T21:27:33.645013Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae2af4f6c448191932f01b35fa364c1",
      "title": "NOX V16 G5-A T02 журнал",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T233900\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=39;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:23:47.816742+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:34:14.833408Z",
        "completed_at": null,
        "status": "in_progress"
      }
    },
    {
      "id": "6ae2af2f84088191ba04843861edf73b",
      "title": "NOX V16 G4-C T09 freeze",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T230300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=3;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:13:33.204221+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:05:57.330218Z",
        "completed_at": "2026-10-29T21:13:29.366720Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae2af03ddd88191b39ad44b379cc3dc",
      "title": "NOX V16 G4-B T08 блокеры",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T225100\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=51;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:21:10.699884+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:34:34.096154Z",
        "completed_at": null,
        "status": "in_progress"
      }
    },
    {
      "id": "6ae2af2d4f8c81919951564c5eb2ddf6",
      "title": "NOX V16 G4-A T07 NOLOSS",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T224800\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=48;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T20:58:10.182584+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T20:49:25.201805Z",
        "completed_at": "2026-10-29T20:58:06.939839Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae2aef78ba881919e6022c1103959a2",
      "title": "NOX V16 G3-C T06 интегратор",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T223900\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=39;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T15:05:52.215559+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T20:28:38.233731Z",
        "completed_at": "2026-10-29T20:41:47.829001Z",
        "status": "failed"
      }
    },
    {
      "id": "6ae2af347fbc81918ddafed356511243",
      "title": "NOX V16 G3-B PACK02",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T222600\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=26;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T20:37:16.909797+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:29:20.830139Z",
        "completed_at": null,
        "status": "in_progress"
      }
    },
    {
      "id": "6ae2af008eac8191a03526f290b801c6",
      "title": "NOX V16 G3-A P04 GPU/RAG",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T222600\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=26;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T20:32:14.348460+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:29:50.452114Z",
        "completed_at": "2026-10-29T21:39:07.826952Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae2aefe3c248191a7131fc9876611e6",
      "title": "NOX V16 G2-C P03 Queue",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T221300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=13;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:22:35.201720+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:12:47.239975Z",
        "completed_at": "2026-10-29T21:22:33.644361Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae2aef9c3fc81918fd4c4b0041207ef",
      "title": "NOX V16 G2-B P02 Voice",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T221300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=13;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:24:38.014025+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:13:03.022058Z",
        "completed_at": "2026-10-29T21:24:35.670038Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae2af31f2988191902bae4aaec2635e",
      "title": "NOX V16 G2-A Host50",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T221300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=13;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:22:13.841313+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:34:04.328874Z",
        "completed_at": null,
        "status": "in_progress"
      }
    },
    {
      "id": "6ae2aefbde94819183730a2ed3cad78c",
      "title": "NOX V16 G1-C P04–P05",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T220100\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=1;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:11:31.015069+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:02:36.960249Z",
        "completed_at": "2026-10-29T21:11:26.648373Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae2aecc59f88191a10a9342f8a1930c",
      "title": "NOX V16 G1-B NSIS source",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T221300\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=13;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:30:30.775686+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:16:09.729016Z",
        "completed_at": "2026-10-29T21:30:27.934440Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae2af28e4b8819192bbf6bb3857cc84",
      "title": "NOX V16 G1-A P01–P03",
      "enabled": true,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261029T220100\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=1;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T21:08:19.210308+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T21:33:52.300793Z",
        "completed_at": null,
        "status": "in_progress"
      }
    },
    {
      "id": "6ae342e4a0248191954f95217ebee33b",
      "title": "NOX V16 T13 E07 PAUSED",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART:20261029T173000\nRRULE:FREQ=HOURLY\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T14:32:15.002169+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T14:31:30.229533Z",
        "completed_at": "2026-10-29T14:32:13.180463Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae342df73788191b8d8fb6b179dad46",
      "title": "NOX V16 T12 BUILD PAUSED",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART:20261029T173000\nRRULE:FREQ=HOURLY\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T14:31:19.701459+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T14:30:42.254922Z",
        "completed_at": "2026-10-29T14:31:18.211941Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae342e74028819197da844e6468b640",
      "title": "NOX V16 T14 RELEASE FIX PAUSED",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART:20261029T173000\nRRULE:FREQ=HOURLY\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T14:28:27.038516+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T14:27:49.862070Z",
        "completed_at": "2026-10-29T14:28:25.521499Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae342ea03d48191ad25ba7bcf4e5c8a",
      "title": "NOX V16 T15 RELEASE PAUSED",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART:20261029T173000\nRRULE:FREQ=HOURLY\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-29T14:27:27.725764+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-29T14:26:56.322252Z",
        "completed_at": "2026-10-29T14:27:25.501720Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae16157f7388191a5d0634fb13d3d01",
      "title": "NOX W4·02 P05 Events SPACE",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T220500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=5;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-28T23:11:11.647488+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-28T23:03:22.342308Z",
        "completed_at": "2026-10-28T23:11:08.953945Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae1618c11908191b891c76f2ffa4238",
      "title": "NOX W4·03 SPACE Mobile Bridge",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T220500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=5;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-28T23:10:54.552245+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-28T23:05:15.492936Z",
        "completed_at": "2026-10-28T23:10:52.626091Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae161819d9481919f3dbb52cbfd9e62",
      "title": "NOX W1·01 SourceLock 729",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T213500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=35;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-28T22:42:45.116265+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-28T22:35:22.586837Z",
        "completed_at": "2026-10-28T22:42:43.443425Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae161b0c5f88191ada31d0e3b12364d",
      "title": "NOX W1·03 Security NO-LOSS",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T213500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=35;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-28T22:38:55.196647+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-28T22:30:05.631153Z",
        "completed_at": "2026-10-28T22:38:53.741620Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae1618459288191b6be333b6af9c89b",
      "title": "NOX W1·02 Native Host50",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T213500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=35;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-28T22:38:44.181590+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-28T22:30:04.889906Z",
        "completed_at": "2026-10-28T22:38:42.485867Z",
        "status": "completed"
      }
    },
    {
      "id": "6ae1614c140881918783372458d52f29",
      "title": "NOX W2·01 D02 WOW E01",
      "enabled": false,
      "schedule": "BEGIN:VEVENT\nDTSTART;TZID=Europe/Moscow:20261028T214500\nRRULE:FREQ=HOURLY;INTERVAL=1;BYMINUTE=45;BYSECOND=0\nEND:VEVENT",
      "next_run_time": null,
      "last_run_time": "2026-10-28T22:52:52.884202+00:00",
      "timezone": "Europe/Moscow",
      "last_run": {
        "started_at": "2026-10-28T22:46:49.591428Z",
        "completed_at": "2026-10-28T22:52:51.304022Z",
        "status": "completed"
      }
    }
  ],
  "last_run_observed_at": "2026-10-29T21:41:00Z"
};

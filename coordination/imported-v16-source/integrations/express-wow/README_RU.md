# NOX V16 · EXPRESS WOW / Creative · R12

SourceLock base commit: 833a37bca2930e0cb9b272ae07f5d6545e3d5096. Все исходники P01–P05, 56 donor WOW, оригинальный D02 и история остаются в объединённом PR162.

ONE ACTIVE E01 D02 renderer: proposals/NOX-CINEMA-FX/nox-cinema.mjs в git и Assets/creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.mjs в staged R13. Archived PR30 сохраняется в Assets/creative/wow200/legacy/d02-pr30, но не импортируется.

One-shot apply: python integrations/express-wow/apply_express.py --r13 R13/R11 --repo UNIFIED --out WORK/NOX-WOW-EXPRESS

Стадия применяет Creative+WOW к отдельной копии R13 с SHA D02 и receipt. Нет перезаписи main, P02–P05, SQLite, LOra, original EXE, NSIS. Статус SOURCE_ONLY пока native Windows/E07 не пройдены.

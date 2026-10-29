# NOX E02 C12 · BLOCKER IDENTIFIED AND GUARDED

Existing P02Store.add_message in PR13 uses `INSERT INTO p02_messages VALUES(?,?,?,?,?)`. SQLite V2 adds `stable_seq`, so old positional writes fail. Reproduced as negative regression test. **Do not activate migration until E06 changes existing canonical writer to explicit-column SQL and proves it on original Windows host**.

New `verified_writer_v2_compatible=False` default means migration HOLD. The adapter requires owner approval, a writer barrier and backup; it does not open a second database. After migration, `stable_history` also checks the v2 index and trigger. Foreign-key enforcement and pre-backup quick_check are mandatory. No automatic P02 schema migration.

Locally: 21/21 isolated SQLite tests PASS; original WPF+Python host, database, installed Ollama, RAG/ASR/TTS/MAESTRO/SIP and E07 same-EXE QA NOT VERIFIED. Existing D02/WOW/weights and all prior branches preserved.

**E06 handoff order:** verify canonical app DB/SourceLock -> approve exact P02 writer patch and v2 admission -> restart/VACUUM/append/ACL tests -> wire original chat/RAG bridge -> real local Ollama + STOP -> one Windows NSIS install -> E07 frozen-SHA QA.

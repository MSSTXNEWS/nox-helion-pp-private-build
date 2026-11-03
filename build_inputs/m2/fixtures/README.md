# fixtures (M2.0-PP)

Fixtures match what the pinned app actually reads.

- `model_config.json` is a byte copy of `model_config.example.json`. `load_model_config` accepts it. No core is bound, so it is not a live model config.
- `personas/persona.*.json` are the five runtime Persona IDs from `helion/personas.py`, joined to `assets/personas_5.json`. License, consent, and revoke stay PENDING. Nothing is signed.
- `rights/media_source_inventory_20261020.csv` is the source inventory (173 rows). Every `rights_status` is `SOURCE_RIGHTS_NOT_REVERIFIED`.
- `expected/` are negative checks: missing product bytes, invented cleared rights, the reference EXE, and a signed owner ACK must all fail.

Owner-only ticks stay unsigned.

# Narrow integration review checkpoint

Status: IN_PROGRESS_SOURCE_ONLY. Paused for the higher-priority authenticated
Resonance HTML identity mismatch. No production action or source fix yet.

Compared warm controller commit 63667188114ab9bf3bb45986de0549090f2e96ae
and integrations bridge commit 391953ee09807a890f0eaf37225e6e3670c1f4a9.

Concrete findings to reproduce and repair:

1. MemfdHandle.close sets closed=True before the release callback succeeds.
   If release raises, the second close returns normally. Controller.release_owned_ram
   can then pop the registry entry and report OWNED_RAM_CLOSED despite an
   unconfirmed RAM lease release. Keep release-pending state, require explicit
   authoritative reconciliation, and never silently replace/drop that handle.
2. Controller._cache_guard chooses per-call should_pause instead of OR-ing it
   with owner_should_pause. Passing a False extra callback can override a True
   host foreground/STOP callback. DriveAdapter already combines the two.
3. Further targeted check pending: WORK→TRAIN after a saved TRAIN checkpoint
   sets resume_from_verified_checkpoint=False because only PAUSED_TRAIN is
   recognized. Recheck checkpoint readback and clarify resume semantics before
   changing it. No claim of a tested defect yet.

Needed next: minimal failing fixtures with real local sealed memfd where
appropriate; repair both package lifecycle contracts; targeted tests, commits
and refreshed existing ZIPs. Already-passed unrelated tests need not repeat.

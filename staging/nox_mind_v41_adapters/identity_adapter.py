"""Map staging CoreID + PersonaID onto persona facets and warm-cache invalidation.

CoreID and PersonaID types are not defined anywhere else in this repository.
PersonaID here is the string the unpacked package already uses as a cache key.
CoreID is recorded on the binding and is not a cache key: ``WarmS03Cache``
invalidates by PersonaID only. Switching persona bumps that generation.
Switching CoreID while the PersonaID stays the same does not.
"""
from __future__ import annotations

from dataclasses import dataclass

from ._path import ensure_mind_package_on_path

ensure_mind_package_on_path()

from nox_mind_v41.persona import EmotionState, Persona

from .protocols import StagingDisabled, resolve_enabled


@dataclass(frozen=True)
class IdentityBinding:
    core_id: str
    persona_id: str


class PersonaIdentityAdapter:
    def __init__(self, cache, *, enabled: bool | None = None, identity_port=None):
        self.cache = cache
        self.identity_port = identity_port
        self.enabled = resolve_enabled(enabled)
        self.binding: IdentityBinding | None = None
        self.persona: Persona | None = None
        self.emotion = EmotionState()

    def current_ids(self):
        self._guard()
        if self.binding is None:
            return (None, None)
        return (self.binding.core_id, self.binding.persona_id)

    def bind(self, core_id: str, persona: Persona, *, emotion_label: str | None = None) -> dict:
        self._guard()
        if not isinstance(core_id, str) or not core_id.strip():
            raise ValueError("core_id is required; this repo has no CoreID type to supply one")
        if not isinstance(persona, Persona):
            raise TypeError("persona must be a staging Persona")
        self._assign(core_id, persona.persona_id, persona)
        if emotion_label:
            self.emotion.update(emotion_label)
        if self.identity_port is not None:
            self.identity_port.core_id = core_id
            self.identity_port.switch_persona(persona.persona_id)
        return {
            "binding": {"core_id": self.binding.core_id, "persona_id": self.binding.persona_id},
            "card": persona.card(),
            "system_block": self.system_block(),
        }

    def switch(self, core_id: str, persona: Persona, *, emotion_label: str | None = None) -> dict:
        return self.bind(core_id, persona, emotion_label=emotion_label)

    def switch_persona(self, persona_id: str) -> None:
        """Protocol method: change PersonaID and invalidate the previous cache key.

        The persona card is cleared because a bare id does not carry facets.
        Use ``switch`` when a ``Persona`` is available.
        """
        self._guard()
        if self.binding is None:
            raise ValueError("bind a core_id before switch_persona")
        self._assign(self.binding.core_id, persona_id, None)
        if self.identity_port is not None:
            self.identity_port.switch_persona(persona_id)

    def system_block(self) -> str:
        self._guard()
        if self.persona is None:
            return ""
        return self.persona.system_block(self.emotion)

    def _assign(self, core_id: str, persona_id: str, persona: Persona | None) -> None:
        previous = self.binding.persona_id if self.binding is not None else None
        if previous is not None and previous != persona_id:
            self.cache.invalidate_persona(previous)
        self.binding = IdentityBinding(core_id, persona_id)
        self.persona = persona

    def _guard(self) -> None:
        if not self.enabled:
            raise StagingDisabled(
                "NOX_MIND_V41_STAGING is off; identity adapter did not bind a persona or invalidate cache"
            )

"""Connect EXISTING NOX A.1 components to the existing, authenticated OneHost.

This factory owns no persistence, permissions, model, scheduler, network client,
process or UI. All callbacks MUST be obtained by the original native owner,
never from a browser, prompt, website, downloaded model or untrusted config.
If even one original owner port is unavailable, boot is denied, not simulated.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from .firstboot_coordinator import FirstBootCallbacks, FirstBootCoordinator
from .worms import WormHold, WormSwarm
from .worm_autopilot import WormAutopilot
from .worm_idea_loop import NativeIdeaLoop
from .a1_initiative_bridge import A1InitiativeBridge
from .a1_native_command import A1NativeCommand


class A1OwnerPortsHold(PermissionError):
    """Original native bridge has no verified implementation for a required port."""


@dataclass(frozen=True)
class ExistingA1OwnerPorts:
    # Windows native SID/session-granted ports. No permission may be synthesized
    # from a model, user data file or a web document.
    consent: Callable  # (session, command) -> exact True after WPF consent
    authorize: Callable  # (session, action) -> exact True under native lease
    stopped: Callable  # () -> bool; only literal False permits continuation
    stop_epoch: Callable  # () -> nonnegative int; must be monotonic
    source_head: Callable  # () -> verified exact current Git HEAD
    worm_policy: Callable  # (session) -> signed owner's policy
    approved_providers: Callable  # (session) -> (provider_map, source_hosts)
    worm_s03_append: Callable  # (session, validated observation) -> True AFTER readback
    s03_observations: Callable  # (session) -> real verified S03 observations
    p02_model_propose: Callable  # (design_brief) -> list from ORIGINAL P02
    s03_candidate_append: Callable  # (session, candidate) -> True AFTER readback
    s03_lessons: Callable  # (session, head) -> signed, verified original lessons
    verify_lesson: Callable  # (session, proof) -> exact True after native verification
    s03_append_readback: Callable  # (session, document) -> True AFTER durable readback
    native_firstboot: FirstBootCallbacks  # ORIGINAL P01/P03/S03 owner services

    def verify(self):
        names = (
            'consent','authorize','stopped','stop_epoch','source_head',
            'worm_policy','approved_providers','worm_s03_append',
            's03_observations','p02_model_propose','s03_candidate_append',
            's03_lessons','verify_lesson','s03_append_readback'
        )
        if any(not callable(getattr(self, name, None)) for name in names):
            raise A1OwnerPortsHold('A1_NATIVE_OWNER_CALLBACK_MISSING')
        if type(self.native_firstboot) is not FirstBootCallbacks:
            raise A1OwnerPortsHold('A1_NATIVE_FIRSTBOOT_CALLBACK_TYPE_REQUIRED')
        self.native_firstboot.verify()
        return True


def build_existing_a1_command(builder, ports: ExistingA1OwnerPorts):
    """Build one user-authorized command adapter using original owner ports.

    Does NOT call boot/tick, enable research or create a background thread.
    Existing WPF caller and native idle scheduling remain the only initiators.
    """
    if type(ports) is not ExistingA1OwnerPorts:
        raise A1OwnerPortsHold('A1_EXACT_NATIVE_OWNER_PORTS_REQUIRED')
    ports.verify()

    def components(session):
        # The signed owner chooses the providers. Do not enable GitHub, RSS,
        # PyPI, NuGet or any other network destination by default.
        if ports.stopped() is not False:
            raise A1OwnerPortsHold('A1_NATIVE_STOPPED_OR_UNKNOWN')
        if ports.authorize(session, 'evolution.autonomy.read') is not True:
            raise A1OwnerPortsHold('A1_NATIVE_RESEARCH_GRANT_REQUIRED')
        approved = ports.approved_providers(session)
        if (type(approved) is not tuple or len(approved) != 2 or
                type(approved[0]) is not dict or type(approved[1]) is not dict):
            raise A1OwnerPortsHold('A1_NATIVE_PROVIDER_MAP_REQUIRED')
        providers, hosts = approved
        swarm = WormSwarm(
            provider_map=providers, admit=ports.authorize,
            persist=ports.worm_s03_append, source_hosts=hosts,
            native_stop=ports.stopped)
        worms = WormAutopilot(
            native_signed_policy=ports.worm_policy,
            source_head=ports.source_head, swarm=swarm,
            native_stop=ports.stopped,
            s03_append_readback=ports.s03_append_readback)
        ideas = NativeIdeaLoop(
            authorized=ports.authorize, source_head=ports.source_head,
            s03_verified_observations=ports.s03_observations,
            p02_model_propose=ports.p02_model_propose,
            s03_save_candidate_readback=ports.s03_candidate_append,
            native_stop=ports.stopped)
        bridge = A1InitiativeBridge(
            worm_autopilot=worms, idea_loop=ideas,
            native_authorize=ports.authorize,
            native_stop=ports.stopped, native_stop_epoch=ports.stop_epoch,
            current_source_head=ports.source_head,
            native_s03_recent_lessons=ports.s03_lessons,
            native_verify_lesson=ports.verify_lesson,
            native_s03_append_readback=ports.s03_append_readback)
        # Use BOTH existing owner STOP witnesses. Never let a stale FirstBoot
        # callback bypass A1 revocation or downgrade stricter native STOP.
        def owner_stopped():
            return not (ports.stopped() is False and
                        ports.native_firstboot.stopped() is False)

        def owner_epoch():
            epoch = ports.stop_epoch()
            firstboot_epoch = ports.native_firstboot.stop_epoch()
            if (type(epoch) is not int or epoch < 0 or
                    type(firstboot_epoch) is not int or firstboot_epoch != epoch):
                raise A1OwnerPortsHold('A1_NATIVE_FIRSTBOOT_STOP_EPOCH_MISMATCH')
            return epoch

        firstboot = FirstBootCoordinator(replace(
            ports.native_firstboot,
            stopped=owner_stopped, stop_epoch=owner_epoch))
        if ports.stopped() is not False:
            raise A1OwnerPortsHold('A1_STOP_DURING_NATIVE_COMPONENT_BIND')
        return {'initiative_bridge': bridge, 'firstboot': firstboot}

    return A1NativeCommand(
        builder=builder, components=components,
        consent=ports.consent, authorize=ports.authorize,
        stopped=ports.stopped, stop_epoch=ports.stop_epoch,
        source_head=ports.source_head)

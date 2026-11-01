"""Narrow addon interface to the one existing P02/S03/OneHost native dispatcher.

No second DB/host/LLM, no auto-authorized chat commands, no code install.
Must be installed by owner #1 in the trusted native dispatcher, not WebView JS.
"""
from __future__ import annotations
from .wow_design import propose_design, approve_design, DesignHold, HEAD_RE
from .wow_background import BackgroundWowController, BackgroundHold

class WowOneHostPort:
    def __init__(self, *, native_source_head, source_evidence, existing_p02_design_generate,
                 native_authorize, native_stop, s03_audit, s03_read_proposal,
                 background_controller=None):
        callbacks=(native_source_head, source_evidence, existing_p02_design_generate,
                   native_authorize, native_stop, s03_audit, s03_read_proposal)
        if not all(callable(x) for x in callbacks):
            raise ValueError('ORIGINAL_P02_S03_NATIVE_HOST_CALLBACKS_REQUIRED')
        self.head=native_source_head
        self.evidence=source_evidence
        self.generate=existing_p02_design_generate
        self.authorize=native_authorize
        self.stopped=native_stop
        self.audit=s03_audit
        self.read=s03_read_proposal
        if background_controller is not None and not isinstance(background_controller, BackgroundWowController):
            raise TypeError('EXISTING_BACKGROUND_CONTROLLER_REQUIRED')
        self.background=background_controller

    def propose(self, native_session, task: str) -> dict:
        native_session.validate()
        head=self.head(native_session)
        if not isinstance(head,str) or not HEAD_RE.fullmatch(head):
            raise DesignHold('CURRENT_MANAGED_GIT_HEAD_REQUIRED')
        context=self.evidence(native_session,task,head)
        if not isinstance(context,list):raise DesignHold('S03_VERIFIED_EVIDENCE_REQUIRED')
        def audit(event,record):
            # Existing owner P02/S03 store transaction and ACL, not a local file.
            self.audit(native_session,event,record)
        return propose_design(task=task,source_head=head,source_evidence=context,
            native_authorize=lambda action,data:self.authorize(native_session,action,data),
            local_coder=lambda request:self.generate(native_session,request),
            stop_requested=lambda:self.stopped(native_session),s03_record=audit)

    def approve(self,native_session,*,proposal_sha256:str,variant_id:str)->dict:
        native_session.validate()
        if not isinstance(proposal_sha256,str) or len(proposal_sha256)!=64:
            raise DesignHold('EXACT_S03_PROPOSAL_SHA_REQUIRED')
        # User may only reference a proposal stored in its own native S03 scope,
        # NEVER supply a renderer-made proposal JSON or source file paths.
        proposal=self.read(native_session,proposal_sha256)
        if not isinstance(proposal,dict):raise DesignHold('SCOPED_ORIGINAL_S03_PROPOSAL_NOT_FOUND')
        current=self.head(native_session)
        return approve_design(proposal,variant_id=variant_id,
            expected_sha256=proposal_sha256,current_head=current,
            native_authorize=lambda action,data:self.authorize(native_session,action,data),
            stop_requested=lambda:self.stopped(native_session),
            s03_record=lambda event,record:self.audit(native_session,event,record))

    def background_status(self, native_session) -> dict:
        """Original S03 persistence read; not browser-local state."""
        if self.background is None:
            raise BackgroundHold('NATIVE_BACKGROUND_SERVICE_NOT_BOUND')
        return self.background.status(native_session)

    def background_switch(self, native_session, enabled: bool) -> dict:
        """ON requires native opt-in; OFF cancels only background generation."""
        if self.background is None:
            raise BackgroundHold('NATIVE_BACKGROUND_SERVICE_NOT_BOUND')
        return self.background.set_enabled(native_session, enabled)

    def background_tick(self, native_session) -> dict:
        """Called on EXISTING idle native actor/scheduler, not on UI/second daemon."""
        if self.background is None:
            raise BackgroundHold('NATIVE_BACKGROUND_SERVICE_NOT_BOUND')
        return self.background.tick(native_session)
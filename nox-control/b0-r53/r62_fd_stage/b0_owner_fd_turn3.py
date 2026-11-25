"""B0 owner FD ingress: isolated composition, no POST or native admission."""
from copy import deepcopy
from b5_retained_ingress import load_retained_chain
from b0_chain_bound import prepare_chain_bound_turn3


class RetainedFDTerminal:
    def __init__(self, evidence, prefix, dialog_id, session_id):
        self._evidence = evidence
        self._prefix = deepcopy(prefix)
        self._scope = dict(dialog_id=dialog_id, session_id=session_id)
        self._consumed = False

    def finish(self, *, artifacts, **browser_evidence):
        if self._consumed:
            return "HOLD_RESUME_ALREADY_CONSUMED"
        self._consumed = True
        try:
            chain = load_retained_chain(artifacts=artifacts, **self._scope)
        except ValueError:
            return "HOLD_B0_TERMINAL_FD_CHAIN"
        if len(chain) != 3 or chain[:2] != self._prefix:
            return "HOLD_B0_TERMINAL_FD_PREFIX"
        if "canonical_rows" in browser_evidence or "witnesses" in browser_evidence:
            return "HOLD_B0_TERMINAL_FD_OVERRIDE"
        rows, witnesses = chain[-1]
        return self._evidence.finish(canonical_rows=rows, witnesses=witnesses,
                                     **browser_evidence)


def prepare_owner_fd_turn3(*, artifacts, **kwargs):
    scope = dict(dialog_id=kwargs["dialog_id"], session_id=kwargs["session_id"])
    chain = load_retained_chain(artifacts=artifacts, **scope)
    if len(chain) != 2:
        raise ValueError("HOLD_B0_PRETURN_FD_LENGTH")
    if "canonical_rows" in kwargs or "prior_witnesses" in kwargs:
        raise ValueError("HOLD_B0_PRETURN_FD_OVERRIDE")
    rows, witnesses = chain[-1]
    evidence = prepare_chain_bound_turn3(retained_chain=chain,
        canonical_rows=rows, prior_witnesses=witnesses, **kwargs)
    if load_retained_chain(artifacts=artifacts, **scope) != chain:
        raise ValueError("HOLD_B0_PRETURN_FD_DRIFT")
    return RetainedFDTerminal(evidence, chain, **scope)

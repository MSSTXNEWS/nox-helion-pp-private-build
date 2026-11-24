"""B0 turn-3 composition, source only. Never sends POST or grants admission."""
from copy import deepcopy
from b0_resume_bridge import prepare_existing_resume_from_owner_get
from b5_chain_guard import verify_existing_chain


class ChainBoundTerminal:
    def __init__(self, evidence, chain, dialog_id, session_id):
        self._evidence = evidence
        self._chain = chain
        self._dialog_id = dialog_id
        self._session_id = session_id
        self._consumed = False

    def finish(self, **kwargs):
        if self._consumed:
            return "HOLD_RESUME_ALREADY_CONSUMED"
        self._consumed = True
        result = self._evidence.finish(**kwargs)
        if result != "RESUME_EVIDENCE_MATCHED":
            return result
        if not verify_existing_chain(
                dialog_id=self._dialog_id, session_id=self._session_id,
                chain=self._chain + ((kwargs["canonical_rows"], kwargs["witnesses"]),)):
            return "HOLD_B0_FULL_S03_CHAIN"
        return result


def prepare_chain_bound_turn3(*, retained_chain, **kwargs):
    """Require original independent turn1+2 pins before the single owner GET."""
    dialog_id, session_id = kwargs["dialog_id"], kwargs["session_id"]
    def valid(chain):
        return (type(chain) is tuple and len(chain) == 2
                and verify_existing_chain(dialog_id=dialog_id, session_id=session_id,
                                          chain=chain)
                and kwargs["row_count"] == 4
                and kwargs["canonical_rows"] == chain[1][0]
                and kwargs["prior_witnesses"] == chain[1][1])
    if not valid(retained_chain):
        raise ValueError("HOLD_B0_FULL_S03_PREFIX")
    frozen = deepcopy(retained_chain)
    evidence = prepare_existing_resume_from_owner_get(**kwargs)
    if retained_chain != frozen or not valid(frozen):
        raise ValueError("HOLD_B0_FULL_S03_PREFIX_DRIFT")
    return ChainBoundTerminal(evidence, frozen, dialog_id, session_id)

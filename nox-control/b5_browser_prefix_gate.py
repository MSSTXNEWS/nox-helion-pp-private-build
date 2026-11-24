"""Existing-dialog pre-POST evidence gate; no transport or native authority.

Owner GET and actual browser observations are distinct inputs from the
authorized caller. Never substitute the GET for browser observations.
"""
from b0_resume_bridge import bind_existing_resume
from b5_r55_pinned import BrowserResumeEvidence


def bind_observed_browser_prefix(*, observed_browser_rows, observed_browser_calls,
                                 **owner_evidence):
    """Validate three views (owner GET, browser DOM, independent S03).

    The caller must capture the browser DOM and its counter before sending
    the next POST. This pure gate cannot establish observation provenance
    or authorize a request. A HOLD must prevent the next POST.
    """
    owner_rows = owner_evidence.get("owner_rows")
    canonical_rows = owner_evidence.get("canonical_rows")
    if (type(observed_browser_rows) is not list
            or observed_browser_rows is owner_rows
            or observed_browser_rows is canonical_rows
            or len(observed_browser_rows) not in (2, 4)
            or type(observed_browser_calls) is not int
            or observed_browser_calls != owner_evidence.get("browser_calls")):
        raise ValueError("HOLD_ACTUAL_BROWSER_PREFIX")
    # Verify the independent owner GET pin and S03 prefix first.
    bind_existing_resume(**owner_evidence)
    # Bind the one-shot evidence object to the actual browser observation,
    # not to a copy of the GET supplied by the owner history endpoint.
    return BrowserResumeEvidence(
        dialog_id=owner_evidence["dialog_id"],
        session_id=owner_evidence["session_id"],
        prior_rows=canonical_rows,
        prior_witnesses=owner_evidence["prior_witnesses"],
        browser_rows=observed_browser_rows,
        browser_calls=observed_browser_calls,
        admitted_calls=owner_evidence["admitted_calls"])

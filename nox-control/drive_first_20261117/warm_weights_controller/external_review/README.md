# Independent local review fixtures

These source bytes are unchanged from the independent reviewer. The paired
integrations package must be importable with the matching 0.2 controller.

Run from the controller directory with both package roots on PYTHONPATH:

```bash
PYTHONPATH=/path/to/warm_weights_controller:/path/to/integrations_bridge python -m unittest discover -s external_review -p test_additional_lifecycle.py -v
```

The reviewed test file SHA is recorded in REVIEW_RECEIPT.json. This checks
local sealed memfd/dup and lease fences, not native model/Drive execution.

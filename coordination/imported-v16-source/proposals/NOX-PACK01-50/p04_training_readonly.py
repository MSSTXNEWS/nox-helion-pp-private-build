"""Read-only P04 training input and checkpoint bindings to original train_qlora.py.

Not an alternative trainer. All paths come from authenticated native Windows
selection, not WebView2 page requests. Actual rights verifier is required.
"""
from __future__ import annotations
from pathlib import Path
from typing import Callable

class TrainingInputHold(RuntimeError):
    pass

class P04TrainingReadOnlyPack:
    def __init__(self, original_worker_module, *,
                 native_dataset_selection: Callable,
                 native_checkpoint_selection: Callable,
                 native_permission: Callable):
        for fn in ("verify_manifest","validated_checkpoint"):
            if not callable(getattr(original_worker_module,fn,None)):
                raise ValueError("Actual original P04 train_qlora source required")
        if not all(callable(x) for x in (native_dataset_selection,native_checkpoint_selection,native_permission)):
            raise ValueError("Trusted native selection and permission required")
        self.worker=original_worker_module
        self.dataset_selection=native_dataset_selection
        self.checkpoint_selection=native_checkpoint_selection
        self.native_permission=native_permission

    def review_dataset(self,session):
        if self.native_permission(session,"datasets.review") is not True:
            raise PermissionError("Native dataset review permission required")
        chosen=self.dataset_selection(session)
        if not isinstance(chosen,tuple) or len(chosen)!=4:
            raise TrainingInputHold("No approved native dataset paths")
        manifest,train,holdout,verifier=(Path(x) for x in chosen)
        # Original verifier compares both SHA-256 and authorized rights,
        # and invokes only the native-owner-selected rights verifier executable.
        result=self.worker.verify_manifest(manifest,train,holdout,verifier)
        return {"datasetId":result["dataset_id"],
                "datasetRevision":result["dataset_revision"],
                "licenseId":result["license_id"],
                "rightsAttestationId":result["_rights_attestation_id"],
                "rightsAttestationSha256":result["_rights_attestation_sha256"],
                "status":"RIGHTS_VERIFIED"}

    def inspect_checkpoint(self,session):
        if self.native_permission(session,"training.checkpoints") is not True:
            raise PermissionError("Native training checkpoint access required")
        chosen=self.checkpoint_selection(session)
        if not isinstance(chosen,tuple) or len(chosen)!=2:
            raise TrainingInputHold("No native checkpoint directory/selection")
        root,selected=(Path(x) for x in chosen)
        # Original worker checks file type, canonical path, trainer_state, full
        # optimizer/scheduler/RNG/model weights. No actual training is executed.
        step,digest=self.worker.validated_checkpoint(root,selected)
        return {"step":step,"checkpointSha256":digest,
                "status":"STRUCTURE_VERIFIED_NOT_GPU_TRAINED"}

    def register(self,dispatcher,*,receipt,owner_port):
        # E06 owner host provides BoundPort, using current native user identity.
        if not isinstance(receipt,str) or not receipt.strip():raise ValueError("Owner receipt required")
        dispatcher.bind("datasets.review",
                        owner_port(self.review_dataset,lambda:True,receipt,4))
        dispatcher.bind("training.checkpoints",
                        owner_port(self.inspect_checkpoint,lambda:True,receipt,4))
        return frozenset(("datasets.review","training.checkpoints"))

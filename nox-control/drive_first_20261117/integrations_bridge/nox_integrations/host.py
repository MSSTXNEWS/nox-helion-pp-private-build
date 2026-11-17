"""Typed handler registration only; the existing host owns authorization/queue."""
import json
import time
import uuid

from .core import BridgeError
from .drive import DriveAdapter
from .providers import Providers

CAPABILITIES = {
    "nox.integrations.drive.check.v1": {"effect":"remote_read","arguments":{}},
    "nox.integrations.drive.list.v1": {"effect":"remote_read","arguments":{"path":"relative_path?","limit":"int<=500?"}},
    "nox.integrations.drive.read.v1": {"effect":"remote_read","arguments":{"path":"relative_path","max_bytes":"int<=1048576?"}},
    "nox.integrations.drive.upload.v1": {"effect":"remote_write","arguments":{"artifact_path":"relative_artifact","remote_path":"relative_drive_path","expected_sha256":"sha256"}},
    "nox.integrations.drive.download.v1": {"effect":"local_cache_write","arguments":{"remote_path":"relative_drive_path","cache_path":"relative_cache_path","expected_sha256":"sha256","size_bytes":"positive_int"}},
    "nox.integrations.notion.search.v1": {"effect":"remote_read","arguments":{"query":"string<=200?","limit":"int<=50?"}},
    "nox.integrations.github.repo.v1": {"effect":"remote_read","arguments":{}},
    "nox.integrations.gitlab.project.v1": {"effect":"remote_read","arguments":{}},
}


class IntegrationBridge:
    def __init__(self,config,*,authorize=None,result_sink=None,native_runtime=False,
                 runner=None,transport=None,should_pause=None):
        self.config=config
        self.authorize=authorize
        self.result_sink=result_sink
        self.native_runtime=native_runtime
        self.drive=DriveAdapter(config,runner=runner,should_pause=should_pause)
        self.providers=Providers(config,transport)
        self._verified={}
        self.handlers={
            "nox.integrations.drive.check.v1":self.drive.check,
            "nox.integrations.drive.list.v1":self.drive.list,
            "nox.integrations.drive.read.v1":self.drive.read,
            "nox.integrations.drive.upload.v1":self.drive.upload_artifact,
            "nox.integrations.drive.download.v1":self.drive.download_verified,
            "nox.integrations.notion.search.v1":self.providers.notion_search,
            "nox.integrations.github.repo.v1":self.providers.github_repo,
            "nox.integrations.gitlab.project.v1":self.providers.gitlab_project,
        }

    def registry(self):
        """Local inspection only. Ready means configured, not successful auth."""
        rows=[]
        for kind,spec in CAPABILITIES.items():
            if ".drive." in kind:
                present=self.config.drive_requirements()
                if ".upload." in kind:
                    present["artifact_root_configured"]=bool(self.config.get("NOX_ARTIFACT_ROOT"))
                if ".download." in kind:
                    present["cache_root_configured"]=bool(self.config.get("NOX_DRIVE_CACHE_ROOT"))
            else:
                service=kind.split(".")[2]
                present={"token_present":bool(self.config.get("NOX_"+service.upper()+"_TOKEN"))}
                if service in ("github","gitlab"):
                    present["target_configured"]=bool(self.config.get("NOX_GITHUB_REPO" if service=="github" else "NOX_GITLAB_PROJECT"))
            status="ready" if all(present.values()) else "pending_credentials"
            if kind=="nox.integrations.drive.download.v1" and self.config.get("NOX_ALLOW_DISK_CACHE")!="1":
                status="disabled_by_policy"
            evidence=self._verified.get(kind)
            if evidence and status=="ready":
                status="tested_native"
            rows.append({"capability":kind,"status":status,"effect":spec["effect"],
                         "configuration_present":present,"native_evidence":evidence,
                         "host_authorization_bound":callable(self.authorize),
                         "result_sink_bound":callable(self.result_sink)})
        return {"schema":"nox.integrations.capabilities.v1","capabilities":rows,
                "new_server":False,"new_queue":False,"new_model":False,
                "download_policy":{"canonical":"external_to_verified_drive_to_owned_ram",
                                   "arbitrary_url_ingest":False,"disk_cache_explicit_opt_in":self.config.get("NOX_ALLOW_DISK_CACHE")=="1",
                                   "ram_requires_host_reservation_and_owned_handle":True}}

    def execute(self,kind,payload,*,task_id):
        """Call only in an existing worker; task_id is supplied by the host."""
        try:
            if kind not in CAPABILITIES or not isinstance(payload,dict):
                raise BridgeError("UNKNOWN_TYPED_HANDLER")
            if not isinstance(task_id,str) or not 1<=len(task_id)<=160:
                raise BridgeError("HOST_TASK_ID_REQUIRED")
            allowed=CAPABILITIES[kind]["arguments"]
            if any(k not in allowed for k in payload):
                raise BridgeError("UNKNOWN_ARGUMENT")
            if len(json.dumps(payload,ensure_ascii=False).encode())>16384:
                raise BridgeError("HANDLER_PAYLOAD_LIMIT")
            self.config.reject_secrets([payload,task_id])
            if not callable(self.authorize) or not callable(self.result_sink):
                raise BridgeError("HOST_BINDING_REQUIRED")
            if self.authorize(kind,payload,task_id) is not True:
                raise BridgeError("HOST_ADMISSION_DENIED")
            try:
                result=self.handlers[kind](**payload)
            except TypeError:
                raise BridgeError("INVALID_HANDLER_ARGUMENTS") from None
            result=self.config.redact(result)
            receipt={"schema":"nox.integration.result.v1","receipt_id":uuid.uuid4().hex,
                     "task_id":task_id,"capability":kind,"at":time.time(),
                     "execution_origin":"native_onehost" if self.native_runtime else "local_or_fixture",
                     "result":result}
            try:
                ack=self.result_sink(receipt)
            except Exception:
                raise BridgeError("RESULT_PERSISTENCE_FAILED",outcome_uncertain=CAPABILITIES[kind]["effect"]!="remote_read") from None
            if not isinstance(ack,str) or not ack:
                raise BridgeError("RESULT_PERSISTENCE_UNCONFIRMED",outcome_uncertain=CAPABILITIES[kind]["effect"]!="remote_read")
            receipt["host_receipt_ref"]=ack
            if self.native_runtime and result.get("remote_verified") is True:
                self._verified[kind]={"receipt_id":receipt["receipt_id"],"host_receipt_ref":ack,"verified_at":receipt["at"]}
            return self.config.redact(receipt)
        except BridgeError as error:
            return error.public()
        except Exception:
            return BridgeError("INTEGRATION_INTERNAL_ERROR").public()

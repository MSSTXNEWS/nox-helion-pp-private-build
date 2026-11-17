"""Operator CLI. status is offline; proof is an explicit read-only operation."""
import argparse
import json
import sys

from .config import Config
from .core import BridgeError
from .host import IntegrationBridge


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("status","proof"))
    parser.add_argument("provider",nargs="?",choices=("drive","notion","github","gitlab"))
    args=parser.parse_args()
    try:
        bridge=IntegrationBridge(Config.load())
        if args.command=="status":
            result=bridge.registry()
        else:
            if not args.provider:
                parser.error("proof requires a provider")
            # Direct operator check; no native/pass state is asserted or persisted.
            functions={"drive":bridge.drive.check,"notion":bridge.providers.notion_search,
                       "github":bridge.providers.github_repo,"gitlab":bridge.providers.gitlab_project}
            result={"execution_origin":"operator_cli","native_acceptance":False,
                    "result":functions[args.provider]()}
        print(json.dumps(bridge.config.redact(result),ensure_ascii=False))
        return 0
    except BridgeError as error:
        print(json.dumps(error.public(),ensure_ascii=False))
        return 2


if __name__=="__main__":
    sys.exit(main())

import json
import sys

from . import build_registry

if __name__ == "__main__":
    reg = build_registry()
    if len(sys.argv) < 2 or sys.argv[1] == "list":
        for d in reg.describe():
            print("%-20s %-7s %s" % (d["name"], d["mode"], d["doc"]))
    else:
        print(json.dumps(reg.call(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}),
                         ensure_ascii=False, indent=1))

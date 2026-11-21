"""CLI импорта бэкапа в S03: python3 -m qs6.import_cli --db s03.db --root /root/nox/backup_s2/unpacked [--dry-run]
Печатает отчёт. Код выхода: 0 принято хоть что-то, 3 ничего не принято (пустой/непонятный бэкап), 2 ошибка аргументов/каталога."""
import argparse
import json
import os
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.root):
        print("нет каталога %s" % a.root, file=sys.stderr)
        return 2
    from .s03_store import Store
    s = Store(a.db)
    try:
        rep = s.import_dir(a.root, dry_run=a.dry_run)
    finally:
        s.close()
    print(json.dumps(rep.as_dict(), ensure_ascii=False) if a.json else rep.text())
    t = rep.totals
    return 0 if (t["facts"] + t["episodes"] + t["profile"] + t["updated"]) > 0 else 3


if __name__ == "__main__":
    sys.exit(main())

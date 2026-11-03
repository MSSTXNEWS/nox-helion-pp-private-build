"""Entry for the M2.3 Linux binary. Not the reference Windows candidate."""
import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if '--m23-self-test' not in args:
        args.insert(0, '--m23-self-test')
    from helion.m23_selftest import main as run
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())

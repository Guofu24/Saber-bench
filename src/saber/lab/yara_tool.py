"""Fixed process boundary for the optional native yara-python dependency."""

import importlib
import sys


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(2)
    yara = importlib.import_module("yara")
    rules = yara.compile(filepath=sys.argv[1])
    for result in rules.match(filepath=sys.argv[2], timeout=30):
        print(result.rule)


if __name__ == "__main__":
    main()

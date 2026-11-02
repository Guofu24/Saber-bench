"""Invoke Volatility's supported console entry point in an isolated child process."""

import importlib


def main() -> None:
    importlib.import_module("volatility3.cli").main()


if __name__ == "__main__":
    main()

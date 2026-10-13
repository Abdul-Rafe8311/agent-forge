"""Read existing result files only; never launch a coding agent or use credentials."""

import argparse
import json
from pathlib import Path

from agentforge.assist.metrics import compare
from agentforge.assist.storage import read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare([read_json(path) for path in args.results]), indent=2))


if __name__ == "__main__":
    main()

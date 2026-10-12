"""Connectivity probe for the configured Akamai vLLM endpoint."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.vllm import check_connection


def main() -> int:
    try:
        result = check_connection()
    except Exception as exc:
        # Endpoint errors are deliberately sanitized; don't echo SDK request details.
        print(f"vLLM connectivity failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

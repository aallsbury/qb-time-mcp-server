"""Launch QBTime over its existing JSON-RPC stdio protocol."""

import argparse
import json
import logging
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

from config import request_timeout
from utils import setup_logging


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).with_name(".env"))
    parser.add_argument("--check-config", action="store_true", help="Validate configuration/imports without API calls or a listener")
    args = parser.parse_args(argv)
    # Existing process environment wins; .env lookup no longer depends on cwd.
    load_dotenv(dotenv_path=args.env_file, override=False)
    token = os.getenv("QB_TIME_ACCESS_TOKEN", "").strip()
    setup_logging(secret=token)
    try:
        if not token:
            raise ValueError("QB_TIME_ACCESS_TOKEN environment variable is required")
        timeout = request_timeout()
        from server import run_server
        if args.check_config:
            print(json.dumps({"ok": True, "tokenConfigured": True, "connectTimeoutSeconds": timeout[0], "readTimeoutSeconds": timeout[1]}))
            return 0
        run_server(token, os.getenv("NODE_ENV", "development"))
        return 0
    except (ValueError, ImportError) as exc:
        # Do not echo credentials or provider response bodies to boot-task output.
        logging.error('QBTime startup failed category=%s', type(exc).__name__)
        print(f"QBTime startup failed ({type(exc).__name__}); check configuration and protected service logs.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

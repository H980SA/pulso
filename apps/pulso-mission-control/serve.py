#!/usr/bin/env python3
"""CLI bootstrap kept separate from the HTTP and persistence contracts."""

import argparse
from pathlib import Path

from server import build_server, default_state_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve PULSO mission control")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    args = parser.parse_args()
    server = build_server(args.bind, args.port, args.state_dir)
    print(f"PULSO mission control: http://{args.bind}:{args.port}/", flush=True)
    print(f"PULSO session store: {args.state_dir}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

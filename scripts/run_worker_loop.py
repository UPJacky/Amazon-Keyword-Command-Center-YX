#!/usr/bin/env python3
"""Run the local queue worker continuously until interrupted."""

import argparse
import json
import signal
import sys
from dataclasses import asdict
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.queue.supervisor import run_loop


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-root", required=True)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--max-backoff", type=float, default=30.0)
    parser.add_argument("--heartbeat-interval", type=float, default=30.0, help="seconds between liveness messages; 0 logs every poll")
    parser.add_argument("--max-cycles", type=int, help="bounded mode for local verification")
    args = parser.parse_args()
    stop_event = Event()

    def request_stop(signum, _frame) -> None:
        stop_event.set()
        print(json.dumps({"event": "worker_stop_requested", "signal": signum}, ensure_ascii=False), file=sys.stderr, flush=True)

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    def heartbeat(stats) -> None:
        print(json.dumps({"event": "worker_heartbeat", **asdict(stats)}, ensure_ascii=False), file=sys.stderr, flush=True)

    try:
        stats = run_loop(args.queue_root, args.storage_root, poll_interval=args.poll_interval, max_backoff=args.max_backoff, max_cycles=args.max_cycles, stop_event=stop_event, heartbeat_interval=args.heartbeat_interval, heartbeat_fn=heartbeat)
    except KeyboardInterrupt:
        print(json.dumps({"stopped": True, "reason": "keyboard_interrupt"}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({
            "cycles": 0,
            "processed": 0,
            "failed": 0,
            "empty_cycles": 0,
            "errors": 1,
            "recovered": 0,
            "stopped": stop_event.is_set(),
            "reason": "unexpected_supervisor_exception",
            "exception_type": type(exc).__name__,
            "error": str(exc),
        }, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(stats.__dict__, ensure_ascii=False, indent=2))
    return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

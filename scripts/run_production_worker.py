#!/usr/bin/env python3
"""Server-only Supabase worker. Default invocation is a zero-network loop."""

import argparse
import json
import os
import signal
import sys
from pathlib import Path
from threading import Event

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worker.runtime.production import ProductionWorker, RestrictedTransport, RuntimeFailure
from worker.providers.mcp_http_transport import McpHttpTransport
from worker.providers.xiyou_live_enrichment import XiyouCallBudget, XiyouLiveEnricher


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live", action="store_true", help="authorize real Supabase queue/storage requests using server env")
    parser.add_argument("--ad-only", action="store_true", help="acknowledge live advertising-only reports; no Provider factory is configured")
    parser.add_argument("--xiyou-keywords", type=int, help="explicitly enable get_keyword_info for at most 1-10 terms per task")
    parser.add_argument("--max-provider-calls", type=int, help="required process-lifetime Xiyou call ceiling")
    parser.add_argument("--max-provider-credits", type=int, help="required process-lifetime Xiyou credit ceiling")
    parser.add_argument("--worker-id", default="kwcc-worker")
    parser.add_argument("--lease-seconds", type=int, default=300)
    parser.add_argument("--heartbeat-interval", type=float)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--poll-interval", type=float, default=1)
    parser.add_argument("--max-cycles", type=int)
    args = parser.parse_args(argv)
    stop = Event()

    def request_stop(_signum, _frame):
        stop.set()

    previous = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, request_stop)
    try:
        # Validate worker and loop settings before constructing a live transport.
        provider_enabled = args.xiyou_keywords is not None
        limits = (args.max_provider_calls, args.max_provider_credits)
        if provider_enabled:
            if args.ad_only or not 1 <= args.xiyou_keywords <= 10 or any(type(value) is not int or value < 1 for value in limits):
                raise RuntimeFailure("SETTINGS_INVALID")
        elif any(value is not None for value in limits):
            raise RuntimeFailure("SETTINGS_INVALID")
        worker = ProductionWorker(worker_id=args.worker_id, lease_seconds=args.lease_seconds,
                                  heartbeat_interval=args.heartbeat_interval, stop_event=stop)
        if args.confirm_live:
            if not args.ad_only and not provider_enabled:
                print(json.dumps({"event": "worker_error", "code": "AD_ONLY_CONFIRMATION_REQUIRED",
                                  "message": "Choose --ad-only or an explicitly budgeted --xiyou-keywords mode; full reports remain incomplete."}), flush=True)
                return 1
            worker.transport = RestrictedTransport.from_env(confirm_live=True, timeout=args.timeout)
            if provider_enabled:
                provider_transport = McpHttpTransport(os.environ.get("XYDC_MCP_URL", ""),
                                                      os.environ.get("XYDC_MCP_TOKEN", ""), timeout=args.timeout)
                budget = XiyouCallBudget(args.max_provider_calls, args.max_provider_credits)
                def factory(task):
                    return XiyouLiveEnricher(transport=provider_transport, country=task.get("marketplace"),
                                             asin=task.get("self_asin"), max_keywords=args.xiyou_keywords,
                                             budget=budget)
                worker.provider_factory = factory
        stats = worker.run_loop(poll_interval=args.poll_interval, max_cycles=args.max_cycles,
                                on_cycle=lambda result: print(json.dumps({"event": "worker_cycle", **result}), flush=True))
        print(json.dumps({"event": "worker_summary", "live": args.confirm_live,
                          "report_scope": "xiyou_keyword_metrics" if provider_enabled else "ad_only",
                          "full_report_complete": False, **stats}), flush=True)
        return 1 if stats["errors"] or stats["failed"] else 0
    except KeyboardInterrupt:
        stop.set()
        print(json.dumps({"event": "worker_stopped"}), flush=True)
        return 0
    except Exception as exc:
        safe = exc if isinstance(exc, RuntimeFailure) else RuntimeFailure("WORKER_FAILED")
        print(json.dumps({"event": "worker_error", "failure_reason": safe.record()}), flush=True)
        return 1
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())

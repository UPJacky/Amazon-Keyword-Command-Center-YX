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
from worker.providers.sorftime_adapter import SorftimeCallBudget, SorftimeCatalogAdapter
from worker.providers.sorftime_transport import SorftimeTransport
from worker.providers.xiyou_live_enrichment import XiyouCallBudget, XiyouLiveEnricher


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live", action="store_true", help="authorize real Supabase queue/storage requests using server env")
    parser.add_argument("--ad-only", action="store_true", help="acknowledge live advertising-only reports; no Provider factory is configured")
    parser.add_argument("--xiyou-keywords", type=int, help="explicitly enable get_keyword_info for at most 1-10 terms per task")
    parser.add_argument("--max-provider-calls", type=int, help="required process-lifetime Xiyou call ceiling")
    parser.add_argument("--max-provider-credits", type=int, help="required process-lifetime Xiyou credit ceiling")
    parser.add_argument("--sorftime-catalog", action="store_true", help="enable explicitly budgeted Sorftime product enrichment")
    parser.add_argument("--max-sorftime-calls", type=int, help="required process-lifetime Sorftime call ceiling")
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
        if args.sorftime_catalog and not provider_enabled:
            raise RuntimeFailure("SETTINGS_INVALID")
        if args.sorftime_catalog and (type(args.max_sorftime_calls) is not int or args.max_sorftime_calls < 1):
            raise RuntimeFailure("SETTINGS_INVALID")
        if not args.sorftime_catalog and args.max_sorftime_calls is not None:
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
                sorftime_budget = None
                sorftime_transport = None
                if args.sorftime_catalog:
                    sorftime_transport = SorftimeTransport(os.environ.get("SORFTIME_MCP_ENDPOINT", ""), timeout=args.timeout)
                    sorftime_budget = SorftimeCallBudget(args.max_sorftime_calls)
                def factory(task):
                    catalog = None
                    if sorftime_transport is not None:
                        catalog = SorftimeCatalogAdapter(transport=sorftime_transport,
                                                         marketplace=task.get("marketplace"),
                                                         budget=sorftime_budget,
                                                         max_calls=args.max_sorftime_calls)
                    return XiyouLiveEnricher(transport=provider_transport, country=task.get("marketplace"),
                                             asin=task.get("self_asin"), max_keywords=args.xiyou_keywords,
                                             budget=budget, enable_competitors=True,
                                             catalog_adapter=catalog,
                                             primary_core_keyword=task.get("primary_core_keyword"))
                worker.provider_factory = factory
        full_report_seen = False

        def emit_cycle(result):
            nonlocal full_report_seen
            full_report_seen = full_report_seen or result.get("full_report_complete") is True
            print(json.dumps({"event": "worker_cycle", **result}), flush=True)

        stats = worker.run_loop(poll_interval=args.poll_interval, max_cycles=args.max_cycles,
                                on_cycle=emit_cycle)
        print(json.dumps({"event": "worker_summary", "live": args.confirm_live,
                          "report_scope": "xiyou_keyword_metrics" if provider_enabled else "ad_only",
                          "full_report_complete": full_report_seen, **stats}), flush=True)
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

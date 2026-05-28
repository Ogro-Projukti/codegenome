"""CLI entry point for Watcher."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from codegenome.exporter import SUPPORTED_FORMATS
from codegenome.watcher import WatcherConfig, WatcherEngine

LOG = logging.getLogger("codegenome")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watcher CLI — local codebase knowledge graph")
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root to analyze",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Run a graph build for the workspace",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force a full rebuild instead of an incremental update",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch the workspace and rebuild incrementally on changes",
    )
    parser.add_argument(
        "--watch-debounce",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="Seconds of inactivity before an incremental rebuild (default: 30)",
    )
    parser.add_argument(
        "--live-graph",
        action="store_true",
        help="Poll workspace file/line totals and rebuild when either increases",
    )
    parser.add_argument(
        "--live-graph-interval",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="Seconds between live graph metric polls (default: 30)",
    )
    parser.add_argument(
        "--print-metrics",
        action="store_true",
        help="Print workspace file/line metric totals as JSON and exit",
    )
    parser.add_argument(
        "--export",
        nargs="*",
        default=["json", "html", "markdown"],
        help=f"Export formats: {', '.join(sorted(SUPPORTED_FORMATS))}",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Timeline SQLite database path (default: .genome/watcher.db)",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Start the MCP server after building",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity",
    )
    parser.add_argument(
        "--dump-timeline",
        action="store_true",
        help="Dump timeline JSON from the workspace database and exit",
    )
    parser.add_argument(
        "--dump-changes",
        action="store_true",
        help="Dump snapshot delta JSON from the workspace database and exit",
    )
    parser.add_argument(
        "--dump-churn",
        action="store_true",
        help="Dump churn rankings JSON from the workspace database and exit",
    )
    parser.add_argument(
        "--node-id",
        default=None,
        help="Optional node id filter for --dump-timeline",
    )
    parser.add_argument(
        "--snapshot-from",
        type=int,
        default=None,
        help="From snapshot id for --dump-changes or --dump-churn",
    )
    parser.add_argument(
        "--snapshot-to",
        type=int,
        default=None,
        help="To snapshot id for --dump-changes or --dump-churn",
    )
    parser.add_argument(
        "--churn-file",
        default=None,
        help="Optional file path for --dump-churn",
    )
    parser.add_argument(
        "--churn-limit",
        type=int,
        default=25,
        help="Ranking limit for --dump-churn",
    )
    return parser.parse_args(argv)


def run_timeline_query(args: argparse.Namespace) -> int:
    from codegenome.graph_store import GraphStore, GraphStoreError

    workspace = Path(args.workspace).resolve()
    db_path = Path(args.db_path).resolve() if args.db_path else workspace / ".genome" / "watcher.db"

    store = GraphStore(db_path)
    try:
        store.open()
        if args.dump_timeline:
            payload = store.get_timeline(node_id=args.node_id)
        elif args.dump_changes:
            if args.snapshot_from is None or args.snapshot_to is None:
                print(
                    "--snapshot-from and --snapshot-to are required with --dump-changes",
                    file=sys.stderr,
                )
                return 1
            payload = store.get_changes(
                snapshot_from=args.snapshot_from,
                snapshot_to=args.snapshot_to,
            )
        elif args.dump_churn:
            payload = store.get_churn(
                file_path=args.churn_file,
                snapshot_from=args.snapshot_from,
                snapshot_to=args.snapshot_to,
                limit=args.churn_limit,
            )
        else:
            return 1
        print(json.dumps(payload))
        return 0
    except (GraphStoreError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "--run-mcp-server":
        from codegenome.mcp_server import main as mcp_main

        return mcp_main(argv[1:])

    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.dump_timeline or args.dump_changes or args.dump_churn:
        return run_timeline_query(args)

    workspace = Path(args.workspace).resolve()
    if args.print_metrics:
        if not workspace.exists():
            print(f"Workspace not found: {workspace}", file=sys.stderr)
            return 1
        from dataclasses import asdict

        from codegenome.workspace_metrics import WorkspaceMetricsScanner

        metrics = WorkspaceMetricsScanner(workspace).scan()
        print(json.dumps(asdict(metrics)))
        return 0

    workspace = Path(args.workspace).resolve()
    if not workspace.exists():
        print(f"Workspace not found: {workspace}", file=sys.stderr)
        return 1

    if not args.build and not args.watch and not args.live_graph:
        print("Nothing to do. Pass --build, --watch, and/or --live-graph.", file=sys.stderr)
        return 1

    config = WatcherConfig(
        workspace=workspace,
        db_path=Path(args.db_path).resolve() if args.db_path else None,
        export_formats=tuple(fmt.lower() for fmt in args.export),
        start_mcp=args.mcp,
        watch_debounce_seconds=max(0.0, float(args.watch_debounce)),
        live_graph=args.live_graph,
        live_graph_poll_seconds=max(1.0, float(args.live_graph_interval)),
    )
    engine = WatcherEngine(config)

    try:
        if args.build or args.watch or args.live_graph:
            result = engine.build(full=args.full)
            graph_json = result.export_paths.get("graph_json", engine.graph_json_path)
            print(f"Build complete: nodes={result.graph.number_of_nodes()} edges={result.graph.number_of_edges()}")
            print(f"Graph JSON: {graph_json}")

        if args.mcp:
            process = engine.start_mcp()
            print(f"MCP server started (pid={process.pid}) on {config.mcp_host}:{config.mcp_port}")

        if args.live_graph:
            engine.monitor_live_graph()
        elif args.watch:
            engine.watch()
    finally:
        engine.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

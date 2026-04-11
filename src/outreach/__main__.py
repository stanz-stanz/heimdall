"""Entry point: python -m src.outreach promote|interpret|send

Batch outreach pipeline for prospect campaigns.
Unlike the delivery bot (persistent Redis subscriber), this module
runs discrete batch operations triggered by the operator.

Examples:
    # Promote Bucket A restaurant prospects into a campaign
    python -m src.outreach promote --campaign 0426-restaurants --bucket A

    # Interpret with Claude API (only high/critical findings)
    python -m src.outreach interpret --campaign 0426-restaurants --min-severity high

    # Dry-run send to see what would go out
    python -m src.outreach send --campaign 0426-restaurants --dry-run

    # Actually send (routes through operator approval)
    python -m src.outreach send --campaign 0426-restaurants
"""

from __future__ import annotations

import argparse
import sys

from src.prospecting.logging_config import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="python -m src.outreach",
        description="Heimdall outreach pipeline — promote, interpret, send",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to clients.db (default: data/clients/clients.db)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ---- promote ----
    promote_parser = subparsers.add_parser(
        "promote",
        help="Load briefs from disk, filter, and insert into prospects table",
    )
    promote_parser.add_argument(
        "--campaign", required=True,
        help="Campaign identifier (e.g. '0426-restaurants')",
    )
    promote_parser.add_argument(
        "--bucket", nargs="+",
        help="Filter to specific buckets (e.g. --bucket A B)",
    )
    promote_parser.add_argument(
        "--industry", nargs="+",
        help="Filter to industry code prefixes (e.g. --industry 56 86)",
    )
    promote_parser.add_argument(
        "--briefs-dir",
        default="data/output/briefs",
        help="Directory containing brief JSON files (default: data/output/briefs)",
    )

    # ---- interpret ----
    interpret_parser = subparsers.add_parser(
        "interpret",
        help="Run Claude API interpretation on promoted prospects",
    )
    interpret_parser.add_argument(
        "--campaign", required=True,
        help="Campaign identifier",
    )
    interpret_parser.add_argument(
        "--min-severity",
        choices=["high", "critical"],
        default=None,
        help="Only interpret prospects with findings at this severity or above "
             "(default: include all)",
    )
    interpret_parser.add_argument(
        "--limit", type=int, default=None,
        help="Max number of prospects to interpret in this batch (for cost control)",
    )
    interpret_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be interpreted without calling the API",
    )
    interpret_parser.add_argument(
        "--tier",
        choices=["watchman", "sentinel", "guardian"],
        default="watchman",
        help="Interpretation tier — controls fix instructions (default: watchman for prospects)",
    )
    interpret_parser.add_argument(
        "--language",
        default=None,
        help="Language override for interpretation (en/da). Default: from config.",
    )

    # ---- send ----
    send_parser = subparsers.add_parser(
        "send",
        help="Compose and send Telegram messages for interpreted prospects",
    )
    send_parser.add_argument(
        "--campaign", required=True,
        help="Campaign identifier",
    )
    send_parser.add_argument(
        "--limit", type=int, default=None,
        help="Max number of messages to send in this batch",
    )
    send_parser.add_argument(
        "--dry-run", action="store_true",
        help="Compose messages and show them without sending",
    )

    # ---- export ----
    export_parser = subparsers.add_parser(
        "export",
        help="Export interpreted prospects as CSV for email mail merge",
    )
    export_parser.add_argument(
        "--campaign", required=True,
        help="Campaign identifier",
    )
    export_parser.add_argument(
        "--output", default=None,
        help="Output CSV path (default: data/output/campaign-{campaign}.csv)",
    )
    export_parser.add_argument(
        "--status", default="interpreted",
        choices=["new", "interpreted", "sent", "failed"],
        help="Export prospects with this outreach status (default: interpreted)",
    )
    export_parser.add_argument(
        "--enriched-db",
        default=None,
        help="Path to enriched companies.db (default: data/enriched/companies.db)",
    )

    return parser


def main() -> None:
    """Parse arguments and dispatch to the appropriate command."""
    parser = _build_parser()
    args = parser.parse_args()

    setup_logging(level=args.log_level.upper())

    if args.command == "promote":
        from src.outreach.promote import run_promote

        run_promote(
            campaign=args.campaign,
            buckets=args.bucket,
            industry_prefixes=args.industry,
            briefs_dir=args.briefs_dir,
            db_path=args.db_path,
        )

    elif args.command == "interpret":
        from src.outreach.interpret import run_interpret

        run_interpret(
            campaign=args.campaign,
            min_severity=args.min_severity,
            limit=args.limit,
            dry_run=args.dry_run,
            tier=args.tier,
            language=args.language,
            db_path=args.db_path,
        )

    elif args.command == "send":
        from src.outreach.send import run_send

        run_send(
            campaign=args.campaign,
            limit=args.limit,
            dry_run=args.dry_run,
            db_path=args.db_path,
        )

    elif args.command == "export":
        from src.outreach.export import run_export

        run_export(
            campaign=args.campaign,
            output=args.output,
            status=args.status,
            db_path=args.db_path,
            enriched_db_path=args.enriched_db,
        )

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from deliberation.api.app.dd_workflow_be1_migration import (
    MIGRATION_CONFIRMATION,
    ROLLBACK_CONFIRMATION,
    apply_projection_plan_to_database,
    plan_projection_migration,
    read_legacy_case_rows,
    rollback_database_projections,
    safe_migration_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run-first BE1 workflow projection migration. No source evidence is changed."
    )
    parser.add_argument("--fixture", type=Path, help="Synthetic JSON array used instead of a database.")
    parser.add_argument("--database", action="store_true", help="Explicitly permit reading the configured database for a dry run.")
    parser.add_argument("--apply", action="store_true", help="Apply only new BE1 projections; requires the write flag and confirmation.")
    parser.add_argument("--rollback", action="store_true", help="Remove only BE1 projections/events; requires the write flag and confirmation.")
    parser.add_argument("--confirm", default="", help="Exact apply/rollback confirmation token.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and args.rollback:
        raise SystemExit("Choose either --apply or --rollback, not both.")
    if args.rollback:
        if not args.database:
            raise SystemExit("--rollback requires explicit --database.")
        result = rollback_database_projections(confirmation=args.confirm)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.fixture:
        rows = json.loads(args.fixture.read_text(encoding="utf-8"))
    elif args.database:
        rows = read_legacy_case_rows()
    else:
        raise SystemExit("Provide a synthetic --fixture or explicitly opt into --database read access.")
    plan = plan_projection_migration(rows)
    print(json.dumps(safe_migration_report(plan), indent=2, sort_keys=True))
    if args.apply:
        if not args.database or args.fixture:
            raise SystemExit("--apply requires explicit --database and cannot use a fixture.")
        result = apply_projection_plan_to_database(plan, confirmation=args.confirm)
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.sim101_preflight import run_sim101_preflight


@dataclass(frozen=True)
class Sim101DryRunResult:
    passed: bool
    status: str
    started_at_utc: str
    run_mode: Optional[str]
    account: Optional[str]
    dry_run_only: bool
    dispatch_attempted: bool
    websocket_connected: bool
    telegram_connected: bool
    orders_sent: int
    preflight: dict
    report_path: str

    def to_dict(self) -> dict:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_sim101_dry_run(
    environ: Optional[Mapping[str, str]] = None,
    report_path: Optional[Path] = None,
    started_at_utc: Optional[str] = None,
) -> Sim101DryRunResult:
    env = dict(os.environ if environ is None else environ)

    destination = (
        Path(report_path)
        if report_path is not None
        else Path("analysis_reports/sim101_dry_run_report.json")
    )

    preflight = run_sim101_preflight(env)
    passed = preflight.passed

    result = Sim101DryRunResult(
        passed=passed,
        status="PASS" if passed else "FAIL",
        started_at_utc=started_at_utc or _utc_now(),
        run_mode=env.get("RUN_MODE"),
        account=(
            env.get("TRADING_ACCOUNT")
            or env.get("ACCOUNT_NAME")
            or env.get("NT_ACCOUNT")
            or env.get("NINJATRADER_ACCOUNT")
        ),
        dry_run_only=True,
        dispatch_attempted=False,
        websocket_connected=False,
        telegram_connected=False,
        orders_sent=0,
        preflight=preflight.to_dict(),
        report_path=str(destination),
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a non-dispatching Sim101 operational dry run."
    )
    parser.add_argument(
        "--report",
        default="analysis_reports/sim101_dry_run_report.json",
        help="JSON report output path.",
    )
    args = parser.parse_args(argv)

    result = run_sim101_dry_run(
        report_path=Path(args.report),
    )

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))

    if result.passed:
        print("SIM101 DRY RUN: PASS")
        return 0

    print("SIM101 DRY RUN: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

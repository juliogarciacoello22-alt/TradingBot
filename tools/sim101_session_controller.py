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

from tools.sim101_readiness import run_sim101_readiness


@dataclass(frozen=True)
class Sim101SessionControllerResult:
    passed: bool
    status: str
    started_at_utc: str
    run_mode: Optional[str]
    account: Optional[str]
    readiness_passed: bool
    controller_only: bool
    server_started: bool
    dispatch_attempted: bool
    websocket_connected: bool
    ninjatrader_connected: bool
    telegram_connected: bool
    orders_sent: int
    readiness: dict
    report_path: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _account_from_env(env: Mapping[str, str]) -> Optional[str]:
    return (
        env.get("TRADING_ACCOUNT")
        or env.get("ACCOUNT_NAME")
        or env.get("NT_ACCOUNT")
        or env.get("NINJATRADER_ACCOUNT")
    )


def run_sim101_session_controller(
    environ: Optional[Mapping[str, str]] = None,
    readiness_evidence_path: Optional[Path] = None,
    readiness_dry_run_report_path: Optional[Path] = None,
    report_path: Optional[Path] = None,
    started_at_utc: Optional[str] = None,
) -> Sim101SessionControllerResult:
    env = dict(os.environ if environ is None else environ)

    destination = (
        Path(report_path)
        if report_path is not None
        else Path("analysis_reports/sim101_session_controller_report.json")
    )

    try:
        readiness = run_sim101_readiness(
            env,
            evidence_path=readiness_evidence_path,
            dry_run_report_path=readiness_dry_run_report_path,
        )
        readiness_passed = readiness.passed
        reason = "readiness_passed" if readiness_passed else "readiness_failed"
        readiness_payload = readiness.to_dict()
    except Exception as exc:
        readiness_passed = False
        reason = f"readiness_exception:{type(exc).__name__}"
        readiness_payload = {
            "passed": False,
            "checks": [],
            "exception": type(exc).__name__,
        }

    result = Sim101SessionControllerResult(
        passed=readiness_passed,
        status="PASS" if readiness_passed else "FAIL",
        started_at_utc=started_at_utc or _utc_now(),
        run_mode=env.get("RUN_MODE"),
        account=_account_from_env(env),
        readiness_passed=readiness_passed,
        controller_only=True,
        server_started=False,
        dispatch_attempted=False,
        websocket_connected=False,
        ninjatrader_connected=False,
        telegram_connected=False,
        orders_sent=0,
        readiness=readiness_payload,
        report_path=str(destination),
        reason=reason,
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
        description="Run the non-operating Sim101 session controller."
    )
    parser.add_argument(
        "--evidence",
        default="analysis_reports/sim101_dry_run_controlled.json",
        help="Controlled dry run evidence used by readiness.",
    )
    parser.add_argument(
        "--readiness-dry-run-report",
        default="analysis_reports/sim101_session_readiness_dry_run.json",
        help="Readiness dry run output path.",
    )
    parser.add_argument(
        "--report",
        default="analysis_reports/sim101_session_controller_report.json",
        help="Session controller JSON report path.",
    )
    args = parser.parse_args(argv)

    result = run_sim101_session_controller(
        readiness_evidence_path=Path(args.evidence),
        readiness_dry_run_report_path=Path(
            args.readiness_dry_run_report
        ),
        report_path=Path(args.report),
    )

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))

    if result.passed:
        print("SIM101 SESSION CONTROLLER: PASS")
        return 0

    print("SIM101 SESSION CONTROLLER: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

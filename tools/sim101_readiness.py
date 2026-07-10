import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.sim101_dry_run import run_sim101_dry_run
from tools.sim101_preflight import run_sim101_preflight


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Sim101ReadinessResult:
    passed: bool
    checks: tuple[ReadinessCheck, ...]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
        }


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def run_sim101_readiness(
    environ: Optional[Mapping[str, str]] = None,
    evidence_path: Optional[Path] = None,
    dry_run_report_path: Optional[Path] = None,
) -> Sim101ReadinessResult:
    env = dict(os.environ if environ is None else environ)

    evidence = (
        Path(evidence_path)
        if evidence_path is not None
        else Path("analysis_reports/sim101_dry_run_controlled.json")
    )

    dry_run_report = (
        Path(dry_run_report_path)
        if dry_run_report_path is not None
        else Path("analysis_reports/sim101_readiness_dry_run.json")
    )

    preflight = run_sim101_preflight(env)
    dry_run = run_sim101_dry_run(
        env,
        report_path=dry_run_report,
    )

    evidence_data = _load_json(evidence)

    checks = (
        ReadinessCheck(
            name="preflight_passed",
            passed=preflight.passed,
            detail=f"passed={preflight.passed}",
        ),
        ReadinessCheck(
            name="dry_run_passed",
            passed=dry_run.passed,
            detail=f"status={dry_run.status}",
        ),
        ReadinessCheck(
            name="dry_run_no_dispatch",
            passed=not dry_run.dispatch_attempted,
            detail=f"dispatch_attempted={dry_run.dispatch_attempted}",
        ),
        ReadinessCheck(
            name="dry_run_zero_orders",
            passed=dry_run.orders_sent == 0,
            detail=f"orders_sent={dry_run.orders_sent}",
        ),
        ReadinessCheck(
            name="dry_run_no_websocket",
            passed=not dry_run.websocket_connected,
            detail=f"websocket_connected={dry_run.websocket_connected}",
        ),
        ReadinessCheck(
            name="dry_run_no_telegram",
            passed=not dry_run.telegram_connected,
            detail=f"telegram_connected={dry_run.telegram_connected}",
        ),
        ReadinessCheck(
            name="controlled_evidence_present",
            passed=evidence.exists(),
            detail=f"path={evidence}",
        ),
        ReadinessCheck(
            name="controlled_evidence_passed",
            passed=evidence_data.get("passed") is True,
            detail=f"passed={evidence_data.get('passed')}",
        ),
        ReadinessCheck(
            name="controlled_evidence_paper",
            passed=evidence_data.get("run_mode") == "PAPER",
            detail=f"run_mode={evidence_data.get('run_mode')}",
        ),
        ReadinessCheck(
            name="controlled_evidence_sim101",
            passed=evidence_data.get("account") == "Sim101",
            detail=f"account={evidence_data.get('account')}",
        ),
        ReadinessCheck(
            name="controlled_evidence_no_dispatch",
            passed=evidence_data.get("dispatch_attempted") is False,
            detail=(
                "dispatch_attempted="
                f"{evidence_data.get('dispatch_attempted')}"
            ),
        ),
        ReadinessCheck(
            name="controlled_evidence_zero_orders",
            passed=evidence_data.get("orders_sent") == 0,
            detail=f"orders_sent={evidence_data.get('orders_sent')}",
        ),
        ReadinessCheck(
            name="controlled_evidence_no_websocket",
            passed=evidence_data.get("websocket_connected") is False,
            detail=(
                "websocket_connected="
                f"{evidence_data.get('websocket_connected')}"
            ),
        ),
        ReadinessCheck(
            name="controlled_evidence_no_telegram",
            passed=evidence_data.get("telegram_connected") is False,
            detail=(
                "telegram_connected="
                f"{evidence_data.get('telegram_connected')}"
            ),
        ),
    )

    return Sim101ReadinessResult(
        passed=all(check.passed for check in checks),
        checks=checks,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate Sim101 operational readiness."
    )
    parser.add_argument(
        "--evidence",
        default="analysis_reports/sim101_dry_run_controlled.json",
        help="Controlled dry run evidence path.",
    )
    parser.add_argument(
        "--dry-run-report",
        default="analysis_reports/sim101_readiness_dry_run.json",
        help="Generated readiness dry run report path.",
    )
    args = parser.parse_args(argv)

    result = run_sim101_readiness(
        evidence_path=Path(args.evidence),
        dry_run_report_path=Path(args.dry_run_report),
    )

    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"[{status}] {check.name}: {check.detail}")

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))

    if result.passed:
        print("SIM101 READINESS: PASS")
        return 0

    print("SIM101 READINESS: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

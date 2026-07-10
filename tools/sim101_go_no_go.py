import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class GoNoGoCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Sim101GoNoGoResult:
    decision: str
    passed: bool
    checks: tuple[GoNoGoCheck, ...]
    dry_run_evidence_path: str
    session_controller_evidence_path: str

    def to_dict(self) -> dict:
        return {
            "decision": self.decision,
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
            "dry_run_evidence_path": self.dry_run_evidence_path,
            "session_controller_evidence_path": (
                self.session_controller_evidence_path
            ),
        }


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def evaluate_sim101_go_no_go(
    dry_run_evidence_path: Optional[Path] = None,
    session_controller_evidence_path: Optional[Path] = None,
) -> Sim101GoNoGoResult:
    dry_run_path = (
        Path(dry_run_evidence_path)
        if dry_run_evidence_path is not None
        else Path("analysis_reports/sim101_dry_run_controlled.json")
    )

    controller_path = (
        Path(session_controller_evidence_path)
        if session_controller_evidence_path is not None
        else Path(
            "analysis_reports/"
            "sim101_session_controller_controlled.json"
        )
    )

    dry_run = _load_json(dry_run_path)
    controller = _load_json(controller_path)

    checks = (
        GoNoGoCheck(
            name="dry_run_evidence_present",
            passed=dry_run_path.exists(),
            detail=f"path={dry_run_path}",
        ),
        GoNoGoCheck(
            name="controller_evidence_present",
            passed=controller_path.exists(),
            detail=f"path={controller_path}",
        ),
        GoNoGoCheck(
            name="dry_run_passed",
            passed=dry_run.get("passed") is True,
            detail=f"passed={dry_run.get('passed')}",
        ),
        GoNoGoCheck(
            name="dry_run_is_paper",
            passed=dry_run.get("run_mode") == "PAPER",
            detail=f"run_mode={dry_run.get('run_mode')}",
        ),
        GoNoGoCheck(
            name="dry_run_is_sim101",
            passed=dry_run.get("account") == "Sim101",
            detail=f"account={dry_run.get('account')}",
        ),
        GoNoGoCheck(
            name="dry_run_no_dispatch",
            passed=dry_run.get("dispatch_attempted") is False,
            detail=(
                "dispatch_attempted="
                f"{dry_run.get('dispatch_attempted')}"
            ),
        ),
        GoNoGoCheck(
            name="dry_run_zero_orders",
            passed=dry_run.get("orders_sent") == 0,
            detail=f"orders_sent={dry_run.get('orders_sent')}",
        ),
        GoNoGoCheck(
            name="dry_run_no_websocket",
            passed=dry_run.get("websocket_connected") is False,
            detail=(
                "websocket_connected="
                f"{dry_run.get('websocket_connected')}"
            ),
        ),
        GoNoGoCheck(
            name="dry_run_no_telegram",
            passed=dry_run.get("telegram_connected") is False,
            detail=(
                "telegram_connected="
                f"{dry_run.get('telegram_connected')}"
            ),
        ),
        GoNoGoCheck(
            name="controller_passed",
            passed=controller.get("passed") is True,
            detail=f"passed={controller.get('passed')}",
        ),
        GoNoGoCheck(
            name="controller_readiness_passed",
            passed=controller.get("readiness_passed") is True,
            detail=(
                "readiness_passed="
                f"{controller.get('readiness_passed')}"
            ),
        ),
        GoNoGoCheck(
            name="controller_is_paper",
            passed=controller.get("run_mode") == "PAPER",
            detail=f"run_mode={controller.get('run_mode')}",
        ),
        GoNoGoCheck(
            name="controller_is_sim101",
            passed=controller.get("account") == "Sim101",
            detail=f"account={controller.get('account')}",
        ),
        GoNoGoCheck(
            name="controller_only",
            passed=controller.get("controller_only") is True,
            detail=f"controller_only={controller.get('controller_only')}",
        ),
        GoNoGoCheck(
            name="server_not_started",
            passed=controller.get("server_started") is False,
            detail=f"server_started={controller.get('server_started')}",
        ),
        GoNoGoCheck(
            name="controller_no_dispatch",
            passed=controller.get("dispatch_attempted") is False,
            detail=(
                "dispatch_attempted="
                f"{controller.get('dispatch_attempted')}"
            ),
        ),
        GoNoGoCheck(
            name="controller_zero_orders",
            passed=controller.get("orders_sent") == 0,
            detail=f"orders_sent={controller.get('orders_sent')}",
        ),
        GoNoGoCheck(
            name="controller_no_websocket",
            passed=controller.get("websocket_connected") is False,
            detail=(
                "websocket_connected="
                f"{controller.get('websocket_connected')}"
            ),
        ),
        GoNoGoCheck(
            name="controller_no_ninjatrader",
            passed=controller.get("ninjatrader_connected") is False,
            detail=(
                "ninjatrader_connected="
                f"{controller.get('ninjatrader_connected')}"
            ),
        ),
        GoNoGoCheck(
            name="controller_no_telegram",
            passed=controller.get("telegram_connected") is False,
            detail=(
                "telegram_connected="
                f"{controller.get('telegram_connected')}"
            ),
        ),
    )

    passed = all(check.passed for check in checks)

    return Sim101GoNoGoResult(
        decision="GO" if passed else "NO-GO",
        passed=passed,
        checks=checks,
        dry_run_evidence_path=str(dry_run_path),
        session_controller_evidence_path=str(controller_path),
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the Sim101 GO/NO-GO evidence."
    )
    parser.add_argument(
        "--dry-run-evidence",
        default="analysis_reports/sim101_dry_run_controlled.json",
    )
    parser.add_argument(
        "--session-controller-evidence",
        default=(
            "analysis_reports/"
            "sim101_session_controller_controlled.json"
        ),
    )
    parser.add_argument(
        "--report",
        default="analysis_reports/sim101_go_no_go_report.json",
    )
    args = parser.parse_args(argv)

    result = evaluate_sim101_go_no_go(
        dry_run_evidence_path=Path(args.dry_run_evidence),
        session_controller_evidence_path=Path(
            args.session_controller_evidence
        ),
    )

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"[{status}] {check.name}: {check.detail}")

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    print(f"SIM101 GO/NO-GO: {result.decision}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())

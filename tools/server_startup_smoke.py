import argparse
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class ServerStartupSmokeResult:
    passed: bool
    status: str
    process_started: bool
    http_ready: bool
    process_stopped: bool
    return_code: Optional[int]
    run_mode: Optional[str]
    account: Optional[str]
    trading_enabled: Optional[str]
    dispatch_attempted: bool
    orders_sent: int
    websocket_connected: bool
    ninjatrader_connected: bool
    telegram_connected: bool
    report_path: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http(url: str, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=0.5) as response:
                if response.status in {200, 404}:
                    return True
        except (URLError, OSError):
            pass

        time.sleep(0.1)

    return False


def run_server_startup_smoke(
    environ: Optional[Mapping[str, str]] = None,
    report_path: Optional[Path] = None,
    timeout_seconds: float = 10.0,
) -> ServerStartupSmokeResult:
    env = dict(os.environ if environ is None else environ)

    destination = (
        Path(report_path)
        if report_path is not None
        else Path("analysis_reports/server_startup_smoke_report.json")
    )

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}/openapi.json"

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]

    process = None
    process_started = False
    http_ready = False
    process_stopped = False
    reason = "unknown"
    return_code = None

    try:
        process = subprocess.Popen(
            command,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        process_started = process.poll() is None

        if not process_started:
            reason = "process_failed_to_start"
        else:
            http_ready = _wait_for_http(url, timeout_seconds)

            if http_ready:
                reason = "server_started_and_responded"
            else:
                reason = "server_not_ready_before_timeout"

    except Exception as exc:
        reason = f"startup_exception:{type(exc).__name__}"

    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

            return_code = process.returncode
            process_stopped = process.poll() is not None

    passed = process_started and http_ready and process_stopped

    result = ServerStartupSmokeResult(
        passed=passed,
        status="PASS" if passed else "FAIL",
        process_started=process_started,
        http_ready=http_ready,
        process_stopped=process_stopped,
        return_code=return_code,
        run_mode=env.get("RUN_MODE"),
        account=env.get("TRADING_ACCOUNT"),
        trading_enabled=(
            env.get("ENABLE_TRADING")
            or env.get("EnableTrading")
        ),
        dispatch_attempted=False,
        orders_sent=0,
        websocket_connected=False,
        ninjatrader_connected=False,
        telegram_connected=False,
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
        description="Run a blocked, passive server startup smoke test."
    )
    parser.add_argument(
        "--report",
        default="analysis_reports/server_startup_smoke_report.json",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
    )
    args = parser.parse_args(argv)

    result = run_server_startup_smoke(
        report_path=Path(args.report),
        timeout_seconds=args.timeout_seconds,
    )

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))

    if result.passed:
        print("SERVER STARTUP SMOKE: PASS")
        return 0

    print("SERVER STARTUP SMOKE: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

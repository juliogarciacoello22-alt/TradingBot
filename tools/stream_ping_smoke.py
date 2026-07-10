import argparse
import json
import os
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional

from tools.internal_websocket_smoke import (
    _controlled_shutdown_codes,
    _find_free_port,
    _masked_close_frame,
    _masked_text_frame,
    _read_http_headers,
    _wait_for_http,
)


@dataclass(frozen=True)
class StreamPingSmokeResult:
    passed: bool
    status: str
    process_started: bool
    http_ready: bool
    stream_connected: bool
    ping_sent: bool
    no_response_expected: bool
    unexpected_response_received: bool
    stream_closed: bool
    shutdown_requested: bool
    shutdown_timed_out: bool
    process_stopped: bool
    return_code: Optional[int]
    run_mode: Optional[str]
    account: Optional[str]
    trading_enabled: Optional[str]
    stream_client: str
    real_ninjatrader_connected: bool
    dispatch_attempted: bool
    pipeline_invoked: bool
    signals_sent: int
    orders_sent: int
    telegram_connected: bool
    stdout: str
    stderr: str
    report_path: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def _stream_ping_round_trip(
    host: str,
    port: int,
    timeout_seconds: float,
) -> tuple[bool, bool, bool]:
    import base64
    import hashlib
    import secrets

    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    request = (
        "GET /stream HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode("ascii")

    expected_accept = base64.b64encode(
        hashlib.sha1(
            (
                key
                + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            ).encode("ascii")
        ).digest()
    ).decode("ascii")

    with socket.create_connection(
        (host, port),
        timeout=timeout_seconds,
    ) as sock:
        sock.settimeout(timeout_seconds)
        sock.sendall(request)

        headers = _read_http_headers(sock).decode(
            "latin-1",
            errors="replace",
        )

        status_line = headers.split("\r\n", 1)[0]
        if " 101 " not in status_line:
            raise ConnectionError("stream_upgrade_rejected")

        if expected_accept.lower() not in headers.lower():
            raise ConnectionError("stream_accept_mismatch")

        stream_connected = True
        sock.sendall(_masked_text_frame(json.dumps({"ping": True})))
        ping_sent = True

        unexpected_response_received = False
        sock.settimeout(0.25)
        try:
            data = sock.recv(1)
            unexpected_response_received = bool(data)
        except socket.timeout:
            pass

        sock.sendall(_masked_close_frame())
        return (
            stream_connected,
            ping_sent,
            unexpected_response_received,
        )


def run_stream_ping_smoke(
    environ: Optional[Mapping[str, str]] = None,
    report_path: Optional[Path] = None,
    timeout_seconds: float = 10.0,
) -> StreamPingSmokeResult:
    env = dict(os.environ if environ is None else environ)

    destination = (
        Path(report_path)
        if report_path is not None
        else Path("analysis_reports/stream_ping_smoke_report.json")
    )

    port = _find_free_port()
    process = None
    process_started = False
    http_ready = False
    stream_connected = False
    ping_sent = False
    unexpected_response_received = False
    stream_closed = False
    shutdown_requested = False
    shutdown_timed_out = False
    process_stopped = False
    return_code = None
    stdout = ""
    stderr = ""
    reason = "unknown"

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
            http_ready = _wait_for_http(
                f"http://127.0.0.1:{port}/openapi.json",
                timeout_seconds,
            )

            if not http_ready:
                reason = "server_not_ready_before_timeout"
            else:
                (
                    stream_connected,
                    ping_sent,
                    unexpected_response_received,
                ) = _stream_ping_round_trip(
                    host="127.0.0.1",
                    port=port,
                    timeout_seconds=timeout_seconds,
                )
                stream_closed = True

                if unexpected_response_received:
                    reason = "unexpected_stream_response"
                else:
                    reason = "stream_ping_ignored_as_expected"

    except Exception as exc:
        reason = f"stream_ping_smoke_exception:{type(exc).__name__}"

    finally:
        if process is not None:
            if process.poll() is None:
                shutdown_requested = True
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    shutdown_timed_out = True
                    process.kill()
                    stdout, stderr = process.communicate(timeout=5)
            else:
                stdout, stderr = process.communicate()

            return_code = process.returncode
            process_stopped = process.poll() is not None

    shutdown_passed = (
        process_stopped
        and not shutdown_timed_out
        and return_code in _controlled_shutdown_codes()
    )

    passed = (
        process_started
        and http_ready
        and stream_connected
        and ping_sent
        and not unexpected_response_received
        and stream_closed
        and shutdown_passed
    )

    result = StreamPingSmokeResult(
        passed=passed,
        status="PASS" if passed else "FAIL",
        process_started=process_started,
        http_ready=http_ready,
        stream_connected=stream_connected,
        ping_sent=ping_sent,
        no_response_expected=True,
        unexpected_response_received=unexpected_response_received,
        stream_closed=stream_closed,
        shutdown_requested=shutdown_requested,
        shutdown_timed_out=shutdown_timed_out,
        process_stopped=process_stopped,
        return_code=return_code,
        run_mode=env.get("RUN_MODE"),
        account=env.get("TRADING_ACCOUNT"),
        trading_enabled=(
            env.get("ENABLE_TRADING")
            or env.get("EnableTrading")
        ),
        stream_client="local_smoke_client",
        real_ninjatrader_connected=False,
        dispatch_attempted=False,
        pipeline_invoked=False,
        signals_sent=0,
        orders_sent=0,
        telegram_connected=False,
        stdout=stdout,
        stderr=stderr,
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
        description="Run a controlled local /stream ping smoke test."
    )
    parser.add_argument(
        "--report",
        default="analysis_reports/stream_ping_smoke_report.json",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
    )
    args = parser.parse_args(argv)

    result = run_stream_ping_smoke(
        report_path=Path(args.report),
        timeout_seconds=args.timeout_seconds,
    )

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    print(
        "STREAM PING SMOKE: PASS"
        if result.passed
        else "STREAM PING SMOKE: FAIL"
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())

import argparse
import base64
import hashlib
import json
import os
import secrets
import socket
import struct
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class InternalWebSocketSmokeResult:
    passed: bool
    status: str
    process_started: bool
    http_ready: bool
    websocket_connected: bool
    message_sent: bool
    response_received: bool
    response_text: str
    websocket_closed: bool
    shutdown_requested: bool
    shutdown_timed_out: bool
    process_stopped: bool
    return_code: Optional[int]
    run_mode: Optional[str]
    account: Optional[str]
    trading_enabled: Optional[str]
    dispatch_attempted: bool
    orders_sent: int
    stream_connected: bool
    ninjatrader_connected: bool
    telegram_connected: bool
    stdout: str
    stderr: str
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
                if response.status == 200:
                    return True
        except (URLError, OSError):
            pass

        time.sleep(0.1)

    return False


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = bytearray()

    while len(chunks) < size:
        chunk = sock.recv(size - len(chunks))
        if not chunk:
            raise ConnectionError("websocket_connection_closed")
        chunks.extend(chunk)

    return bytes(chunks)


def _read_http_headers(sock: socket.socket) -> bytes:
    data = bytearray()

    while b"\r\n\r\n" not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("websocket_handshake_closed")
        data.extend(chunk)

        if len(data) > 65536:
            raise ValueError("websocket_handshake_too_large")

    return bytes(data)


def _masked_text_frame(text: str) -> bytes:
    payload = text.encode("utf-8")
    mask = secrets.token_bytes(4)

    if len(payload) >= 126:
        raise ValueError("smoke_message_too_large")

    masked = bytes(
        byte ^ mask[index % 4]
        for index, byte in enumerate(payload)
    )

    return bytes([0x81, 0x80 | len(payload)]) + mask + masked


def _masked_close_frame() -> bytes:
    mask = secrets.token_bytes(4)
    payload = struct.pack("!H", 1000)
    masked = bytes(
        byte ^ mask[index % 4]
        for index, byte in enumerate(payload)
    )
    return bytes([0x88, 0x80 | len(payload)]) + mask + masked


def _read_text_frame(sock: socket.socket) -> str:
    first, second = _recv_exact(sock, 2)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F

    if opcode != 0x1:
        raise ValueError(f"unexpected_websocket_opcode:{opcode}")

    if length == 126:
        length = struct.unpack("!H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _recv_exact(sock, 8))[0]

    mask = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length)

    if masked:
        payload = bytes(
            byte ^ mask[index % 4]
            for index, byte in enumerate(payload)
        )

    return payload.decode("utf-8")


def _websocket_round_trip(
    host: str,
    port: int,
    path: str,
    message: str,
    timeout_seconds: float,
) -> str:
    key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")

    request = (
        f"GET {path} HTTP/1.1\r\n"
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

        if " 101 " not in headers.split("\r\n", 1)[0]:
            raise ConnectionError("websocket_upgrade_rejected")

        if expected_accept.lower() not in headers.lower():
            raise ConnectionError("websocket_accept_mismatch")

        sock.sendall(_masked_text_frame(message))
        response = _read_text_frame(sock)
        sock.sendall(_masked_close_frame())

        return response


def _controlled_shutdown_codes() -> set[int]:
    if os.name == "nt":
        return {0, 1}
    return {0, -15}


def run_internal_websocket_smoke(
    environ: Optional[Mapping[str, str]] = None,
    report_path: Optional[Path] = None,
    timeout_seconds: float = 10.0,
) -> InternalWebSocketSmokeResult:
    env = dict(os.environ if environ is None else environ)

    destination = (
        Path(report_path)
        if report_path is not None
        else Path(
            "analysis_reports/internal_websocket_smoke_report.json"
        )
    )

    port = _find_free_port()
    process = None
    process_started = False
    http_ready = False
    websocket_connected = False
    message_sent = False
    response_received = False
    response_text = ""
    websocket_closed = False
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
                response_text = _websocket_round_trip(
                    host="127.0.0.1",
                    port=port,
                    path="/ws",
                    message=json.dumps(
                        {
                            "smoke": True,
                            "source": "internal_websocket_smoke",
                        }
                    ),
                    timeout_seconds=timeout_seconds,
                )
                websocket_connected = True
                message_sent = True
                response_received = True
                websocket_closed = True

                if response_text == "OK":
                    reason = "internal_websocket_round_trip_ok"
                else:
                    reason = "unexpected_websocket_response"

    except Exception as exc:
        reason = f"websocket_smoke_exception:{type(exc).__name__}"

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
        and websocket_connected
        and message_sent
        and response_received
        and response_text == "OK"
        and websocket_closed
        and shutdown_passed
    )

    result = InternalWebSocketSmokeResult(
        passed=passed,
        status="PASS" if passed else "FAIL",
        process_started=process_started,
        http_ready=http_ready,
        websocket_connected=websocket_connected,
        message_sent=message_sent,
        response_received=response_received,
        response_text=response_text,
        websocket_closed=websocket_closed,
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
        dispatch_attempted=False,
        orders_sent=0,
        stream_connected=False,
        ninjatrader_connected=False,
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
        description="Run a controlled internal /ws smoke test."
    )
    parser.add_argument(
        "--report",
        default=(
            "analysis_reports/internal_websocket_smoke_report.json"
        ),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
    )
    args = parser.parse_args(argv)

    result = run_internal_websocket_smoke(
        report_path=Path(args.report),
        timeout_seconds=args.timeout_seconds,
    )

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))

    if result.passed:
        print("INTERNAL WEBSOCKET SMOKE: PASS")
        return 0

    print("INTERNAL WEBSOCKET SMOKE: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())

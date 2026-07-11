import json
import tempfile
import unittest
from pathlib import Path

from tools.analyze_post_decision_outcomes import (
    SessionValidationError,
    analyze_session,
    build_report,
    discover_sessions,
    extract_side,
    format_markdown,
    write_reports,
)


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _decision(side=None, reason="ok"):
    detail = "structured decision"
    if side:
        detail += f" side={side} accepted"
    return {
        "terminal_stage": "final_signal",
        "terminal_reason": reason,
        "terminal_subreason": "none",
        "build_signal_reason": "scalper_generated",
        "valid_entry_reason": "ok",
        "ob_reason": "ok",
        "timing_reason": "ok",
        "detail": detail,
    }


def _snapshot(index, close=None, high=None, low=None, timestamp=None):
    close = 100.0 + index if close is None else close
    return {
        "event": "signal_engine_v4_full_path_snapshot",
        "snapshot": {
            "decision_id": f"decision-{index}",
            "timestamp": index if timestamp is None else timestamp,
            "price": close,
            "last_candle": {
                "close": close,
                "high": close + 1.0 if high is None else high,
                "low": close - 1.0 if low is None else low,
                "instrument": "NQ",
                "barType": "Minute",
                "barSize": 1,
            },
        },
    }


def _session(root, name, decisions, snapshots):
    session = root / name
    session.mkdir(parents=True)
    _write_jsonl(session / "pipeline_decisions.jsonl", decisions)
    _write_jsonl(session / "signal_engine_full_path_snapshots.jsonl", snapshots)
    return session


class AnalyzePostDecisionOutcomesTests(unittest.TestCase):
    def test_ordinal_alignment_and_snapshot_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(
                Path(tmp),
                "aligned",
                [_decision("BUY"), _decision("SELL")],
                [_snapshot(0), _snapshot(1)],
            )
            result = analyze_session(session)

        self.assertEqual(result["outcomes"][0]["decision_id"], "decision-0")
        self.assertEqual(result["outcomes"][0]["side"], "BUY")
        self.assertEqual(result["outcomes"][1]["decision_id"], "decision-1")
        self.assertEqual(result["outcomes"][1]["side"], "SELL")
        self.assertEqual(result["outcomes"][0]["instrument"], "NQ")

    def test_unequal_record_counts_abort_only_bad_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _session(root, "bad", [_decision(), _decision()], [_snapshot(0)])
            _session(root, "good", [_decision()], [_snapshot(0)])
            report = build_report(discover_sessions(root))

        self.assertEqual(report["sessions_analyzed"], 1)
        self.assertEqual(report["sessions_invalid"], 1)
        self.assertEqual(report["sessions"][0]["session_id"], "good")
        self.assertIn("record_count_mismatch", report["invalid_sessions"][0]["reason"])
        self.assertEqual(len(report["outcomes"]), 1)

    def test_non_increasing_timestamps_abort_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(
                Path(tmp),
                "bad-time",
                [_decision(), _decision()],
                [_snapshot(0, timestamp=10), _snapshot(1, timestamp=10)],
            )
            with self.assertRaisesRegex(
                SessionValidationError, "not_strictly_increasing"
            ):
                analyze_session(session)

    def test_iso_8601_timestamps_are_validated_and_preserved(self):
        snapshots = [
            _snapshot(0, timestamp="2026-01-02T09:30:00-06:00"),
            _snapshot(1, timestamp="2026-01-02T09:31:00-06:00"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(
                Path(tmp), "iso-time", [_decision(), _decision()], snapshots
            )
            result = analyze_session(session)

        self.assertEqual(
            result["outcomes"][0]["timestamp"], "2026-01-02T09:30:00-06:00"
        )

    def test_side_extraction_buy_sell_and_absent(self):
        self.assertEqual(extract_side("x side=BUY y"), "BUY")
        self.assertEqual(extract_side("side = sell"), "SELL")
        self.assertIsNone(extract_side("no direction"))
        self.assertIsNone(extract_side(None))

    def test_close_plus_5_and_buy_returns(self):
        snapshots = [_snapshot(i) for i in range(7)]
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(
                Path(tmp), "buy", [_decision("BUY") for _ in snapshots], snapshots
            )
            horizon = analyze_session(session)["outcomes"][0]["horizons"]["5"]

        self.assertEqual(horizon["close"], 105.0)
        self.assertAlmostEqual(horizon["raw_return"], 0.05)
        self.assertAlmostEqual(horizon["signed_return"], 0.05)

    def test_buy_mfe_and_mae(self):
        snapshots = [_snapshot(i) for i in range(6)]
        snapshots[2]["snapshot"]["last_candle"]["high"] = 112.0
        snapshots[3]["snapshot"]["last_candle"]["low"] = 92.0
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(
                Path(tmp), "buy-excursion", [_decision("BUY") for _ in snapshots], snapshots
            )
            horizon = analyze_session(session)["outcomes"][0]["horizons"]["5"]

        self.assertAlmostEqual(horizon["MFE"], 0.12)
        self.assertAlmostEqual(horizon["MAE"], -0.08)

    def test_sell_signed_return_mfe_and_mae(self):
        snapshots = [_snapshot(i, close=100.0 - i) for i in range(6)]
        snapshots[2]["snapshot"]["last_candle"]["low"] = 88.0
        snapshots[4]["snapshot"]["last_candle"]["high"] = 108.0
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(
                Path(tmp),
                "sell-excursion",
                [_decision("SELL") for _ in snapshots],
                snapshots,
            )
            horizon = analyze_session(session)["outcomes"][0]["horizons"]["5"]

        self.assertAlmostEqual(horizon["raw_return"], -0.05)
        self.assertAlmostEqual(horizon["signed_return"], 0.05)
        self.assertAlmostEqual(horizon["MFE"], 0.12)
        self.assertAlmostEqual(horizon["MAE"], -0.08)

    def test_absent_side_has_no_directional_derivatives(self):
        snapshots = [_snapshot(i) for i in range(6)]
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(
                Path(tmp), "no-side", [_decision() for _ in snapshots], snapshots
            )
            horizon = analyze_session(session)["outcomes"][0]["horizons"]["5"]

        self.assertAlmostEqual(horizon["raw_return"], 0.05)
        self.assertIsNone(horizon["signed_return"])
        self.assertIsNone(horizon["MFE"])
        self.assertIsNone(horizon["MAE"])

    def test_insufficient_future_data_nulls_all_derived_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(Path(tmp), "short", [_decision("BUY")], [_snapshot(0)])
            horizon = analyze_session(session)["outcomes"][0]["horizons"]["5"]

        self.assertEqual(horizon["status"], "insufficient_future_data")
        for field in ("close", "raw_return", "signed_return", "MFE", "MAE"):
            self.assertIsNone(horizon[field])

    def test_aggregates_include_complete_insufficient_and_favorable_rate(self):
        snapshots = [_snapshot(i) for i in range(7)]
        decisions = [_decision("BUY", "ok") for _ in snapshots]
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(Path(tmp), "aggregate", decisions, snapshots)
            report = build_report([session])

        group = report["aggregates"]["side"][0]
        stats = group["horizons"]["5"]
        self.assertEqual(group["value"], "BUY")
        self.assertEqual(group["count"], 7)
        self.assertEqual(stats["complete_samples"], 2)
        self.assertEqual(stats["insufficient_samples"], 5)
        self.assertAlmostEqual(stats["mean"], (0.05 + 5 / 101) / 2)
        self.assertEqual(stats["favorable_close_rate"], 1.0)

    def test_markdown_contains_validation_and_aggregate_tables(self):
        report = build_report([])
        markdown = format_markdown(report)

        self.assertIn("# BIUMOLO Offline Post-Decision Outcomes", markdown)
        self.assertIn("## Session validation", markdown)
        self.assertIn("## Aggregate by `terminal_stage`", markdown)
        self.assertIn("Favorable close rate", markdown)

    def test_reports_use_utf8_bom_convention_and_preserve_unicode(self):
        report = build_report([])
        report["invalid_sessions"].append(
            {"session_id": "sesión", "session_path": "x", "reason": "razón"}
        )
        report["sessions_invalid"] = 1
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "report.json"
            md_path = Path(tmp) / "report.md"
            write_reports(report, json_path, md_path)
            json_bytes = json_path.read_bytes()
            md_bytes = md_path.read_bytes()

        self.assertTrue(json_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(md_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertIn("sesión", json_bytes.decode("utf-8-sig"))
        self.assertIn("razón", md_bytes.decode("utf-8-sig"))

    def test_missing_pair_member_is_reported_and_other_sessions_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incomplete = root / "incomplete"
            incomplete.mkdir()
            _write_jsonl(incomplete / "pipeline_decisions.jsonl", [_decision()])
            _session(root, "complete", [_decision()], [_snapshot(0)])
            report = build_report(discover_sessions(root))

        self.assertEqual(report["sessions_discovered"], 2)
        self.assertEqual(report["sessions_analyzed"], 1)
        self.assertIn("missing_required_files", report["invalid_sessions"][0]["reason"])


if __name__ == "__main__":
    unittest.main()

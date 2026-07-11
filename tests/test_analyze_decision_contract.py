import json
import tempfile
import unittest
from pathlib import Path

from tools.analyze_decision_contract import (
    analyze_session,
    build_filter_analysis,
    build_funnel,
    build_outcome_extremes,
    build_report,
    discover_sessions,
    format_markdown,
    write_reports,
)


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _decision(
    *,
    terminal_reason="valid_entry_failed",
    terminal_subreason="missing_displacement",
    valid_entry_reason="missing_displacement",
    ob_reason="raw_ob_missing",
    timing_reason="ok",
    build_reason="valid_entry_failed",
    side=None,
    allowed=False,
):
    final = terminal_reason == "ok"
    return {
        "terminal_stage": "final_signal" if final else "build_signal",
        "terminal_reason": terminal_reason,
        "terminal_subreason": terminal_subreason,
        "build_signal_reason": build_reason,
        "valid_entry_reason": valid_entry_reason,
        "ob_reason": ob_reason,
        "timing_reason": timing_reason,
        "detail": f"side={side} mode=SCALPER" if side else "side=None mode=None",
        "allowed": allowed,
    }


def _snapshot(index, *, close=None, high=None, low=None, micro=None):
    close = 100.0 + index if close is None else close
    return {
        "snapshot": {
            "timestamp": index,
            "price": close,
            "last_candle": {
                "close": close,
                "high": close + 1 if high is None else high,
                "low": close - 1 if low is None else low,
            },
            "microstructure": micro
            or {
                "displacement": "up",
                "momentum": "up",
                "fake_displacement": False,
                "mitigation_light": False,
            },
        }
    }


def _session(root, decisions, snapshots, summary=None):
    session = root / "fixture"
    session.mkdir()
    _write_jsonl(session / "pipeline_decisions.jsonl", decisions)
    _write_jsonl(session / "signal_engine_full_path_snapshots.jsonl", snapshots)
    (session / "session_summary.json").write_text(
        json.dumps(summary or {}, ensure_ascii=False), encoding="utf-8"
    )
    return session


class DecisionContractDiagnosisTests(unittest.TestCase):
    def test_decision_funnel_counts_percentages_and_drops(self):
        records = [
            _decision(),
            _decision(ob_reason="ok"),
            _decision(ob_reason="ok", valid_entry_reason="entry_filters_passed"),
            _decision(
                terminal_reason="execution_rejected",
                terminal_subreason="execution_filter",
                ob_reason="ok",
                valid_entry_reason="entry_filters_passed",
                build_reason="scalper_generated",
            ),
            _decision(
                terminal_reason="ok",
                terminal_subreason=None,
                ob_reason="ok",
                valid_entry_reason="entry_filters_passed",
                build_reason="scalper_generated",
                side="BUY",
                allowed=True,
            ),
        ]
        funnel = build_funnel(records)
        counts = {stage["stage"]: stage["count"] for stage in funnel["stages"]}

        self.assertEqual(counts["pipeline_decisions"], 5)
        self.assertEqual(counts["ob_valid"], 4)
        self.assertEqual(counts["valid_entry_passed"], 3)
        self.assertEqual(counts["build_signal"], 2)
        self.assertEqual(counts["final_signal"], 1)
        self.assertEqual(counts["execution"], 1)
        self.assertEqual(funnel["stages"][1]["percentage"], 80.0)
        self.assertEqual(funnel["stages"][1]["drop_from_previous"], 1)

    def test_exact_terminal_rankings_use_pipeline_denominator(self):
        decisions = [
            _decision(),
            _decision(),
            _decision(terminal_reason="timing_invalid", terminal_subreason="low volatility"),
        ]
        snapshots = [_snapshot(i) for i in range(3)]
        with tempfile.TemporaryDirectory() as tmp:
            report = build_report([_session(Path(tmp), decisions, snapshots)])

        ranking = report["terminal_reason_ranking"]
        self.assertEqual(ranking[0]["reason"], "valid_entry_failed")
        self.assertEqual(ranking[0]["count"], 2)
        self.assertAlmostEqual(ranking[0]["percentage"], 200 / 3)
        self.assertEqual(report["terminal_subreason_ranking"][0]["reason"], "missing_displacement")

    def test_filter_concentration_first_blocker_and_overlap_matrix(self):
        records = [
            {
                **_decision(),
                "first_blocking_reason": "missing_displacement",
                "active_filters": [
                    "missing_displacement",
                    "mitigation_light_true",
                    "raw_ob_missing",
                ],
            },
            {
                **_decision(
                    terminal_subreason="mitigation_light_true",
                    valid_entry_reason="mitigation_light_true",
                ),
                "first_blocking_reason": "mitigation_light_true",
                "active_filters": ["mitigation_light_true", "raw_ob_missing"],
            },
        ]
        analysis = build_filter_analysis(records)

        self.assertEqual(
            analysis["overlap_matrix"]["missing_displacement"]["mitigation_light_true"],
            1,
        )
        mitigation = next(
            item for item in analysis["ranking"] if item["filter"] == "mitigation_light_true"
        )
        self.assertEqual(mitigation["count"], 2)
        self.assertEqual(mitigation["first_blocking_count"], 1)
        self.assertEqual(mitigation["first_blocking_reason_frequency"], 50.0)
        self.assertEqual(
            analysis["top_two_concentration_over_blocked_setups_percentage"], 100.0
        )
        pair = next(
            item
            for item in analysis["overlap_ranking"]
            if {item["left"], item["right"]}
            == {"missing_displacement", "mitigation_light_true"}
        )
        self.assertEqual(pair["dominant_filter"], "mitigation_light_true")

    def test_false_negative_ranks_blocked_setup_by_mfe(self):
        decisions = [_decision() for _ in range(22)]
        snapshots = [_snapshot(i) for i in range(22)]
        snapshots[0] = _snapshot(
            0,
            micro={
                "displacement": "up",
                "momentum": "up",
                "mitigation_light": True,
                "fake_displacement": False,
            },
        )
        snapshots[10]["snapshot"]["last_candle"]["high"] = 150.0
        with tempfile.TemporaryDirectory() as tmp:
            session = analyze_session(_session(Path(tmp), decisions, snapshots))
            structured = [row for row in session["records"] if row["structured"]]
            extremes = build_outcome_extremes(structured)

        top = extremes["top_20_blocked_strongest_favorable"][0]
        self.assertEqual(top["classification"], "blocked_then_favorable")
        self.assertEqual(top["side"], "BUY")
        self.assertEqual(top["blocking_reason"], "valid_entry_failed")
        self.assertAlmostEqual(top["MFE"], 0.5)

    def test_false_positive_ranks_accepted_worst_signed_return(self):
        decisions = [
            _decision(
                terminal_reason="ok",
                terminal_subreason=None,
                valid_entry_reason="entry_filters_passed",
                ob_reason="ok",
                build_reason="scalper_generated",
                side="BUY",
                allowed=True,
            )
            for _ in range(23)
        ]
        snapshots = [_snapshot(i, close=100.0 - i) for i in range(23)]
        with tempfile.TemporaryDirectory() as tmp:
            session = analyze_session(_session(Path(tmp), decisions, snapshots))
            extremes = build_outcome_extremes(session["records"])

        top = extremes["top_20_accepted_worst_outcome"][0]
        self.assertEqual(top["classification"], "accepted_then_adverse")
        self.assertEqual(top["side"], "BUY")
        self.assertEqual(top["timestamp"], 2)
        self.assertAlmostEqual(top["future_return"], -20 / 98)

    def test_markdown_contains_required_sections_and_evidence(self):
        report = build_report([])
        markdown = format_markdown(report)

        self.assertIn("# BIUMOLO Decision Contract Diagnosis", markdown)
        self.assertIn("## Decision funnel", markdown)
        self.assertIn("## Filter overlap ranking", markdown)
        self.assertIn("## Engineering findings", markdown)
        self.assertNotIn("recommend", markdown.lower())

    def test_json_and_markdown_are_utf8_bom(self):
        report = build_report([])
        report["engineering_findings"].append(
            {"finding": "evidencia", "evidence": "concentración exacta"}
        )
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "diagnosis.json"
            md_path = Path(tmp) / "diagnosis.md"
            write_reports(report, json_path, md_path)
            json_bytes = json_path.read_bytes()
            md_bytes = md_path.read_bytes()

        self.assertTrue(json_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(md_bytes.startswith(b"\xef\xbb\xbf"))
        payload = json.loads(json_bytes.decode("utf-8-sig"))
        self.assertEqual(payload["analysis"], "offline_decision_contract_diagnosis")
        self.assertIn("concentración", md_bytes.decode("utf-8-sig"))

    def test_discovery_and_summary_reconciliation(self):
        decisions = [_decision()]
        snapshots = [_snapshot(0)]
        summary = {
            "total_pipeline_executed": 1,
            "total_build_signal_generated": 0,
            "total_final_signals": 0,
            "total_execution_rejected": 0,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = _session(root, decisions, snapshots, summary)
            discovered = discover_sessions(root)
            analyzed = analyze_session(session)

        self.assertEqual(discovered, [session])
        self.assertTrue(analyzed["summary_reconciliation"]["summary_present"])
        self.assertTrue(
            all(check["matches"] for check in analyzed["summary_reconciliation"]["checks"])
        )


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from tools.analyze_filter_scorecard import (
    SessionValidationError,
    analyze_session,
    build_rankings,
    build_report,
    build_scorecards,
    classify_state,
    discover_filter_names,
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
    first="novel_filter_true",
    terminal_reason="valid_entry_failed",
    accepted=False,
    side=None,
    extra=None,
):
    row = {
        "terminal_stage": "final_signal" if accepted else "build_signal",
        "terminal_reason": "ok" if accepted else terminal_reason,
        "terminal_subreason": None if accepted else first,
        "valid_entry_reason": "entry_filters_passed" if accepted else first,
        "ob_reason": "ok" if accepted else "raw_ob_missing",
        "timing_reason": "ok",
        "build_signal_reason": "scalper_generated" if accepted else "valid_entry_failed",
        "detail": f"side={side} mode=SCALPER" if side else "side=None mode=None",
        "allowed": accepted,
    }
    row.update(extra or {})
    return row


def _snapshot(index, *, close=None, high=None, low=None, micro=None, timestamp=None):
    close = 100.0 + index if close is None else close
    return {
        "snapshot": {
            "timestamp": index if timestamp is None else timestamp,
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
                "novel_filter": True,
            },
        }
    }


def _session(root, name, decisions, snapshots, *, summary=True):
    session = root / name
    session.mkdir()
    _write_jsonl(session / "pipeline_decisions.jsonl", decisions)
    _write_jsonl(session / "signal_engine_full_path_snapshots.jsonl", snapshots)
    if summary:
        (session / "session_summary.json").write_text("{}", encoding="utf-8")
    return session


def _score_record(
    name,
    *,
    first=None,
    returns=(0.1, 0.1, 0.1, 0.1),
    status="complete",
    terminal_reason="valid_entry_failed",
):
    return {
        "session_id": "fixture",
        "timestamp": 1,
        "terminal_reason": terminal_reason,
        "terminal_subreason": first,
        "first_block": first,
        "reason_fields": {
            "terminal_reason": terminal_reason,
            "terminal_subreason": first,
            "new_gate_reason": name,
        },
        "features": {},
        "side": "BUY",
        "outcomes": {
            str(horizon): {
                "status": status,
                "return": value if status == "complete" else None,
                "MFE": abs(value) + 0.01 if status == "complete" else None,
                "MAE": -0.02 if status == "complete" else None,
                "close": 101 if status == "complete" else None,
            }
            for horizon, value in zip((5, 10, 20, 50), returns)
        },
    }


class AnalyzeFilterScorecardTests(unittest.TestCase):
    def test_automatic_filter_discovery_includes_future_reason_field(self):
        records = [
            _score_record("brand_new_gate", first="first_gate"),
            {
                **_score_record("pass_value", first=None, terminal_reason="ok"),
                "reason_fields": {
                    "terminal_reason": "ok",
                    "new_gate_reason": "pass_value",
                },
            },
        ]

        filters = discover_filter_names(records)

        self.assertIn("brand_new_gate", filters)
        self.assertIn("first_gate", filters)
        self.assertNotIn("pass_value", filters)

    def test_coverage_first_and_later_blocks(self):
        records = [
            _score_record("shared_filter", first="shared_filter"),
            _score_record("shared_filter", first="other_filter"),
        ]

        card = next(card for card in build_scorecards(records) if card["filter"] == "shared_filter")

        self.assertEqual(card["coverage"]["total_blocks"], 2)
        self.assertEqual(card["coverage"]["first_blocks"], 1)
        self.assertEqual(card["coverage"]["later_blocks"], 1)
        self.assertEqual(card["coverage"]["percentage_of_structured_pipeline"], 100.0)
        self.assertEqual(card["coverage"]["percentage_within_valid_entry_failed"], 100.0)

    def test_generic_filter_predicate_detects_later_block_without_name_allowlist(self):
        first = _score_record("pass", first="missing_future_feature")
        first["features"] = {"future_feature": None}
        later = _score_record("other_value", first="other_filter")
        later["reason_fields"] = {
            "terminal_reason": "valid_entry_failed",
            "terminal_subreason": "other_filter",
        }
        later["features"] = {"future_feature": None}

        card = next(
            card
            for card in build_scorecards([first, later])
            if card["filter"] == "missing_future_feature"
        )

        self.assertEqual(card["coverage"]["total_blocks"], 2)
        self.assertEqual(card["coverage"]["first_blocks"], 1)
        self.assertEqual(card["coverage"]["later_blocks"], 1)

    def test_outcome_metrics_and_filter_economy(self):
        records = [
            _score_record("economic_filter", first="economic_filter", returns=(0.1, 0.2, 0.3, 0.4)),
            _score_record("economic_filter", first="economic_filter", returns=(-0.1, -0.2, -0.1, -0.4)),
        ]

        card = next(card for card in build_scorecards(records) if card["filter"] == "economic_filter")
        metric = card["outcomes"]["20"]

        self.assertAlmostEqual(metric["mean_return"], 0.1)
        self.assertAlmostEqual(metric["median_return"], 0.1)
        self.assertAlmostEqual(metric["mean_MFE"], 0.21)
        self.assertAlmostEqual(metric["mean_MAE"], -0.02)
        self.assertEqual(metric["favorable_close_rate"], 0.5)
        self.assertEqual(card["economics"]["filter_cost"], 1)
        self.assertEqual(card["economics"]["filter_benefit"], 1)
        self.assertEqual(card["quality"]["estimated_false_negative_rate"], 0.5)
        self.assertEqual(card["quality"]["estimated_protection_rate"], 0.5)

    def test_representative_cases_are_exactly_best_worst_and_median(self):
        records = [
            _score_record("case_filter", first="case_filter", returns=(value,) * 4)
            for value in (-0.2, 0.1, 0.5)
        ]
        records[0]["timestamp"] = 1
        records[1]["timestamp"] = 2
        records[2]["timestamp"] = 3

        card = next(card for card in build_scorecards(records) if card["filter"] == "case_filter")
        cases = card["representative_cases"]

        self.assertEqual(set(cases), {"best_block", "worst_block", "representative_case"})
        self.assertEqual(cases["best_block"]["timestamp"], 3)
        self.assertEqual(cases["worst_block"]["timestamp"], 1)
        self.assertEqual(cases["representative_case"]["timestamp"], 2)
        for case in cases.values():
            self.assertEqual(
                set(case),
                {
                    "session_id",
                    "timestamp",
                    "side",
                    "terminal_reason",
                    "terminal_subreason",
                    "return",
                    "MFE",
                    "MAE",
                },
            )

    def test_classification_rules_cover_all_states(self):
        self.assertEqual(classify_state("LOW", "HIGH", "HIGH"), "KEEP")
        self.assertEqual(classify_state("HIGH", "LOW", "MEDIUM"), "EXPERIMENT")
        self.assertEqual(classify_state("HIGH", "LOW", "LOW"), "INVESTIGATE")
        self.assertEqual(classify_state("MEDIUM", "MEDIUM", "HIGH"), "INVESTIGATE")

    def test_decision_trace_is_derived_and_reproducible(self):
        records = [
            _score_record("trace_filter", first="trace_filter", returns=(0.2,) * 4)
            for _ in range(120)
        ]
        card = next(card for card in build_scorecards(records) if card["filter"] == "trace_filter")
        trace = card["decision_trace"]

        self.assertEqual(trace["Sample size"], "HIGH")
        self.assertEqual(trace["Estimated Cost"], "HIGH")
        self.assertEqual(trace["Estimated Benefit"], "LOW")
        self.assertEqual(trace["Confidence"], "HIGH")
        self.assertEqual(trace["State"], "EXPERIMENT")
        self.assertIn("tercile", trace["Coverage basis"])
        self.assertIn("Wilson 95%", trace["rule"])

    def test_rankings_order_impact_cost_benefit_and_uncertainty(self):
        high_cost = [
            _score_record("high_cost", first="high_cost", returns=(0.2,) * 4)
            for _ in range(40)
        ]
        high_benefit = [
            _score_record("high_benefit", first="high_benefit", returns=(-0.2,) * 4)
            for _ in range(30)
        ]
        uncertain = [
            _score_record("uncertain", first="uncertain", status="side_unavailable")
            for _ in range(5)
        ]
        cards = build_scorecards(high_cost + high_benefit + uncertain)
        rankings = build_rankings(cards)

        self.assertEqual(rankings["highest_impact"][0]["filter"], "high_cost")
        self.assertEqual(rankings["highest_cost"][0]["filter"], "high_cost")
        self.assertEqual(rankings["highest_benefit"][0]["filter"], "high_benefit")
        self.assertEqual(rankings["highest_uncertainty"][0]["filter"], "uncertain")

    def test_json_markdown_and_utf8_bom(self):
        report = build_report([])
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "scorecard.json"
            md_path = Path(tmp) / "scorecard.md"
            write_reports(report, json_path, md_path)
            json_bytes = json_path.read_bytes()
            md_bytes = md_path.read_bytes()

        self.assertTrue(json_bytes.startswith(b"\xef\xbb\xbf"))
        self.assertTrue(md_bytes.startswith(b"\xef\xbb\xbf"))
        payload = json.loads(json_bytes.decode("utf-8-sig"))
        markdown = md_bytes.decode("utf-8-sig")
        self.assertEqual(payload["analysis"], "offline_decision_contract_filter_scorecard")
        self.assertIn("# BIUMOLO Decision Contract Filter Scorecard", markdown)
        self.assertIn("## DCR-002 answer", markdown)

    def test_invalid_session_isolated_and_legacy_full_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _session(root, "legacy", [{"reason": "no_final_signal"}], [_snapshot(0)])
            _session(root, "full", [_decision()], [_snapshot(0)])
            bad = root / "bad"
            bad.mkdir()
            _write_jsonl(bad / "pipeline_decisions.jsonl", [_decision(), _decision()])
            _write_jsonl(bad / "signal_engine_full_path_snapshots.jsonl", [_snapshot(0)])
            report = build_report(discover_sessions(root))

        self.assertEqual(report["sessions_discovered"], 3)
        self.assertEqual(report["sessions_analyzed"], 2)
        self.assertEqual(report["sessions_invalid"], 1)
        self.assertEqual(report["coverage"]["pipeline_decisions_total"], 2)
        self.assertEqual(report["coverage"]["structured_decisions"], 1)
        self.assertEqual(report["coverage"]["legacy_or_unstructured_excluded"], 1)
        self.assertIn("record_count_mismatch", report["invalid_sessions"][0]["reason"])

    def test_non_increasing_timestamp_session_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = _session(
                Path(tmp),
                "bad_time",
                [_decision(), _decision()],
                [_snapshot(0, timestamp=2), _snapshot(1, timestamp=2)],
            )
            with self.assertRaisesRegex(SessionValidationError, "not_strictly_increasing"):
                analyze_session(session)


if __name__ == "__main__":
    unittest.main()

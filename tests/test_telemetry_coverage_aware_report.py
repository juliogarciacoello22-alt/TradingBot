import json
import tempfile
import unittest
from pathlib import Path

from tools.analyze_strategy_behavior import analyze_records, build_report, classify_telemetry


class TelemetryCoverageAwareReportTests(unittest.TestCase):
    def test_classify_telemetry(self):
        self.assertEqual(classify_telemetry([]), 'EMPTY')
        self.assertEqual(classify_telemetry([{'reason': 'legacy'}]), 'LEGACY')
        self.assertEqual(classify_telemetry([{'terminal_reason': 'ok'}]), 'FULL')
        self.assertEqual(
            classify_telemetry([{'terminal_reason': 'ok'}, {'reason': 'legacy'}]),
            'PARTIAL',
        )

    def test_analyze_records_reports_structured_decisions(self):
        analysis = analyze_records([
            {'terminal_reason': 'ok', 'terminal_stage': 'final_signal'},
            {'reason': 'legacy'},
        ])
        self.assertEqual(analysis['pipeline_decisions'], 2)
        self.assertEqual(analysis['structured_decisions'], 1)
        self.assertEqual(analysis['telemetry_class'], 'PARTIAL')

    def test_build_report_separates_raw_and_structured_funnels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / 'legacy'
            full = root / 'full'
            legacy.mkdir()
            full.mkdir()
            (legacy / 'pipeline_decisions.jsonl').write_text(
                ''.join(json.dumps({'reason': 'legacy'}) + '\n' for _ in range(9)),
                encoding='utf-8',
            )
            (full / 'pipeline_decisions.jsonl').write_text(
                json.dumps({
                    'build_signal_reason': 'scalper_generated',
                    'terminal_stage': 'final_signal',
                    'terminal_reason': 'ok',
                }) + '\n',
                encoding='utf-8',
            )
            report = build_report([legacy, full])

        self.assertEqual(report['aggregate']['pipeline_decisions'], 10)
        self.assertEqual(report['structured_aggregate']['pipeline_decisions'], 1)
        self.assertEqual(report['telemetry_coverage']['structured_decisions'], 1)
        self.assertEqual(report['telemetry_coverage']['coverage_percent'], 10.0)
        self.assertEqual(
            report['structured_aggregate']['funnel']['pipeline_to_build_signal_pct'],
            100.0,
        )
        self.assertIn(
            'structured_telemetry_coverage_below_80_percent',
            report['warnings'],
        )


if __name__ == '__main__':
    unittest.main()

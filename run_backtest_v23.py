import argparse
import json
from dataclasses import replace
from pathlib import Path

from backtesting.v23.data_loader import load_last_file
from backtesting.v23.recorder import write_results
from backtesting.v23.runner import BacktestRunnerV23
from core.strategy_v23.config import StrategyConfigV23


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic BiUmolo v2.3 backtester")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commission-round-trip", type=float, required=True)
    parser.add_argument("--exit-slippage-ticks", type=int, default=0)
    args = parser.parse_args()

    config = replace(
        StrategyConfigV23(),
        commission_round_trip=args.commission_round_trip,
        exit_slippage_ticks=args.exit_slippage_ticks,
    )
    dataset = load_last_file(
        args.dataset,
        timezone_name=config.timezone,
        tick_size=config.tick_size,
    )
    result = BacktestRunnerV23(config).run(dataset)
    write_results(
        args.output,
        manifest=result.manifest,
        signals=list(result.signals),
        rejections=list(result.rejections),
        trades=list(result.trades),
        summary=result.summary,
        daily=list(result.daily),
        curve=list(result.equity_curve),
    )
    print(json.dumps(result.summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()


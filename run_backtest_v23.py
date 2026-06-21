import argparse
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from backtesting.v23.data_loader import load_last_file
from backtesting.v23.recorder import write_results
from backtesting.v23.runner import BacktestRunnerV23, RunMetadata
from core.strategy_v23.config import StrategyConfigV23


def resolve_git_head(repository: Path) -> str:
    git_dir = repository / ".git"
    if git_dir.is_file():
        marker = git_dir.read_text(encoding="utf-8").strip()
        if not marker.startswith("gitdir: "):
            raise RuntimeError("Invalid .git file")
        git_dir = (repository / marker.removeprefix("gitdir: ")).resolve()
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head
    reference = head.removeprefix("ref: ")
    loose_ref = git_dir / reference
    if loose_ref.exists():
        return loose_ref.read_text(encoding="utf-8").strip()
    packed_refs = git_dir / "packed-refs"
    if packed_refs.exists():
        for line in packed_refs.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith(("#", "^")):
                commit_hash, name = line.split(" ", 1)
                if name == reference:
                    return commit_hash
    raise RuntimeError(f"Unable to resolve Git reference: {reference}")


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
    commit_hash = resolve_git_head(Path(__file__).resolve().parent)
    metadata = RunMetadata(commit_hash, datetime.now(timezone.utc))
    result = BacktestRunnerV23(config).run(dataset, metadata=metadata)
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

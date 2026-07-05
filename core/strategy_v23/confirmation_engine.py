from .models import Bar, Direction, Setup, SwingPoint


def microstructure_confirmation(
    swings: list[SwingPoint],
    side: Direction,
) -> bool:
    if len(swings) < 4:
        return False
    recent = swings[-4:]
    if any(recent[index].kind == recent[index - 1].kind for index in range(1, 4)):
        return False
    swing_highs = [point.price for point in recent if point.kind == "HIGH"]
    swing_lows = [point.price for point in recent if point.kind == "LOW"]
    if len(swing_highs) != 2 or len(swing_lows) != 2:
        return False
    if side == Direction.BUY:
        return swing_highs[-1] > swing_highs[-2] and swing_lows[-1] > swing_lows[-2]
    return swing_highs[-1] < swing_highs[-2] and swing_lows[-1] < swing_lows[-2]


def confirmations(
    *,
    bar: Bar,
    setup: Setup,
    swings: list[SwingPoint],
    volume20: float | None,
    atr14: float | None,
    atr_five_bars_ago: float | None,
) -> tuple[str, ...]:
    result: list[str] = []
    if microstructure_confirmation(swings, setup.side):
        result.append("microstructure")
    if volume20 is not None and bar.volume >= volume20:
        result.append("volume")
    if atr14 is not None and atr_five_bars_ago is not None and atr14 >= atr_five_bars_ago:
        result.append("atr_rising")
    if setup.level_kind in {"vwap", "vwap_plus1", "vwap_minus1"}:
        result.append("vwap_rejection")
    return tuple(result)

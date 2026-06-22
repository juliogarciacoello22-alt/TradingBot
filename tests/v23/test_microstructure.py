import unittest

from core.strategy_v23.confirmation_engine import microstructure_confirmation
from core.strategy_v23.models import Direction, SwingPoint

from .helpers import bar


def swing(index: int, kind: str, price: float) -> SwingPoint:
    return SwingPoint(index, bar(index).timestamp, kind, price)


class MicrostructureTests(unittest.TestCase):
    def test_buy_requires_chronological_higher_high_and_higher_low(self):
        structure = [
            swing(1, "LOW", 100.0),
            swing(2, "HIGH", 110.0),
            swing(3, "LOW", 105.0),
            swing(4, "HIGH", 115.0),
        ]
        self.assertTrue(microstructure_confirmation(structure, Direction.BUY))
        self.assertFalse(microstructure_confirmation(structure, Direction.SELL))

    def test_sell_requires_chronological_lower_high_and_lower_low(self):
        structure = [
            swing(1, "HIGH", 115.0),
            swing(2, "LOW", 105.0),
            swing(3, "HIGH", 110.0),
            swing(4, "LOW", 100.0),
        ]
        self.assertTrue(microstructure_confirmation(structure, Direction.SELL))

    def test_adjacent_same_kind_is_not_valid_structure(self):
        malformed = [
            swing(1, "LOW", 100.0),
            swing(2, "HIGH", 110.0),
            swing(3, "HIGH", 115.0),
            swing(4, "LOW", 105.0),
        ]
        self.assertFalse(microstructure_confirmation(malformed, Direction.BUY))


if __name__ == "__main__":
    unittest.main()

from decimal import Decimal

import pytest

from app.modules.boq.status import LineStatus, quantities, required_qty

D = Decimal


@pytest.mark.parametrize(
    ("qty", "build", "attrition", "unit", "dnp", "expected"),
    [
        (D(3), 25, D(0), "pcs", False, D(75)),
        (D(3), 25, D(2), "pcs", False, D(77)),  # 76.5 -> 77 (round up)
        (D(1), 10, D("0.5"), "pcs", False, D(11)),  # 10.05 -> 11
        (D(4), 50, D(2), "pcs", False, D(204)),  # exact
        (D("1.5"), 7, D(3), "m", False, D("10.82")),  # 10.815 -> 10.82 (non-countable: 0.01)
        (D(2), 10, D(2), "pcs", True, D(0)),  # DNP
        (D(0), 10, D(2), "pcs", False, D(0)),  # zero qty
        (D(2), 0, D(2), "pcs", False, D(0)),  # no build
    ],
)
def test_required_qty(
    qty: Decimal, build: int, attrition: Decimal, unit: str, dnp: bool, expected: Decimal
) -> None:
    assert required_qty(qty, build, attrition, unit=unit, dnp=dnp) == expected


@pytest.mark.parametrize(
    ("required", "ordered", "received", "issued", "status", "shortfall", "pending"),
    [
        (D(0), D(0), D(0), D(0), LineStatus.NOT_REQUIRED, D(0), D(0)),
        (D(0), D(5), D(5), D(0), LineStatus.NOT_REQUIRED, D(0), D(0)),
        (D(100), D(0), D(0), D(0), LineStatus.NOT_ORDERED, D(100), D(0)),
        (D(100), D(40), D(0), D(0), LineStatus.PARTIALLY_ORDERED, D(60), D(40)),
        (D(100), D(100), D(0), D(0), LineStatus.ORDERED, D(0), D(100)),
        (D(100), D(120), D(0), D(0), LineStatus.ORDERED, D(0), D(120)),  # over-ordered
        (D(100), D(100), D(30), D(0), LineStatus.PARTIALLY_RECEIVED, D(0), D(70)),
        (D(100), D(40), D(30), D(0), LineStatus.PARTIALLY_RECEIVED, D(60), D(10)),
        (D(100), D(100), D(100), D(0), LineStatus.RECEIVED, D(0), D(0)),
        (D(100), D(100), D(110), D(0), LineStatus.RECEIVED, D(0), D(0)),  # over-receipt
        (
            D(100),
            D(0),
            D(100),
            D(0),
            LineStatus.RECEIVED,
            D(100),
            D(0),
        ),  # stock-covered, nothing ordered
        (D(100), D(100), D(100), D(50), LineStatus.RECEIVED, D(0), D(0)),  # partly issued
        (D(100), D(100), D(100), D(100), LineStatus.ISSUED, D(0), D(0)),
    ],
)
def test_every_status_branch(
    required, ordered, received, issued, status, shortfall, pending
) -> None:
    q = quantities(required, ordered, received, issued)
    assert q.status == status
    assert q.shortfall == shortfall
    assert q.pending_receipt == pending


def test_fully_received_flag() -> None:
    assert quantities(D(10), D(10), D(10)).fully_received
    assert quantities(D(0)).fully_received
    assert not quantities(D(10), D(10), D(9)).fully_received

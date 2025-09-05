# payment/utils.py
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Tuple

def _to_cents(amount) -> int:
    d = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)

def collect_checkout_items(request) -> Tuple[List[Dict], int]:
    """
    Map session cart rows to payment line items.
    Each row stored with 'unit_cents' and qty=1 (single-car).
    """
    items: List[Dict] = []
    total = 0
    for r in request.session.get("cart", []):
        unit = int(r.get("unit_cents", 0) or 0)
        title = r.get("title", "Car")
        make = r.get("make", "")
        model = r.get("model_name", "")
        name = f"{title} — {make} {model}".strip().rstrip("—")
        items.append({
            "product_id": str(r.get("id", "")),
            "name": name,
            "unit_amount": unit,
            "quantity": 1,
        })
        total += unit
    return items, total

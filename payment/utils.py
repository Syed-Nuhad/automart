from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Tuple

def _to_cents(amount) -> int:
    d = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(d * 100)

# -------- OPTION A: session-based cart (DEFAULT) --------
def collect_checkout_items(request) -> Tuple[List[Dict], int]:
    """
    Session cart shape expected:
    request.session['cart'] = [
      {"id": 12, "name": "T-shirt", "price": 19.99, "qty": 2},
      ...
    ]
    """
    items: List[Dict] = []
    total = 0

    cart = request.session.get("cart", [])
    for row in cart:
        unit = _to_cents(row.get("price", 0))
        qty  = int(row.get("qty", 1) or 1)
        items.append({
            "product_id": str(row.get("id", "")),
            "name": row.get("name", "Item"),
            "unit_amount": unit,
            "quantity": qty,
        })
        total += unit * qty

    return items, total
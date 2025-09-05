from typing import List, Dict, Tuple




def collect_checkout_items(request) -> Tuple[List[Dict], int]:
    """
    RETURN:
      - items: list of dicts like [{'product_id': '123', 'name': 'T-shirt', 'unit_amount': 1999, 'quantity': 2}, ...]
      - total_cents: integer total in cents
    TODO (ADAPT): Replace the stub with your cart reading logic.
    """
    items = []
    total = 0

    # ---------- ADAPT THIS BLOCK ----------
    # EXAMPLE A) If you store a session cart:
    # session_cart = request.session.get("cart", [])
    # for row in session_cart:
    #     unit_cents = int(float(row["price"]) * 100)
    #     qty = int(row.get("qty", 1))
    #     items.append({
    #         "product_id": str(row.get("id", "")),
    #         "name": row.get("name", "Item"),
    #         "unit_amount": unit_cents,
    #         "quantity": qty,
    #     })
    #     total += unit_cents * qty

    # EXAMPLE B) If you have a CartItem model:
    # from shop.models import CartItem
    # qs = CartItem.objects.filter(user=request.user)
    # for ci in qs:
    #     unit_cents = int(ci.product.price * 100)
    #     items.append({
    #         "product_id": str(ci.product_id),
    #         "name": ci.product.title,
    #         "unit_amount": unit_cents,
    #         "quantity": ci.quantity,
    #     })
    #     total += unit_cents * ci.quantity
    # --------------------------------------

    # Fallback demo item (remove after you adapt):
    if not items:
        items = [{
            "product_id": "DEMO1",
            "name": "Demo Item",
            "unit_amount": 1999,
            "quantity": 1,
        }]
        total = 1999

    return items, total
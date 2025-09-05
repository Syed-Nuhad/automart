# payment/context_processors.py
def cart_meta(request):
    cart = list(request.session.get("cart", []))
    return {
        "cart_count": len(cart),
        "cart_total_cents": sum(int(r.get("unit_cents", 0) or 0) for r in cart),
        "cart_ids": [str(r.get("id")) for r in cart],
    }

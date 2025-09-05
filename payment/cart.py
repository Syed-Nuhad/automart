# payment/cart.py
from typing import Dict, List

from payment.utils import _to_cents

SESSION_KEY = "cart"

def _get_cart(request) -> List[Dict]:
    return list(request.session.get(SESSION_KEY, []))

def _save_cart(request, cart: List[Dict]) -> None:
    # normalize by id; single-quantity cart (only 1 per car)
    seen = {}
    for r in cart:
        key = str(r.get("id"))
        if not key:
            continue
        # keep the last version for the same id
        seen[key] = {
            "id": key,
            "title": r.get("title", "Car"),
            "make": r.get("make", ""),
            "model_name": r.get("model_name", ""),
            "unit_cents": int(r.get("unit_cents", 0) or 0),
            "cover_url": r.get("cover_url") or None,
        }
    request.session[SESSION_KEY] = list(seen.values())
    request.session.modified = True

def in_cart(request, pid: str) -> bool:
    pid = str(pid)
    return any(str(r.get("id")) == pid for r in _get_cart(request))

def add_item(request, *, pid: str, title: str, make: str, model_name: str, unit_cents: int, cover_url: str | None) -> bool:
    """
    Returns True if newly added, False if it was already in the cart.
    Single-quantity: if car exists, we don't add again.
    """
    pid = str(pid)
    cart = _get_cart(request)
    if any(str(r.get("id")) == pid for r in cart):
        return False  # already there
    cart.append({
        "id": pid,
        "title": title,
        "make": make,
        "model_name": model_name or "",
        "unit_cents": int(unit_cents or 0),
        "cover_url": cover_url or None,
    })
    _save_cart(request, cart)
    return True

def remove_item(request, *, pid: str) -> None:
    pid = str(pid)
    cart = [r for r in _get_cart(request) if str(r.get("id")) != pid]
    _save_cart(request, cart)

def clear(request) -> None:
    request.session[SESSION_KEY] = []
    request.session.modified = True

def count(request) -> int:
    return len(_get_cart(request))

def total_cents(request) -> int:
    return sum(int(r.get("unit_cents", 0) or 0) for r in _get_cart(request))
def _car_to_session_row(car: Car) -> dict:
    # convert Decimal price to cents (handles 200,000 correctly)
    unit_cents = _to_cents(car.price)
    cover_url = None
    if getattr(car, "cover", None):
        try:
            cover_url = car.cover.url
        except Exception:
            cover_url = None
    return {
        "pid": str(car.pk),
        "title": car.title,
        "make": str(car.make),
        "model_name": car.model_name or "",
        "unit_cents": unit_cents,
        "cover_url": cover_url,
    }
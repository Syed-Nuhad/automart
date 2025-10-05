from marketplace.models import SellerProfile, SavedSearch, Cart


def seller_flags(request):
    is_seller = False
    is_seller_pending = False
    if request.user.is_authenticated:
        try:
            sp = request.user.seller_profile
            is_seller = sp.is_verified
            is_seller_pending = (sp.verification_status in ("DRAFT", "PENDING"))
        except SellerProfile.DoesNotExist:
            pass
    return {"is_seller": is_seller, "is_seller_pending": is_seller_pending}


def saved_search_badge(request):
    if not request.user.is_authenticated:
        return {}
    has_new = False
    for s in SavedSearch.objects.filter(user=request.user, is_active=True):
        if s.new_matches_qs().exists():
            has_new = True
            break
    return {"has_new_saved_searches": has_new}



def nav_counts(request):
    # safe default if sessions not ready (e.g., during some system checks)
    try:
        cart = Cart.for_request(request)
        count = cart.total_quantity
    except Exception:
        count = 0
    return {"cart_count": count}



# models/context_processors.py
from typing import List

COMPARE_SESSION_KEY = "compare_ids"
MAX_COMPARE = 4

def compare_context(request):
    ids = request.session.get(COMPARE_SESSION_KEY, [])
    if not isinstance(ids, list):
        ids = []
    try:
        ids = [int(x) for x in ids]
    except Exception:
        ids = []
    return {
        "compare_ids": ids,              # list of car IDs in compare
        "compare_count": len(ids),       # count badge for navbar
        "compare_max": MAX_COMPARE,
    }
# marketplace/context_processors.py
from .compare_session import get_ids, MAX_COMPARE

def compare_meta(request):
    ids = get_ids(request)
    return {
        "compare_ids": ids,
        "compare_count": len(ids),
        "compare_max": MAX_COMPARE,
    }

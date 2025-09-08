# automart/marketplace/view_saved_searches.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.db import transaction

from marketplace.models import SavedSearch

# These are the exact keys visible in your repo/templates/filters
ALLOWED_KEYS = [
    "make", "model_name", "body_type", "transmission", "fuel",
    "price_min", "price_max", "mileage_max",
    "is_featured", "is_new", "is_certified", "is_hot",
]

def _extract_filters(qd):
    """Pick out only the allowed filter keys, trimming blanks."""
    out = {}
    for k in ALLOWED_KEYS:
        v = (qd.get(k) or "").strip()
        if v != "":
            out[k] = v
    return out


@login_required
@transaction.atomic
def saved_search_create(request):
    """
    Create (or reuse) a saved search from current filters.
    Accepts POST (hidden form) or GET (?make=Toyota&...).
    """
    qd = request.POST if request.method == "POST" else request.GET
    params = _extract_filters(qd)
    if not params:
        messages.warning(request, "No filters to save.")
        return redirect(reverse("marketplace:saved_search_list"))

    # Name and frequency
    name = (qd.get("name") or qd.get("q") or "My search").strip()[:120]
    freq = (qd.get("frequency") or "DAILY").upper()
    if freq not in ("DAILY", "WEEKLY"):
        freq = "DAILY"

    # Deduplicate via params_hash (your model supports this)
    try:
        params_hash = SavedSearch.hash_for(params)
    except AttributeError:
        import hashlib, json
        params_hash = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()

    existing = SavedSearch.objects.filter(user=request.user, params_hash=params_hash).first()
    if existing:
        messages.info(request, "You already saved this search.")
        return redirect(reverse("marketplace:saved_search_list"))

    # Create and persist
    ss = SavedSearch(user=request.user, name=name, frequency=freq, is_active=True)
    if hasattr(ss, "set_params"):
        ss.set_params(params)      # your helper: sets params + params_hash
    else:
        ss.params = params
        ss.params_hash = params_hash
    ss.save()

    # Baseline watermark so “new” means after this save moment
    ss.last_seen_car_created_at = timezone.now()
    ss.save(update_fields=["last_seen_car_created_at"])

    messages.success(request, "Search saved.")
    return redirect(reverse("marketplace:saved_search_list"))


@login_required
def saved_search_list(request):
    """List saved searches with a count of NEW matches since the watermark."""
    searches = SavedSearch.objects.filter(user=request.user).order_by("-created_at")
    items = [{"s": s, "new_count": s.new_matches_qs().count()} for s in searches]
    return render(request, "saved_searches/list.html", {"items": items})


@login_required
def saved_search_new(request, pk):
    """
    Show up to 50 NEW matches for the chosen saved search (since watermark).
    Uses your existing file name new_html.html (don’t rename your template).
    """
    s = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    cars = list(s.new_matches_qs().order_by("-created")[:50])
    return render(request, "saved_searches/new_html.html", {"search": s, "cars": cars})


@login_required
def saved_search_mark_read(request, pk):
    """Move the watermark to the newest listing so count resets to zero."""
    if request.method != "POST":
        return redirect(reverse("marketplace:saved_search_list"))
    s = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    newest = s.queryset().order_by("-created").first()
    s.last_seen_car_created_at = (newest.created if newest else timezone.now())
    s.save(update_fields=["last_seen_car_created_at"])
    messages.success(request, "Marked as read.")
    return redirect(reverse("marketplace:saved_search_list"))


@login_required
def saved_search_delete(request, pk):
    """Delete a saved search."""
    if request.method != "POST":
        return redirect(reverse("marketplace:saved_search_list"))
    s = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    s.delete()
    messages.info(request, "Saved search deleted.")
    return redirect(reverse("marketplace:saved_search_list"))
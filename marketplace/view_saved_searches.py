from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from marketplace.models import SavedSearch


def _extract_filters(qd):
    fields = [
        "make","model_name","body_type","transmission","fuel",
        "price_min","price_max","mileage_max","is_featured","is_new","is_certified","is_hot",
    ]
    out = {}
    for k in fields:
        v = qd.get(k)
        if v not in (None, ""):
            out[k] = v
    return out

@login_required
def saved_search_create(request):
    if request.method != "POST":
        return redirect(request.META.get("HTTP_REFERER", "/"))

    params = _extract_filters(request.POST)
    if not params:
        messages.warning(request, "No filters to save.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    ss = SavedSearch(user=request.user)
    ss.set_params(params)
    existing = SavedSearch.objects.filter(user=request.user, params_hash=ss.params_hash).first()
    if existing:
        messages.info(request, "This search is already saved.")
        return redirect("saved_search_list")

    ss.name = (request.POST.get("name") or "My search").strip()
    ss.save()
    messages.success(request, "Search saved.")
    return redirect("saved_search_list")

@login_required
def saved_search_list(request):
    items = []
    for s in SavedSearch.objects.filter(user=request.user).order_by("-created_at"):
        new_count = s.new_matches_qs().count()
        items.append({"s": s, "new_count": new_count})
    return render(request, "saved_searches/list.html", {"items": items})

@login_required
def saved_search_new(request, pk):
    s = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    cars = s.new_matches_qs().order_by("-created")[:50]
    return render(request, "saved_searches/new.html", {"search": s, "cars": cars})

@login_required
def saved_search_mark_read(request, pk):
    s = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    newest = s.newest_car_created()
    s.last_seen_car_created_at = newest or timezone.now()
    s.save(update_fields=["last_seen_car_created_at"])
    messages.success(request, "Marked as read.")
    return redirect("saved_search_list")

@login_required
def saved_search_delete(request, pk):
    s = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    if request.method == "POST":
        s.delete()
        messages.success(request, "Saved search removed.")
    return redirect("saved_search_list")



@login_required
def saved_search_list(request):
    items = SavedSearch.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "saved_searches/list.html", {"items": items})


@login_required
def saved_search_toggle(request, pk):
    ss = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    ss.is_active = not ss.is_active
    ss.save(update_fields=["is_active"])
    messages.success(request, f"Alerts {'enabled' if ss.is_active else 'paused'}.")
    return redirect(reverse("saved_search_list"))
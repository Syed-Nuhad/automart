# views.py (full corrected)

from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import send_mail, EmailMessage
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db.models import Count, Q, Exists, OuterRef
from django.http import (
    JsonResponse, Http404, HttpResponseBadRequest, HttpResponseRedirect
)
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from marketplace.models import SellerProfile
from . import models as m
from .forms import SignUpForm, TestDriveForm
from .models import Car


@ensure_csrf_cookie
def index(request):
    # ---------- Featured block ----------
    featured_qs = (
        m.Car.objects.filter(is_featured=True)
        .select_related("make", "body_type")
        .prefetch_related("images")
    )
    if not featured_qs.exists():
        featured_qs = (
            m.Car.objects.filter(is_hot=True)
            .select_related("make", "body_type")
            .prefetch_related("images")
        )
    featured_cars = featured_qs[:8]

    hero_slides = m.HeroSlide.objects.filter(is_active=True)

    # ---------- Base queryset ----------
    cars_qs = (
        m.Car.objects.all()
        .select_related("make", "body_type")
        .prefetch_related("images")
    )

    # ---------- Filters (hero + sidebar) ----------
    make_slug = request.GET.get("make")
    if make_slug:
        cars_qs = cars_qs.filter(make__slug=make_slug)

    model = request.GET.get("model")
    if model:
        cars_qs = cars_qs.filter(model_name__icontains=model)

    location = request.GET.get("location")
    if location:
        cars_qs = cars_qs.filter(seller_meta__icontains=location)

    max_price = request.GET.get("max_price")
    if max_price:
        try:
            cars_qs = cars_qs.filter(price__lte=float(max_price))
        except ValueError:
            pass

    min_price = request.GET.get("min_price")
    if min_price:
        try:
            cars_qs = cars_qs.filter(price__gte=float(min_price))
        except ValueError:
            pass

    body_slugs = request.GET.getlist("body_types")
    if body_slugs:
        cars_qs = cars_qs.filter(body_type__slug__in=body_slugs)

    fuel = request.GET.get("fuel")
    if fuel:
        cars_qs = cars_qs.filter(fuel=fuel)

    transmission = request.GET.get("transmission")
    if transmission:
        cars_qs = cars_qs.filter(transmission=transmission)

    if request.GET.get("featured") == "1":
        cars_qs = cars_qs.filter(is_featured=True)

    # ---------- Sorting ----------
    sort = request.GET.get("sort")
    if sort in {"-created", "price", "-price", "mileage"}:
        cars_qs = cars_qs.order_by(sort)

    # ---------- Pagination ----------
    paginator = Paginator(cars_qs, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Build querystring for pagination (keep filters, drop page)
    qs = request.GET.copy()
    qs.pop("page", None)
    querystring = qs.urlencode()

    # ---------- Active car & seller image ----------
    active_car = featured_cars.first() or (page_obj.object_list[0] if page_obj.object_list else None)
    seller_image = active_car.seller_image if (active_car and active_car.seller_image) else None

    if request.user.is_authenticated:
        try:
            userprofile = SellerProfile.objects.get(user=request.user)
        except SellerProfile.DoesNotExist:
            userprofile = None
    else:
        userprofile = None

    context = {
        "hero_slides": hero_slides,
        "featured_cars": featured_cars,
        "cars": page_obj.object_list,
        "is_paginated": page_obj.has_other_pages(),
        "paginator": paginator,
        "page_obj": page_obj,
        "querystring": querystring,
        "sort": sort,
        "makes": m.Make.objects.all(),
        "userprofile": userprofile,
        "body_types": m.BodyType.objects.all(),
        # Choice tuples: (code, label) → template shows translated label but submits code
        "fuel_choices": [
            ("Petrol", _("Petrol")),
            ("Diesel", _("Diesel")),
            ("Hybrid", _("Hybrid")),
            ("Electric", _("Electric")),
        ],
        "transmission_choices": [
            ("Automatic", _("Automatic")),
            ("Manual", _("Manual")),
            ("CVT", _("CVT")),
        ],
        "active_car": active_car,
        "seller_image": seller_image,
        "q": {
            "make": make_slug or "",
            "model": model or "",
            "location": location or "",
            "min_price": min_price or "",
            "max_price": request.GET.get("max_price") or "",
            "body_types": body_slugs,
            "fuel": fuel or "",
            "transmission": transmission or "",
            "featured": request.GET.get("featured", ""),
        },
        "quick_chips": [
            {"title": _("New arrivals")},
            {"title": _("Certified")},
            {"title": _("Under $20k")},
            {"title": _("SUV")},
            {"title": _("Electric")},
        ],
    }
    return render(request, "index.html", context)


# ---- wishlist page ----
def wishlist_page(request):
    ids = _session_ids(request, "wishlist_ids")
    cars = list(m.Car.objects.filter(pk__in=ids))
    # keep original session order
    cars.sort(key=lambda c: ids.index(c.pk))
    return render(request, "wishlist.html", {"cars": cars})


# ---- nav badge counters ----
def nav_counters(request):
    wishlist_ids = _session_ids(request, "wishlist_ids")
    compare_ids = _session_ids(request, "compare_ids")
    return JsonResponse({"ok": True, "wishlist": len(wishlist_ids), "compare": len(compare_ids)})


# ---- toggle_wishlist ----
@require_http_methods(["GET", "POST"])
def toggle_wishlist(request, pk):
    get_object_or_404(m.Car, pk=pk)

    ids = _session_ids(request, "wishlist_ids")
    if pk in ids:
        ids.remove(pk)
        in_wishlist = False
    else:
        ids.append(pk)
        in_wishlist = True

    request.session["wishlist_ids"] = ids

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "in_wishlist": in_wishlist, "count": len(ids)})

    # no-JS fallback: back
    return HttpResponseRedirect(request.META.get("HTTP_REFERER", "/wishlist/"))


def _compare_items(ids):
    qs = m.Car.objects.filter(pk__in=ids).select_related("make", "body_type")
    order = {pid: i for i, pid in enumerate(ids)}
    cars = sorted(qs, key=lambda c: order.get(c.pk, 10**9))
    return [
        {
            "id": c.pk,
            "title": c.title,
            "price": float(c.price) if c.price is not None else None,
            "mileage": c.mileage,
            "fuel": c.get_fuel_display() if c.fuel else "",
            "transmission": c.get_transmission_display() if c.transmission else "",
            "body": c.body_type.name if c.body_type else None,
            "cover": c.cover.url if c.cover else None,
        }
        for c in cars
    ]


@require_http_methods(["GET", "POST"])
def toggle_compare(request, pk: int):
    get_object_or_404(m.Car, pk=pk)

    ids = request.session.get("compare_ids", [])
    in_compare = False

    if pk in ids:
        ids.remove(pk)
        in_compare = False
    else:
        if len(ids) >= 4:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"ok": False, "error": "max_4"}, status=400)
            return redirect(reverse("compare_page"))
        ids.append(pk)
        in_compare = True

    request.session["compare_ids"] = ids
    payload = {"ok": True, "in_compare": in_compare, "count": len(ids), "items": _compare_items(ids)}

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(payload)

    next_url = (
        request.GET.get("next")
        or request.POST.get("next")
        or request.META.get("HTTP_REFERER")
        or reverse("compare_page")
    )
    return redirect(next_url)


def car_json(request, pk: int):
    try:
        car = (
            m.Car.objects.select_related("make", "body_type")
            .prefetch_related("images")
            .get(pk=pk)
        )
    except m.Car.DoesNotExist:
        raise Http404(_("Car not found"))

    data = {
        "id": car.id,
        "title": car.title,
        "make": car.make.name if car.make_id else "",
        "model_name": car.model_name or "",
        "body_type": car.body_type.name if car.body_type_id else "",
        "price": float(car.price) if car.price is not None else None,
        "mileage": car.mileage,
        "transmission": car.get_transmission_display() if car.transmission else "",
        "fuel": car.get_fuel_display() if car.fuel else "",
        "overview": car.overview or "",
        "history": car.history or "",
        "seller_name": car.seller_name or "",
        "seller_meta": car.seller_meta or "",
        "cover": car.cover.url if car.cover else "",
        "images": [img.image.url for img in car.images.all()],
        "is_new": car.is_new,
        "is_certified": car.is_certified,
        "is_hot": car.is_hot,
        "is_featured": getattr(car, "is_featured", False),
    }
    return JsonResponse(data)


# ---------- finance helpers ----------
def _to_decimal(val, default=None):
    try:
        if val in ("", None):
            return default
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _monthly_payment(price, down, apr_pct, months):
    """
    monthly = P * r / (1 - (1+r)^-n), r = apr/12
    """
    price = _to_decimal(price, Decimal("0"))
    down = _to_decimal(down, Decimal("0"))
    months = int(months or 60)
    if months <= 0:
        months = 60

    principal = price - down
    if principal < 0:
        principal = Decimal("0")

    r = _to_decimal(apr_pct, Decimal("0")) / Decimal("1200")  # APR% -> monthly rate
    if r == 0:
        m = (principal / months) if months > 0 else Decimal("0")
    else:
        m = principal * r / (1 - (1 + r) ** Decimal(-months))
    return principal, m


def finance_offers(request):
    # params: ?max_price=&down=&apr=&term=
    max_price = _to_decimal(request.GET.get("max_price"), None)
    down = _to_decimal(request.GET.get("down"), Decimal("0"))
    apr = _to_decimal(request.GET.get("apr"), Decimal("0"))
    try:
        term = int(request.GET.get("term") or 60)
    except (TypeError, ValueError):
        term = 60

    qs = m.Car.objects.all().select_related("make", "body_type").prefetch_related("images")
    if max_price is not None:
        qs = qs.filter(price__isnull=False, price__lte=max_price)

    offers = []
    for car in qs:
        principal, monthly = _monthly_payment(car.price or 0, down, apr, term)
        offers.append({"car": car, "principal": principal, "monthly": monthly})

    # lowest monthly first
    offers.sort(key=lambda x: (x["monthly"] if x["monthly"] is not None else Decimal("0")))

    context = {
        "offers": offers,
        "params": {"max_price": max_price, "down": down, "apr": apr, "term": term},
        "makes": m.Make.objects.all(),
        "body_types": m.BodyType.objects.all(),
        "fuel_choices": m.Car.FUEL_CHOICES,
        "transmission_choices": m.Car.TRANSMISSION_CHOICES,
    }
    return render(request, "finance_offers.html", context)


def _cmp_session(request):
    return request.session.setdefault("compare_ids", [])


def _cmp_payload(ids):
    cars = list(m.Car.objects.filter(id__in=ids).select_related("make", "body_type"))
    idx = {cid: i for i, cid in enumerate(ids)}
    cars.sort(key=lambda c: idx.get(c.id, 1e9))
    items = []
    for c in cars:
        items.append(
            {
                "id": c.id,
                "title": c.title,
                "price": float(c.price) if c.price is not None else None,
                "mileage": c.mileage,
                "fuel": c.get_fuel_display() if c.fuel else "",
                "transmission": c.get_transmission_display() if c.transmission else "",
                "body": c.body_type.name if c.body_type else "",
                "cover": c.cover.url if c.cover else "",
            }
        )
    return items


def _extract_phone_from_text(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"(\+?\d[\d\s().-]{6,}\d)", str(text))
    raw = m.group(1) if m else str(text)
    digits = re.sub(r"\D+", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def car_detail(request, pk: int):
    car = get_object_or_404(m.Car, pk=pk)

    # ----- finance inputs
    dp_default, apr_default, term_default = 3000, 6, 60

    def to_number(val, default):
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(default)

    down = to_number(request.GET.get("down"), dp_default)
    apr = to_number(request.GET.get("apr"), apr_default)
    term = int(to_number(request.GET.get("term"), term_default))

    base_price = float(car.price or 0)
    principal = max(0.0, base_price - max(0.0, down))
    r = (apr / 100.0) / 12.0
    if r == 0:
        monthly = principal / max(1, term)
    else:
        f = pow(1 + r, term)
        monthly = principal * (r * f) / (f - 1)
    calc_input = {"down": int(down), "apr": apr, "term": term}
    calc_monthly = round(monthly, 0)

    # ----- reviews
    agg = m.CarReview.aggregate_for_car(pk)
    rating_avg = agg["rating_avg"]
    rating_count = agg["rating_count"]
    rating_dist = agg["rating_dist"]
    top_positive = agg["top_positive"]
    top_critical = agg["top_critical"]
    rating_full_stars = int(rating_avg // 1)

    qs = (
        m.CarReview.objects.filter(car_id=pk, status=True)
        .select_related("user")
        .annotate(
            helpful_count=Count(
                "feedback", filter=Q(feedback__action=m.ReviewFeedback.ACTION_HELPFUL)
            ),
            report_count=Count(
                "feedback", filter=Q(feedback__action=m.ReviewFeedback.ACTION_REPORT)
            ),
        )
    )
    if request.user.is_authenticated:
        qs = qs.annotate(
            i_liked=Exists(
                m.ReviewFeedback.objects.filter(
                    review_id=OuterRef("pk"),
                    user_id=request.user.id,
                    action=m.ReviewFeedback.ACTION_HELPFUL,
                )
            ),
            i_reported=Exists(
                m.ReviewFeedback.objects.filter(
                    review_id=OuterRef("pk"),
                    user_id=request.user.id,
                    action=m.ReviewFeedback.ACTION_REPORT,
                )
            ),
        )
    reviews = qs.order_by("-created_at")

    existing_review = None
    if request.user.is_authenticated:
        existing_review = m.CarReview.objects.filter(
            car_id=pk, user_id=request.user.id
        ).first()

    # ----- phone cleaned once
    raw_phone = (getattr(car, "seller_phone", None) or car.seller_meta or "").strip()
    phone_digits = re.sub(r"\D+", "", raw_phone)
    seller_has_phone = len(phone_digits) > 6
    whatsapp_text = _("Hi! I am interested in %(title)s") % {
        "title": car.title or _("this car")
    }

    # ===== Seller avatar for template
    User = get_user_model()
    userprofile = None

    # Try: find seller by email and use their SellerProfile.avatar
    if car.seller_email:
        seller_user = User.objects.filter(email__iexact=car.seller_email).first()
        sp = getattr(seller_user, "seller_profile", None) if seller_user else None
        if sp and getattr(sp, "avatar", None):
            userprofile = SimpleNamespace(profile_picture=sp.avatar)

    # Fallback: use car.seller_image
    if userprofile is None and getattr(car, "seller_image", None):
        userprofile = SimpleNamespace(profile_picture=car.seller_image)

    seller_verified = bool(getattr(car, "is_certified", False))

    return render(
        request,
        "car_detail.html",
        {
            "seller_verified": seller_verified,
            "car": car,
            "reviews": reviews,
            "top_positive": top_positive,
            "top_critical": top_critical,
            "rating_avg": rating_avg,
            "rating_count": rating_count,
            "rating_full_stars": rating_full_stars,
            "rating_dist": rating_dist,
            "existing_review": existing_review,
            "calc_input": calc_input,
            "calc_monthly": calc_monthly,
            # avatar + contact
            "userprofile": userprofile,
            "seller_phone_digits": phone_digits,
            "seller_has_phone": seller_has_phone,
            "whatsapp_text": whatsapp_text,

            "seller_point": car.seller_point(),  # None or dict {lat,lng,name,address,phone}
            "default_center": [37.0902, -95.7129, 4],
        },
    )
def car_geo(request, pk: int):
    car = get_object_or_404(Car, pk=pk)
    if car.seller_lat is None or car.seller_lng is None:
        return JsonResponse({"ok": False, "error": "no_coords"}, status=404)

    return JsonResponse({
        "ok": True,
        "id": car.id,
        "name": car.seller_name or car.title,
        "address": car.seller_address or car.seller_meta or "",
        "phone": car.seller_phone or "",
        "lat": float(car.seller_lat),
        "lng": float(car.seller_lng),
        "url": reverse("car_detail", args=[car.id]),
    })

@login_required
def submit_review(request, pk=None, car_id=None):
    car_pk = pk or car_id
    if car_pk is None:
        return HttpResponseBadRequest(_("Missing car id"))

    ref = request.META.get("HTTP_REFERER", "/")
    if request.method != "POST":
        return redirect(ref)

    car = get_object_or_404(m.Car, id=car_pk)
    ref = request.META.get("HTTP_REFERER") or car.get_absolute_url()

    try:
        review = m.CarReview.objects.get(user=request.user, car=car)
        # update existing
        review.subject = request.POST.get("subject", "")
        review.review = request.POST.get("review", "")
        review.rating = float(request.POST.get("rating") or 0)
        review.save()
        messages.success(request, _("Thank you! Your review has been updated."))
    except m.CarReview.DoesNotExist:
        m.CarReview.objects.create(
            car=car,
            user=request.user,
            subject=request.POST.get("subject", ""),
            review=request.POST.get("review", ""),
            rating=float(request.POST.get("rating") or 0),
            ip=request.META.get("REMOTE_ADDR", ""),
        )
        messages.success(request, _("Thank you! Your review has been submitted."))
    return redirect(ref)


@require_POST
def share_car(request, pk: int):
    car = get_object_or_404(m.Car, pk=pk)

    to_email = (request.POST.get("to") or "").strip()
    note = (request.POST.get("note") or "").strip()

    if not to_email:
        messages.error(request, _("Please enter a recipient email."))
        return redirect("car_detail", pk=pk)
    try:
        validate_email(to_email)
    except ValidationError:
        messages.error(request, _("That doesn't look like a valid email address."))
        return redirect("car_detail", pk=pk)

    share_url = request.build_absolute_uri(reverse("car_detail", args=[pk]))
    subject = _("Check this car: %(title)s") % {"title": car.title}
    sender = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@automart.local")
    who = getattr(request.user, "username", "") or _("Someone")

    body_lines = [
        _("%(who)s wanted to share this car with you:") % {"who": who},
        "",
        f"{car.title}",
        share_url,
    ]
    if note:
        body_lines.extend(["", _("Message:"), note])
    body = "\n".join(body_lines)

    send_mail(subject, body, sender, [to_email], fail_silently=False)

    messages.success(request, _("Shared by email."))
    return redirect("car_detail", pk=pk)


# ---- helpers ----
def _session_ids(request, key: str):
    raw = request.session.get(key, [])
    out = []
    for x in raw:
        try:
            ix = int(x)
        except (TypeError, ValueError):
            continue
        if ix not in out:
            out.append(ix)
    return out


def compare_page(request):
    ids = _session_ids(request, "compare_ids")
    cars = m.Car.objects.filter(pk__in=ids)
    cars = sorted(cars, key=lambda c: ids.index(c.pk))
    return render(request, "compare_page.html", {"cars": cars})


@require_POST
def clear_wishlist(request):
    # fix: use unified key
    request.session["wishlist_ids"] = []
    return redirect(reverse("wishlist_page"))


@login_required(login_url="login")
@require_http_methods(["GET", "POST"])
def test_drive(request, pk):
    car = get_object_or_404(m.Car, pk=pk)

    if request.method == "POST":
        form = TestDriveForm(request.POST)
        if form.is_valid():
            td = form.save(commit=False)
            td.car = car
            td.save()

            # Pick recipient: car.seller_email → TESTDRIVE_DEBUG_EMAIL → SALES_TEAM_EMAIL
            to_addr = (
                (car.seller_email or "").strip()
                or getattr(settings, "TESTDRIVE_DEBUG_EMAIL", None)
                or getattr(settings, "SALES_TEAM_EMAIL", None)
            )

            if to_addr:
                subject = _("New Test Drive Request — %(title)s") % {"title": car.title}
                body = (
                    f"{_('Car')}: {car.title}\n"
                    f"{_('Name')}: {td.full_name}\n"
                    f"{_('Email')}: {td.email}\n"
                    f"{_('Phone')}: {td.phone or '—'}\n"
                    f"{_('When')}: {td.preferred_date} {td.preferred_time or ''}\n"
                    f"{_('Notes')}:\n{td.message or '—'}\n"
                )

                email = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[to_addr],
                    reply_to=[td.email] if td.email else None,
                )
                email.send(fail_silently=False)
    else:
        form = TestDriveForm()

    return render(request, "test_drive.html", {"car": car, "form": form})


def signup(request):
    next_url = request.GET.get("next") or request.POST.get("next") or reverse("home")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Auto-login
            raw_password = form.cleaned_data.get("password1")
            user = authenticate(request, username=user.username, password=raw_password)
            if user:
                login(request, user)
            return redirect(next_url)
    else:
        form = SignUpForm()
    return render(request, "auth/signup.html", {"form": form, "next": next_url})


@require_GET
def reviews_json(request, pk: int):
    car = get_object_or_404(m.Car, pk=pk)

    agg = m.CarReview.aggregate_for_car(pk)
    items = [
        {
            "user": r.user.get_username(),
            "rating": r.rating,
            "subject": r.subject,
            "review": r.review,
            "created": r.created_at.isoformat(timespec="seconds"),
        }
        for r in car.reviews.filter(status=True).select_related("user")[:50]
    ]
    return JsonResponse({"ok": True, "aggregate": agg, "items": items})


@login_required
@require_http_methods(["POST"])
def add_review(request, pk: int):
    car = get_object_or_404(m.Car, pk=pk)

    # rating can be float (e.g. 4.5)
    try:
        rating = float(request.POST.get("rating", 0))
        if rating <= 0 or rating > 5:
            raise ValueError
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid rating"}, status=400)

    subject = (request.POST.get("subject") or "").strip()[:120]
    review_text = (request.POST.get("review") or "").strip()

    obj, created = m.CarReview.objects.update_or_create(
        car=car,
        user=request.user,
        defaults={"rating": rating, "subject": subject, "review": review_text},
    )
    agg = m.CarReview.aggregate_for_car(pk)
    return JsonResponse({"ok": True, "created": created, "aggregate": agg})


@login_required
@require_http_methods(["POST"])
def add_review_form(request, pk: int):
    car = get_object_or_404(m.Car, pk=pk)

    rating_str = (request.POST.get("rating") or "").strip()
    try:
        rating = float(rating_str)
        if rating <= 0 or rating > 5:
            raise ValueError
    except Exception:
        return redirect(f"/car/{pk}/#reviews")

    subject = (request.POST.get("subject") or "").strip()[:120]
    review_text = (request.POST.get("review") or "").strip()

    m.CarReview.objects.update_or_create(
        car=car,
        user=request.user,
        defaults={"rating": rating, "subject": subject, "review": review_text},
    )
    return redirect(f"/car/{pk}/#reviews")


@login_required
@require_POST
def review_mark_helpful(request, rid: int):
    review = get_object_or_404(m.CarReview, pk=rid, status=True)
    fb, created = m.ReviewFeedback.objects.get_or_create(
        review=review, user=request.user, action=m.ReviewFeedback.ACTION_HELPFUL
    )
    if created:
        # Optional: remove a previous report so a user can't both like & report
        m.ReviewFeedback.objects.filter(
            review=review, user=request.user, action=m.ReviewFeedback.ACTION_REPORT
        ).delete()
        messages.success(request, _("Marked helpful."))
    else:
        fb.delete()
        messages.info(request, _("Removed your like."))

    return redirect(
        request.META.get("HTTP_REFERER", reverse("car_detail", args=[review.car_id]))
        + "#reviews"
    )


@login_required
@require_POST
def review_report(request, rid: int):
    review = get_object_or_404(m.CarReview, pk=rid, status=True)
    fb, created = m.ReviewFeedback.objects.get_or_create(
        review=review, user=request.user, action=m.ReviewFeedback.ACTION_REPORT
    )
    if created:
        # Optional symmetry: remove a previous like
        m.ReviewFeedback.objects.filter(
            review=review, user=request.user, action=m.ReviewFeedback.ACTION_HELPFUL
        ).delete()
        messages.warning(request, _("Reported."))
    else:
        fb.delete()
        messages.info(request, _("Removed your report."))

    return redirect(
        request.META.get("HTTP_REFERER", reverse("car_detail", args=[review.car_id]))
        + "#reviews"
    )

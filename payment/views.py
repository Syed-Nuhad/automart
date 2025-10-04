# payment/views.py  — PayPal only (redirect flow), with tax/fee breakdown and cart clearing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.timezone import localtime

import json
import uuid
import hashlib
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponse,
    HttpResponseBadRequest, HttpResponseNotAllowed, JsonResponse, HttpResponseForbidden,
)
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Order, OrderItem
from .utils import collect_checkout_items

# ----------------------------- Config -----------------------------

# Sandbox by default; set PAYPAL_API_BASE="https://api-m.paypal.com" for live
PAYPAL_API_BASE = getattr(settings, "PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")

# Optional totals
TAX_RATE = Decimal(str(getattr(settings, "CHECKOUT_TAX_RATE", "0")))  # e.g. "0.08" => 8%
FEE_CENTS = int(getattr(settings, "CHECKOUT_FEE_CENTS", 0))           # e.g. 299

# Your charge currency
CURRENCY = (getattr(settings, "PAYMENT_CURRENCY", "usd") or "usd").lower()


# ----------------------------- Helpers -----------------------------

def _paypal_access_token() -> str:
    r = requests.post(
        f"{PAYPAL_API_BASE}/v1/oauth2/token",
        data={"grant_type": "client_credentials"},
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _fallback_items_from_marketplace(request):
    """
    Build (items, total_cents) from the marketplace Cart in the DB using session_key.
    Safe against differing field names; it tries multiple attributes.
    """
    try:
        if not request.session.session_key:
            request.session.save()

        from marketplace.models import Cart as MarketplaceCart  # local import to avoid cycles
        cart_obj = MarketplaceCart.objects.filter(session_key=request.session.session_key).first()
        if not cart_obj:
            return [], 0

        # Prefer related manager; fallback if your model names differ.
        try:
            cart_items = cart_obj.cartitem_set.select_related('car')
        except Exception:
            cart_items = getattr(cart_obj, 'items', lambda: [])()

        items, total = [], 0
        for ci in cart_items:
            car = getattr(ci, 'car', None)

            name = (
                getattr(car, 'title', None)
                or getattr(ci, 'title', None)
                or f"Item {getattr(ci, 'car_id', '') or getattr(car, 'id', '')}"
            )

            # Derive a cents price from the most likely fields, in order.
            unit_cents = (
                int(getattr(ci, 'unit_price_cents', 0) or 0)
                or int(getattr(ci, 'unit_amount', 0) or 0)
                or int(getattr(ci, 'unit_cents', 0) or 0)
                or int(getattr(car, 'price_cents', 0) or 0)
                or int(Decimal(str(getattr(car, 'price', 0) or 0)) * 100)
            )

            qty = int(getattr(ci, 'qty', None) or getattr(ci, 'quantity', None) or 1)

            product_id = (
                getattr(ci, 'car_id', '') or getattr(ci, 'product_id', '') or getattr(car, 'id', '') or ''
            )

            items.append({
                "name": name,
                "unit_amount": unit_cents,
                "quantity": qty,
                "product_id": product_id,
            })
            total += unit_cents * qty

        return items, total
    except Exception:
        return [], 0

def _idem(prefix: str, request) -> str:
    sk = getattr(request.session, "session_key", "") or ""
    return f"{prefix}-{sk}-{uuid.uuid4()}"


def _send_order_receipt(order, request=None):
    """Email an HTML + text receipt to the buyer. Silent if no email set."""
    if not getattr(order, "email", ""):
        return

    # session guard (avoid duplicate send if user reloads return URL)
    if request and request.session.get("receipt_sent_for") == order.id:
        return

    items = OrderItem.objects.filter(order=order)
    placed = (
        getattr(order, "created_dt", None)
        or getattr(order, "created_at", None)
        or getattr(order, "created_on", None)
    )
    ctx = {
        "order": order,
        "items": items,
        "placed": localtime(placed) if placed else None,
        "site_name": getattr(settings, "SITE_NAME", "AutoMart"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", getattr(settings, "DEFAULT_FROM_EMAIL", "")),
        "detail_url": request.build_absolute_uri(reverse("order_detail", args=[order.id])) if request else "",
    }

    subject = f"Receipt for Order #{order.id} — {ctx['site_name']}"
    text_body = render_to_string("payment/emails/receipt.txt", ctx)
    html_body = render_to_string("payment/emails/receipt.html", ctx)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[order.email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)

    if request:
        request.session["receipt_sent_for"] = order.id

def _cents_to_str(c: int) -> str:
    return str((Decimal(int(c)) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def _compute_breakdown(items):
    """
    items: list of {"name": str, "unit_amount": int (cents), "quantity": int}
    returns (subtotal_cents, tax_cents, fee_cents, total_cents)
    """
    subtotal = sum(int(it["unit_amount"]) * int(it["quantity"]) for it in items)
    tax = int((Decimal(subtotal) * TAX_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    fees = int(FEE_CENTS)
    total = subtotal + tax + fees
    return subtotal, tax, fees, total

def _clear_user_carts(request):
    """
    Idempotently clear both the session-cart (this app) and the marketplace DB cart.
    Safe to call multiple times.
    """
    # 1) session cart used by this app (if present)
    try:
        from .cart import clear as session_cart_clear
        session_cart_clear(request)
    except Exception:
        request.session.pop("cart", None)

    # 2) marketplace Cart (DB) keyed by session_key
    try:
        from marketplace.models import Cart as MarketplaceCart
        sk = request.session.session_key
        if sk:
            cart_obj = MarketplaceCart.objects.filter(session_key=sk).first()
            if cart_obj:
                cart_obj.cartitem_set.all().delete()
    except Exception:
        pass


# ----------------------------- Pages -----------------------------

@login_required
def checkout_page(request):
    items, total_cents = collect_checkout_items(request)
    ui_currency = (request.session.get("currency") or CURRENCY).upper()
    return render(request, "payment/checkout.html", {
        "items": items,
        "total_cents": total_cents,
        "currency": ui_currency,
        "PAYPAL_CLIENT_ID": getattr(settings, "PAYPAL_CLIENT_ID", ""),
    })


# ----------------------------- PayPal: Redirect Flow -----------------------------


@login_required
def paypal_start(request):
    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])

    # Primary source: your session/checkout util
    items, total_cents = collect_checkout_items(request)

    # Fallback: marketplace DB cart → items
    if total_cents <= 0 or not items:
        items, total_cents = _fallback_items_from_marketplace(request)

    if total_cents <= 0 or not items:
        messages.error(request, "Your cart is empty.")
        return redirect("cart")

    # --- compute, create order, create PayPal order, redirect (unchanged) ---
    subtotal, tax, fees, total = _compute_breakdown(items)

    order = Order.objects.create(
        user=request.user,
        email=getattr(request.user, "email", "") or "",
        currency=(getattr(settings, "PAYMENT_CURRENCY", "usd") or "usd").lower(),
        total_amount=total,
        status="pending",
        gateway="paypal",
    )
    for it in items:
        OrderItem.objects.create(
            order=order,
            product_id=it.get("product_id", ""),
            product_name=it["name"],
            unit_amount=int(it["unit_amount"]),
            quantity=int(it["quantity"]),
        )
    if tax > 0:
        OrderItem.objects.create(order=order, product_id="", product_name="Tax",  unit_amount=tax,  quantity=1)
    if fees > 0:
        OrderItem.objects.create(order=order, product_id="", product_name="Fees", unit_amount=fees, quantity=1)

    currency = order.currency.upper()
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "custom_id": str(order.id),
            "invoice_id": order.order_number,
            "amount": {
                "currency_code": currency,
                "value": _cents_to_str(total),
                "breakdown": {
                    "item_total": {"currency_code": currency, "value": _cents_to_str(subtotal)},
                    **({"tax_total": {"currency_code": currency, "value": _cents_to_str(tax)}} if tax > 0 else {}),
                    **({"handling":  {"currency_code": currency, "value": _cents_to_str(fees)}} if fees > 0 else {}),
                },
            },
            "items": [
                {
                    "name": it["name"][:127],
                    "quantity": str(int(it["quantity"])),
                    "unit_amount": {"currency_code": currency, "value": _cents_to_str(int(it["unit_amount"]))},
                } for it in items
            ],
        }],
        "application_context": {
            "shipping_preference": "NO_SHIPPING",
            "return_url": request.build_absolute_uri(reverse("paypal_return")),
            "cancel_url": request.build_absolute_uri(reverse("checkout_canceled")),
        },
    }

    access = _paypal_access_token()
    res = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders",
        json=body,
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
        timeout=20,
    )
    res.raise_for_status()
    data = res.json()

    order.external_id = data.get("id", "")
    order.save(update_fields=["external_id"])

    for link in data.get("links", []):
        if link.get("rel") in ("approve", "payer-action"):
            return redirect(link["href"])

    return HttpResponseBadRequest("PayPal approval link missing.")




def _finalize_inventory(order):
    """
    After an order is paid:
    - mark the purchased cars as sold/unavailable (best-effort based on your model fields)
    - remove those cars from ALL marketplace carts
    Safe to call multiple times.
    """
    try:
        from models.models import Car
    except Exception:
        Car = None

    # collect car ids from OrderItems (they're stored as strings)
    car_ids = []
    for oi in OrderItem.objects.filter(order=order):
        pid = (oi.product_id or "").strip()
        if pid.isdigit():
            car_ids.append(int(pid))

    if not car_ids:
        return

    # 1) mark cars as sold/unavailable
    if Car:
        cars = list(Car.objects.filter(pk__in=car_ids))
        # figure out which field to flip
        sold_field = None
        sample = cars[0] if cars else None
        if sample is not None:
            if hasattr(sample, "sold"):
                sold_field = "sold"
            elif hasattr(sample, "is_sold"):
                sold_field = "is_sold"
            elif hasattr(sample, "available"):
                sold_field = "available"  # will set to False
            elif hasattr(sample, "status"):
                sold_field = "status"     # set to "sold" if possible

        for car in cars:
            try:
                if sold_field in ("sold", "is_sold"):
                    setattr(car, sold_field, True)
                    car.save(update_fields=[sold_field])
                elif sold_field == "available":
                    setattr(car, "available", False)
                    car.save(update_fields=["available"])
                elif sold_field == "status":
                    # try to assign "sold"; if your choices differ, at least store a truthy value
                    try:
                        setattr(car, "status", "sold")
                        car.save(update_fields=["status"])
                    except Exception:
                        # last resort: plain save so any business logic runs
                        car.save()
                else:
                    # no known field; still save so signals/hooks can run
                    car.save()
            except Exception:
                pass

    # 2) remove these cars from ALL marketplace carts
    try:
        from marketplace.models import Cart as MarketplaceCart
        # try a direct CartItem model if it exists
        try:
            from marketplace.models import CartItem
            # typical shapes
            qs = CartItem.objects.all()
            if hasattr(CartItem, "car_id"):
                qs.filter(car_id__in=car_ids).delete()
            elif hasattr(CartItem, "product_id"):
                qs.filter(product_id__in=car_ids).delete()
            else:
                # fall back: scan each cart's related items
                for c in MarketplaceCart.objects.all():
                    try:
                        c.cartitem_set.filter(car_id__in=car_ids).delete()
                    except Exception:
                        try:
                            c.cartitem_set.filter(product_id__in=car_ids).delete()
                        except Exception:
                            pass
        except Exception:
            # no CartItem import; use related name
            for c in MarketplaceCart.objects.all():
                try:
                    c.cartitem_set.filter(car_id__in=car_ids).delete()
                except Exception:
                    try:
                        c.cartitem_set.filter(product_id__in=car_ids).delete()
                    except Exception:
                        pass
    except Exception:
        pass




# views.py

@login_required
def paypal_return(request):
    """
    User returns from PayPal (?token=<paypal_order_id>).
    Capture the order, persist evidence, clear carts, and show success.
    """
    token = request.GET.get("token")
    if not token:
        return HttpResponseBadRequest("Missing token")

    order = Order.objects.filter(external_id=token, gateway="paypal").first()

    # If we already marked it paid, don't try to capture again.
    if order and getattr(order, "status", "") == "paid":
        return redirect(reverse("checkout_success") + f"?order_id={order.id}&gateway=paypal")

    access = _paypal_access_token()
    try:
        res = requests.post(
            f"{PAYPAL_API_BASE}/v2/checkout/orders/{token}/capture",
            headers={
                "Authorization": f"Bearer {access}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": _idem("pp-capture", request),  # idempotency
            },
            timeout=20,
        )
    except requests.RequestException:
        # Network or timeout; treat as failure but don't crash
        if order:
            order.status = "failed"
            order.save(update_fields=["status"])
            return redirect(reverse("checkout_canceled") + f"?order_id={order.id}")
        return redirect(reverse("checkout_canceled"))

    # Try to parse JSON body (both success & error)
    try:
        data = res.json()
    except Exception:
        data = {}

    def _is_already_captured(err_json: dict) -> bool:
        """
        PayPal sometimes returns 422 UNPROCESSABLE_ENTITY with issue 'ORDER_ALREADY_CAPTURED'
        or duplicate request id. Treat these as success.
        """
        details = (err_json or {}).get("details") or []
        issues = {str(d.get("issue") or "").upper() for d in details if isinstance(d, dict)}
        name = str((err_json or {}).get("name") or "").upper()
        return any(
            iss in issues for iss in {
                "ORDER_ALREADY_CAPTURED",
                "DUPLICATE_REQUEST_ID",
                "CAPTURE_ALREADY_COMPLETED",
            }
        ) or name in {"UNPROCESSABLE_ENTITY"}

    success_like = res.ok or _is_already_captured(data)
    if success_like:
        if order:
            # Persist all evidence and mark paid (idempotent helper you wrote)
            order.mark_paid(evidence=(data or {}))
            # Clear both session and DB carts (idempotent)
            _clear_user_carts(request)

            return redirect(reverse("checkout_success") + f"?order_id={order.id}&gateway=paypal")

        # No local order found; just send user to success page without id.
        return redirect(reverse("checkout_success"))

    # ---- failure path ----
    if order:
        order.status = "failed"
        if hasattr(order, "gateway_response"):
            order.gateway_response = data or {"raw": res.text}
            order.save(update_fields=["status", "gateway_response"])
        else:
            order.save(update_fields=["status"])
        return redirect(reverse("checkout_canceled") + f"?order_id={order.id}")

    return redirect(reverse("checkout_canceled"))

# ----------------------------- Result Pages -----------------------------

@login_required
def checkout_success(request):
    """
    Success page. If the order is already paid, clear carts (idempotent).
    Supports ?order_id=...
    """
    oid = request.GET.get("order_id")
    order = None
    if oid:
        try:
            order = Order.objects.get(id=int(oid))
        except Exception:
            order = None

    if order and getattr(order, "status", "") == "paid":
        _clear_user_carts(request)

    return render(request, "payment/success.html", {"order": order})

@login_required
def checkout_cancel(request):
    """
    Cancel page route used by urls.py name 'checkout_canceled'.
    (We keep the function name 'checkout_cancel' to match your urls import.)
    """
    oid = request.GET.get("order_id")
    if oid:
        Order.objects.filter(id=oid, status="pending").update(status="canceled")
    return render(request, "payment/cancel.html")


# ----------------------------- (Optional) Buttons API -----------------------------
# If you ever switch to PayPal JS Buttons (no redirect), these endpoints support that flow.
# Keep them registered in urls.py only if you plan to use them.

@login_required
@require_POST
def api_paypal_create_order(request):
    """
    Server-authoritative create:
    - Builds local Order + OrderItems from session/cart
    - Creates PayPal Order with same amount & breakdown
    - Returns { paypalOrderId, orderId }
    """
    items, _ = collect_checkout_items(request)
    if not items:
        return HttpResponseBadRequest("Cart is empty")

    subtotal, tax, fees, total = _compute_breakdown(items)
    order = Order.objects.create(
        user=request.user,
        email=getattr(request.user, "email", "") or "",
        currency=CURRENCY,
        total_amount=total,
        status="pending",
        gateway="paypal",
    )
    for it in items:
        OrderItem.objects.create(
            order=order,
            product_id=it.get("product_id", ""),
            product_name=it["name"],
            unit_amount=int(it["unit_amount"]),
            quantity=int(it["quantity"]),
        )
    if tax > 0:
        OrderItem.objects.create(order=order, product_id="", product_name="Tax",  unit_amount=tax, quantity=1)
    if fees > 0:
        OrderItem.objects.create(order=order, product_id="", product_name="Fees", unit_amount=fees, quantity=1)

    currency = CURRENCY.upper()
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "custom_id": str(order.id),
                "invoice_id": f"am-{order.id}",
                "amount": {
                    "currency_code": currency,
                    "value": _cents_to_str(total),
                    "breakdown": {
                        "item_total": {"currency_code": currency, "value": _cents_to_str(subtotal)},
                        **({"tax_total": {"currency_code": currency, "value": _cents_to_str(tax)}} if tax > 0 else {}),
                        **({"handling":  {"currency_code": currency, "value": _cents_to_str(fees)}} if fees > 0 else {}),
                    },
                },
                "items": [
                    {
                        "name": it["name"][:127],
                        "quantity": str(int(it["quantity"])),
                        "unit_amount": {"currency_code": currency, "value": _cents_to_str(int(it["unit_amount"]))},
                    }
                    for it in items
                ],
            }
        ],
        "application_context": {"shipping_preference": "NO_SHIPPING"},
    }

    access = _paypal_access_token()
    res = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders",
        json=body,
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": _idem("pp-create", request),
        },
        timeout=20,
    )
    res.raise_for_status()
    data = res.json()

    pp_order_id = data.get("id")
    order.external_id = pp_order_id or ""
    order.save(update_fields=["external_id"])

    return HttpResponse(
        json.dumps({"paypalOrderId": pp_order_id, "orderId": order.id}),
        content_type="application/json"
    )

@login_required
@require_POST
def api_paypal_capture_order(request):
    """
    Capture approved order (server-side). We do not mark paid here in API flow;
    the redirect flow already handles marking paid in paypal_return.
    """
    try:
        body = json.loads(request.body or "{}")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    pp_order_id = body.get("paypalOrderId")
    local_id = body.get("orderId")
    if not pp_order_id or not local_id:
        return HttpResponseBadRequest("missing ids")

    # Ensure local order exists & matches
    if not Order.objects.filter(id=local_id, external_id=pp_order_id, gateway="paypal").exists():
        return HttpResponseBadRequest("order mismatch")

    access = _paypal_access_token()
    res = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders/{pp_order_id}/capture",
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": _idem("pp-capture", request),
        },
        timeout=20,
    )
    res.raise_for_status()
    data = res.json()
    return HttpResponse(json.dumps({"status": data.get("status", "UNKNOWN")}), content_type="application/json")


# ----------------------------- Webhook (optional) -----------------------------


# ---- make sure these imports exist near the top of views.py ----
import json
from decimal import Decimal
from django.http import HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from .models import Order, OrderItem
# ---------------------------------------------------------------


@csrf_exempt
def paypal_webhook(request):
    """
    Handle PayPal webhooks.
    We care about PAYMENT.CAPTURE.COMPLETED:
      - find the local Order
      - verify amount & currency against snapshot
      - mark paid (or failed on mismatch)
      - persist gateway evidence if the fields exist
    """
    if request.method != "POST":
        return HttpResponse(status=405)

    try:
        event = json.loads((request.body or b"{}").decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("invalid json")

    event_type = (event.get("event_type") or "").upper()
    if event_type != "PAYMENT.CAPTURE.COMPLETED":
        # Not an event we reconcile; ack to avoid retries.
        return HttpResponse(status=200)

    resource = event.get("resource") or {}
    amount   = resource.get("amount") or {}
    value    = amount.get("value", "0.00")
    currency = (amount.get("currency_code") or "").lower()

    # ---- locate the order ----
    # Prefer PayPal Order ID from supplementary_data.related_ids.order_id
    related = (resource.get("supplementary_data") or {}).get("related_ids") or {}
    paypal_order_id = related.get("order_id") or resource.get("order_id")

    # Fallback: our own id placed in custom_id or in invoice_id like "am-<id>"
    invoice_id = (resource.get("invoice_id") or "").strip()
    custom_id  = (resource.get("custom_id") or "").strip()
    if not custom_id and invoice_id.lower().startswith("am-"):
        custom_id = invoice_id[3:]

    order = None
    if paypal_order_id:
        order = Order.objects.filter(external_id=paypal_order_id, gateway="paypal").first()
    if not order and custom_id:
        try:
            order = Order.objects.get(id=int(custom_id), gateway="paypal")
        except Exception:
            order = None

    # If we still can't find it or it's already paid, just ack.
    if not order or getattr(order, "status", "") == "paid":
        return HttpResponse(status=200)

    # ---- compute paid vs expected ----
    try:
        paid_cents = int(Decimal(str(value)) * 100)
    except Exception:
        paid_cents = 0

    expected = 0
    for oi in OrderItem.objects.filter(order=order):
        expected += int(getattr(oi, "unit_amount", 0)) * int(getattr(oi, "quantity", 1))

    # Always stash the latest raw gateway JSON if the field exists
    update_fields = []
    if hasattr(order, "gateway_response"):
        # keep the most recent capture payload; you can also merge if preferred
        order.gateway_response = resource
        update_fields.append("gateway_response")

    # ---- success path ----
    if currency == getattr(order, "currency", "").lower() and paid_cents == expected:
        order.status = "paid"
        update_fields.append("status")

        # capture id (if your model has it)
        cap_id = resource.get("id")
        if cap_id and hasattr(order, "paypal_capture_id") and not getattr(order, "paypal_capture_id", None):
            order.paypal_capture_id = cap_id
            update_fields.append("paypal_capture_id")

        # paid_at timestamp
        if hasattr(order, "paid_at") and not getattr(order, "paid_at", None):
            order.paid_at = timezone.now()
            update_fields.append("paid_at")

        # try to persist payer info when present & the fields exist
        payer = resource.get("payer") or event.get("payer") or {}
        if hasattr(order, "payer_id") and not getattr(order, "payer_id", None):
            pid = payer.get("payer_id") or payer.get("id")
            if pid:
                order.payer_id = pid
                update_fields.append("payer_id")
        if hasattr(order, "payer_email") and not getattr(order, "payer_email", None):
            pe = payer.get("email_address")
            if pe:
                order.payer_email = pe
                update_fields.append("payer_email")

        order.save(update_fields=update_fields or None)
        return HttpResponse(status=200)

    # ---- mismatch / failure path ----
    order.status = "failed"
    update_fields.append("status")

    # If you have a JSONField `metadata`, attach a mismatch note
    if hasattr(order, "metadata"):
        meta = getattr(order, "metadata", {}) or {}
        meta["mismatch"] = {"got": paid_cents, "exp": expected, "currency": currency}
        order.metadata = meta
        update_fields.append("metadata")

    order.save(update_fields=update_fields or None)
    return HttpResponse(status=200)






def set_currency(request):
    """
    Store the chosen display currency in the session, then return to the previous page.
    Accepts POST or GET (?currency=USD).
    """
    cur = (request.POST.get("currency") or request.GET.get("currency") or "USD").upper()
    request.session["currency"] = cur
    return redirect(request.META.get("HTTP_REFERER") or "/")


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).order_by("-id")
    return render(request, "payment/order_list.html", {"orders": orders})

@login_required
def order_detail(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not (order.user_id == request.user.id or request.user.is_staff):
        return HttpResponse(status=403)
    items = OrderItem.objects.filter(order=order)
    return render(request, "payment/order_detail.html", {"order": order, "items": items})




@login_required
@require_POST
def order_refund(request, pk: int):
    """
    Full refund for a paid PayPal order.
    Allowed for staff OR the original purchaser.
    """
    order = get_object_or_404(Order, pk=pk)
    if not (request.user.is_staff or order.user_id == getattr(request.user, "id", None)):
        return HttpResponseForbidden("Not allowed")

    if order.status != "paid":
        return HttpResponseBadRequest("Order is not paid")
    if not getattr(order, "paypal_capture_id", ""):
        return HttpResponseBadRequest("No PayPal capture id on this order")

    # Build refund request (full amount)
    currency = (order.currency or "usd").upper()
    body = {
        "amount": {
            "value": _cents_to_str(order.total_amount),
            "currency_code": currency,
        }
    }

    access = _paypal_access_token()
    res = requests.post(
        f"{PAYPAL_API_BASE}/v2/payments/captures/{order.paypal_capture_id}/refund",
        json=body,
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": _idem("pp-refund", request),
        },
        timeout=20,
    )
    try:
        res.raise_for_status()
    except requests.HTTPError:
        return JsonResponse({"ok": False, "error": "paypal_refund_failed", "detail": res.text}, status=502)

    data = res.json()
    # Mark locally
    order.mark_refunded(amount_cents=order.total_amount, evidence=data)

    return JsonResponse({
        "ok": True,
        "refund_id": data.get("id"),
        "refund_status": data.get("status"),
    })
# ===================== START: payments/views.py =====================
import hashlib
import json
import uuid
from decimal import Decimal

import requests  # <-- NEW: using REST calls for PayPal

# ---------- Stripe ----------
import stripe
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt  # already used above
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.contrib import messages




from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.conf import settings

from marketplace.models import Cart
from .models import Order, OrderItem
from .utils import collect_checkout_items, _to_cents
from .cart import add_item as cart_add_item, remove_item as cart_remove_item, clear as cart_clear, \
    in_cart as cart_in_cart, total_cents as cart_total_cents, count as cart_count, _car_to_session_row

from models.models import  Car

stripe.api_key = settings.STRIPE_SECRET_KEY

# ---------- PayPal (SDK-free REST) ----------
# Use Sandbox for testing; switch to "https://api-m.paypal.com" for live.
PAYPAL_API_BASE = getattr(settings, "PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")

# Import your Car (or Product) model here. Adjust app/model names to match your project.
# Example assumes a Car model with fields: id, title (or name), price
try:
    def _get_product(pk):
        obj = get_object_or_404(Car, pk=pk)
        name = getattr(obj, "title", None) or getattr(obj, "name", None) or f"Item {obj.pk}"
        price = getattr(obj, "price", 0)
        return obj, name, price
except Exception:
    # Fallback: demo-only — remove in real project
    def _get_product(pk):
        # If you don't have the model import yet, this will act as a dummy
        return object(), f"Item {pk}", 19.99


@login_required
def cart_page(request):
    """Render the cart page."""
    cart = request.session.get("cart", [])
    total_cents = sum(_to_cents(r.get("price", 0)) * int(r.get("qty", 1)) for r in cart)
    currency = (getattr(settings, "PAYMENT_CURRENCY", "usd") or "usd").upper()
    return render(request, "payment/cart.html", {
        "rows": cart,
        "total_cents": total_cents,
        "currency": currency,
    })


@require_POST
@login_required
def cart_add(request, pid):
    """Add a product to cart (qty from POST or default 1)."""
    qty = int(request.POST.get("qty", 1) or 1)
    _, name, price = _get_product(pid)
    cart_add_item(request, pid=str(pid), name=name, price=price, qty=qty)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        from .cart import count as cart_count_fn, total_cents as total_cents_fn
        return JsonResponse({
            "ok": True,
            "cart_count": cart_count_fn(request),
            "cart_total_cents": total_cents_fn(request),
        })
    messages.success(request, f"Added '{name}' to cart.")
    return redirect(request.META.get("HTTP_REFERER") or reverse("cart_page"))


@require_POST
@login_required
def cart_update(request, pid):
    """Set quantity for a product (min 1)."""
    try:
        qty = int(request.POST.get("qty", 1))
    except ValueError:
        return HttpResponseBadRequest("Invalid qty")
    cart_set_qty(request, pid=str(pid), qty=qty)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        from .cart import count as cart_count_fn, total_cents as total_cents_fn
        return JsonResponse({
            "ok": True,
            "cart_count": cart_count_fn(request),
            "cart_total_cents": total_cents_fn(request),
        })
    return redirect("cart_page")


@require_POST
@login_required
def cart_remove(request, pid):
    cart_remove_item(request, pid=str(pid))
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        from .cart import count as cart_count_fn, total_cents as total_cents_fn
        return JsonResponse({
            "ok": True,
            "cart_count": cart_count_fn(request),
            "cart_total_cents": total_cents_fn(request),
        })
    return redirect("cart_page")


@require_POST
@login_required
def cart_clear_all(request):
    cart_clear(request)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("cart_page")
def _paypal_access_token() -> str:
    """
    Get an OAuth2 access token via Client Credentials.
    Requires PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in settings.
    """
    resp = requests.post(
        f"{PAYPAL_API_BASE}/v1/oauth2/token",
        data={"grant_type": "client_credentials"},
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]



@login_required
def checkout_page(request):
    items, total = collect_checkout_items(request)
    ui_currency = (request.session.get("currency") or getattr(settings, "PAYMENT_CURRENCY", "usd") or "usd").upper()

    # PayPal note: we’re charging in backend base currency (usually USD).
    # The UI currency is display-only for now.
    context = {
        "items": items,
        "total_cents": total,
        "currency": ui_currency,
        "PAYPAL_CLIENT_ID": getattr(settings, "PAYPAL_CLIENT_ID", ""),
    }
    return render(request, "payment/checkout.html", context)

@require_POST
def set_currency(request):
    cur = (request.POST.get("currency") or "USD").upper()
    request.session["currency"] = cur
    return HttpResponseRedirect(request.META.get("HTTP_REFERER") or "/")

@login_required
def api_create_stripe_session(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    items, total = collect_checkout_items(request)
    if total <= 0:
        return JsonResponse({"error": "Cart is empty"}, status=400)

    # Create local Order (pending)
    order = Order.objects.create(
        user=request.user,
        email=request.user.email or "",
        currency=settings.PAYMENT_CURRENCY or "usd",
        total_amount=total,
        status="pending",
        gateway="stripe",
    )
    for it in items:
        OrderItem.objects.create(
            order=order,
            product_id=it.get("product_id", ""),
            product_name=it["name"],
            unit_amount=it["unit_amount"],
            quantity=it["quantity"],
        )

    success_url = request.build_absolute_uri(reverse(settings.CHECKOUT_SUCCESS_URL_NAME))
    cancel_url = request.build_absolute_uri(reverse(settings.CHECKOUT_CANCEL_URL_NAME))

    line_items = [
        {
            "price_data": {
                "currency": settings.PAYMENT_CURRENCY or "usd",
                "product_data": {"name": it["name"]},
                "unit_amount": it["unit_amount"],
            },
            "quantity": it["quantity"],
        }
        for it in items
    ]

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        success_url=success_url + "?order_id=" + str(order.id) + "&gateway=stripe",
        cancel_url=cancel_url + "?order_id=" + str(order.id) + "&gateway=stripe",
        client_reference_id=str(order.id),
        metadata={"user_id": str(request.user.id)},
    )

    order.external_id = session.id
    order.save(update_fields=["external_id"])

    return JsonResponse({"sessionId": session.id})


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig = request.headers.get("Stripe-Signature", "")
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET
    try:
        event = stripe.Webhook.construct_event(payload, sig, endpoint_secret)
    except Exception:
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        data = event["data"]["object"]
        order_id = data.get("client_reference_id")
        try:
            order = Order.objects.get(
                id=order_id, external_id=data.get("id"), gateway="stripe"
            )
            order.status = "paid"
            order.save(update_fields=["status"])
        except Order.DoesNotExist:
            pass

    return HttpResponse(status=200)


@login_required
def checkout_success(request):
    order_id = request.GET.get("order_id")
    if order_id:
        try:
            order = Order.objects.get(id=order_id)
            ctx = {"order": order}
        except Order.DoesNotExist:
            ctx = {"order": None}
    else:
        ctx = {"order": None}
    return render(request, "payments/success.html", ctx)


@login_required
def checkout_cancel(request):
    order_id = request.GET.get("order_id")
    if order_id:
        Order.objects.filter(id=order_id, status="pending").update(status="canceled")
    return render(request, "payments/cancel.html")


@login_required
def api_paypal_create_order(request):
    """
    Creates a local pending Order, then creates a PayPal Order (Orders v2).
    Returns { paypalOrderId, orderId } for the front-end PayPal Buttons flow.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    items, total = collect_checkout_items(request)
    if total <= 0:
        return JsonResponse({"error": "Cart is empty"}, status=400)

    # Local pending order
    order = Order.objects.create(
        user=request.user,
        email=request.user.email or "",
        currency=settings.PAYMENT_CURRENCY or "usd",
        total_amount=total,
        status="pending",
        gateway="paypal",
    )
    for it in items:
        OrderItem.objects.create(
            order=order,
            product_id=it.get("product_id", ""),
            product_name=it["name"],
            unit_amount=it["unit_amount"],
            quantity=it["quantity"],
        )

    access = _paypal_access_token()
    decimal_amount = f"{total/100:.2f}"
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": (settings.PAYMENT_CURRENCY or "USD").upper(),
                    "value": decimal_amount,
                }
            }
        ],
    }

    res = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders",
        json=body,
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
        timeout=20,
    )
    res.raise_for_status()
    pp = res.json()
    pp_order_id = pp["id"]

    order.external_id = pp_order_id
    order.save(update_fields=["external_id"])

    return JsonResponse({"paypalOrderId": pp_order_id, "orderId": order.id})


@login_required
def api_paypal_capture_order(request):
    """
    Captures an approved PayPal Order and marks the local Order as paid.
    Expects JSON body: { "paypalOrderId": "...", "orderId": ... }
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    data = json.loads(request.body or "{}")
    pp_order_id = data.get("paypalOrderId")
    order_id = data.get("orderId")
    if not pp_order_id or not order_id:
        return JsonResponse({"error": "Missing ids"}, status=400)

    access = _paypal_access_token()
    res = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders/{pp_order_id}/capture",
        headers={"Authorization": f"Bearer {access}", "Content-Type": "application/json"},
        timeout=20,
    )
    res.raise_for_status()

    # Mark local order paid
    try:
        order = Order.objects.get(
            id=order_id, external_id=pp_order_id, gateway="paypal"
        )
        order.status = "paid"
        order.save(update_fields=["status"])
    except Order.DoesNotExist:
        pass

    return JsonResponse({"status": "ok"})
# ===================== END: payments/views.py =====================






@login_required
def cart_page(request):
    cart = list(request.session.get("cart", []))
    rows = []
    for r in cart:
        unit = int(r.get("unit_cents", 0) or 0)
        rows.append({
            "id": str(r.get("id")),
            "title": r.get("title", "Car"),
            "make": r.get("make", ""),
            "model_name": r.get("model_name", ""),
            "unit_cents": unit,
            "cover_url": r.get("cover_url"),
        })
    total = sum(row["unit_cents"] for row in rows)  # qty is 1 per car
    currency = (request.session.get("currency") or getattr(settings, "PAYMENT_CURRENCY", "usd") or "usd").upper()
    return render(request, "payment/cart.html", {"rows": rows, "total_cents": total, "currency": currency})


@require_POST
@login_required
def cart_add(request, pid):
    # single-click add: ignore qty, force single item per car
    car = get_object_or_404(Car, pk=pid)
    data = _car_to_session_row(car)
    added = cart_add_item(
        request,
        pid=data["pid"],
        title=data["title"],
        make=data["make"],
        model_name=data["model_name"],
        unit_cents=data["unit_cents"],
        cover_url=data["cover_url"],
    )
    # AJAX support to flip button and badge
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "added": added,
            "already": (not added),
            "cart_count": cart_count(request),
            "cart_total_cents": cart_total_cents(request),
        })
    # non-AJAX: just go back
    return redirect(request.META.get("HTTP_REFERER") or "cart_page")

@require_POST
@login_required
def cart_remove(request, pid):
    cart_remove_item(request, pid=str(pid))
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "cart_count": cart_count(request),
            "cart_total_cents": cart_total_cents(request),
        })
    return redirect("cart_page")

@require_POST
@login_required
def cart_clear_all(request):
    cart_clear(request)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("cart_page")





# ---------- shared helpers ----------

def _session_cart(request):
    if not request.session.session_key:
        request.session.save()
    sk = request.session.session_key
    return Cart.objects.select_related().prefetch_related("cartitem_set__car").get_or_create(
        session_key=sk,
        user=request.user if request.user.is_authenticated else None
    )[0]

def _money_cents(x) -> int:
    return int(Decimal(str(x or 0)) * 100)

def _new_idem(prefix: str, request) -> str:
    base = f"{prefix}:{request.session.session_key}:{uuid.uuid4()}"
    return hashlib.sha256(base.encode()).hexdigest()[:64]

def _build_snapshot(order: Order, cart: Cart):
    # create OrderItems snapshot and compute subtotal
    order.items.all().delete()
    subtotal = 0
    for ci in cart.items():
        oi = OrderItem.objects.create(
            order=order,
            car=ci.car,
            title=ci.car.title,
            unit_price_cents=ci.unit_price_cents,
            qty=ci.qty,
        )
        subtotal += oi.line_total_cents
    order.subtotal_cents = subtotal
    order.currency = getattr(settings, "DEFAULT_CURRENCY", "usd")
    order.save(update_fields=["subtotal_cents", "currency"])

def _verify_amounts(order: Order, paid_amount_cents: int) -> bool:
    # recompute from snapshot & compare to gateway amount
    expected = order.recompute_subtotal()
    order.save(update_fields=["subtotal_cents"])
    return int(expected) == int(paid_amount_cents)

# ---------- Stripe ----------

import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

@require_POST
@transaction.atomic
def stripe_start(request):
    cart = _session_cart(request)
    if not cart.items().exists():
        return HttpResponseBadRequest("Cart empty")

    # create order (pending) with snapshot
    order = Order.objects.create(
        user=request.user if request.user.is_authenticated else None,
        status="pending",
        client_ip=request.META.get("REMOTE_ADDR"),
        metadata={"source": "stripe"},
    )
    _build_snapshot(order, cart)

    # build line items server-side (no client totals)
    line_items = []
    for oi in order.items.all():
        line_items.append({
            "price_data": {
                "currency": order.currency,
                "product_data": { "name": oi.title },
                "unit_amount": oi.unit_price_cents,
            },
            "quantity": oi.qty,
        })

    idem = _new_idem("stripe_session", request)
    order.stripe_idempotency_key = idem
    order.save(update_fields=["stripe_idempotency_key"])

    success_url = request.build_absolute_uri(reverse("marketplace:checkout_success")) + f"?order={order.pk}"
    cancel_url = request.build_absolute_uri(reverse("marketplace:checkout_canceled")) + f"?order={order.pk}"

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=False,
        metadata={"order_id": str(order.pk)},
        expand=["payment_intent"],
        idempotency_key=idem,  # <-- idempotency
    )
    order.stripe_checkout_session = session.id
    if session.payment_intent:
        order.stripe_payment_intent = session.payment_intent.id
    order.save(update_fields=["stripe_checkout_session","stripe_payment_intent"])
    # Front-end redirect to Stripe
    return JsonResponse({"sessionId": session.id})

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception:
        return HttpResponse(status=400)

    if event["type"] == "payment_intent.succeeded":
        pi = event["data"]["object"]
        order = Order.objects.filter(stripe_payment_intent=pi["id"]).first()
        if order and order.status != "paid":
            amount_received = int(pi.get("amount_received") or 0)
            # line-item verification
            if _verify_amounts(order, amount_received):
                order.status = "paid"
                order.save(update_fields=["status"])
            else:
                order.status = "failed"
                order.metadata["mismatch"] = {"got": amount_received, "exp": order.subtotal_cents}
                order.save(update_fields=["status","metadata"])
    # You can also handle checkout.session.completed if you prefer.
    return HttpResponse(status=200)

def checkout_success(request):
    return render(request, "checkout_success.html", {"order_id": request.GET.get("order")})

def checkout_canceled(request):
    return render(request, "checkout_canceled.html", {"order_id": request.GET.get("order")})

# ---------- PayPal ----------


# ===================== PAYPAL (REST) — DROP-IN REPLACEMENT =====================
import uuid
import json
from decimal import Decimal, ROUND_HALF_UP

import requests
from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

from .models import Order, OrderItem  # your payment app models
# collect_checkout_items(request) must return (items, total_cents),
# where each item is {"name": str, "unit_amount": int (cents), "quantity": int, "product_id": optional}

# API base: sandbox by default
PAYPAL_API_BASE = getattr(settings, "PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")

def _paypal_access_token() -> str:
    """Client credentials token."""
    resp = requests.post(
        f"{PAYPAL_API_BASE}/v1/oauth2/token",
        data={"grant_type": "client_credentials"},
        auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def _idem(prefix: str, request) -> str:
    """Best-effort idempotency key."""
    try:
        sk = request.session.session_key or ""
    except Exception:
        sk = ""
    return f"{prefix}-{sk}-{uuid.uuid4()}"

@login_required
@require_POST
def api_paypal_create_order(request):
    """
    Server-authoritative create:
    - Builds local Order + OrderItems from session/cart
    - Creates PayPal Order with same amount & line-item breakdown
    - Returns { paypalOrderId, orderId }
    """
    from .utils import collect_checkout_items  # local import to avoid import cycles

    items, total_cents = collect_checkout_items(request)
    if total_cents <= 0 or not items:
        return JsonResponse({"error": "Cart is empty"}, status=400)

    # Create local pending order
    order = Order.objects.create(
        user=request.user,
        email=getattr(request.user, "email", "") or "",
        currency=(getattr(settings, "PAYMENT_CURRENCY", "usd") or "usd").lower(),
        total_amount=total_cents,
        status="pending",
        gateway="paypal",
    )
    for it in items:
        OrderItem.objects.create(
            order=order,
            product_id=it.get("product_id", ""),
            product_name=it["name"],
            unit_amount=int(it["unit_amount"]),  # cents
            quantity=int(it["quantity"]),
        )

    # Build PayPal payload with itemized breakdown
    currency = order.currency.upper()
    def cents_to_str(c: int) -> str:
        return str((Decimal(c) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    pp_items = [
        {
            "name": it["name"][:127],
            "quantity": str(int(it["quantity"])),
            "unit_amount": {"currency_code": currency, "value": cents_to_str(int(it["unit_amount"]))},
        }
        for it in items
    ]
    item_total_cents = sum(int(it["unit_amount"]) * int(it["quantity"]) for it in items)
    body = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                # Helps you find the order again in webhooks
                "custom_id": str(order.id),
                "invoice_id": f"am-{order.id}",
                "amount": {
                    "currency_code": currency,
                    "value": cents_to_str(total_cents),
                    "breakdown": {
                        "item_total": {
                            "currency_code": currency,
                            "value": cents_to_str(item_total_cents),
                        }
                    },
                },
                "items": pp_items,
            }
        ],
        # No return/cancel URLs here (JS Buttons call capture directly)
        "application_context": {"shipping_preference": "NO_SHIPPING"},
    }

    # Create PayPal order (idempotent)
    access = _paypal_access_token()
    request_id = _idem("pp-create", request)
    res = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders",
        json=body,
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": request_id,  # idempotency
        },
        timeout=20,
    )
    try:
        res.raise_for_status()
    except requests.HTTPError as e:
        return JsonResponse({"error": "paypal_create_failed", "detail": res.text}, status=502)

    data = res.json()
    pp_order_id = data.get("id")
    if not pp_order_id:
        return JsonResponse({"error": "paypal_no_id", "detail": data}, status=502)

    # Link PayPal order to your local one
    order.external_id = pp_order_id
    # If your model has a dedicated field, uncomment:
    # order.paypal_order_id = pp_order_id
    order.save(update_fields=["external_id"])

    return JsonResponse({"paypalOrderId": pp_order_id, "orderId": order.id})

@login_required
@require_POST
def api_paypal_capture_order(request):
    """
    Capture approved order (server-side). Do **not** mark paid here.
    Let the webhook make the final decision after verifying amounts.
    Expects JSON: { "paypalOrderId": "...", "orderId": ... }
    """
    try:
        body = json.loads(request.body or "{}")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    pp_order_id = body.get("paypalOrderId")
    local_id = body.get("orderId")
    if not pp_order_id or not local_id:
        return JsonResponse({"error": "missing_ids"}, status=400)

    # Optional: assert the local order matches the pp id we created
    if not Order.objects.filter(id=local_id, external_id=pp_order_id, gateway="paypal").exists():
        return JsonResponse({"error": "order_mismatch"}, status=400)

    access = _paypal_access_token()
    res = requests.post(
        f"{PAYPAL_API_BASE}/v2/checkout/orders/{pp_order_id}/capture",
        headers={
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "PayPal-Request-Id": _idem("pp-capture", request),  # idempotency
        },
        timeout=20,
    )
    try:
        res.raise_for_status()
    except requests.HTTPError:
        return JsonResponse({"error": "paypal_capture_failed", "detail": res.text}, status=502)

    data = res.json()
    status = data.get("status", "UNKNOWN")
    # DO NOT mark paid here; webhook will verify amounts and finalize
    return JsonResponse({"status": status})

@csrf_exempt
def paypal_webhook(request):
    """
    Handle PayPal webhooks (recommended event: PAYMENT.CAPTURE.COMPLETED).
    Verifies paid amount against server-side snapshot (line items),
    then sets Order.status = 'paid' (or 'failed' if mismatch).
    """
    # (Optional) verify the webhook signature using PayPal verify endpoint.
    try:
        event = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponse(status=400)

    if event.get("event_type") != "PAYMENT.CAPTURE.COMPLETED":
        return HttpResponse(status=200)

    resource = event.get("resource", {}) or {}
    amount = resource.get("amount", {}) or {}
    value = amount.get("value", "0.00")
    currency = (amount.get("currency_code") or "").lower()

    # Identify the PayPal order ID and your local custom_id
    related = (resource.get("supplementary_data", {}) or {}).get("related_ids", {}) or {}
    paypal_order_id = related.get("order_id")
    custom_id = resource.get("custom_id") or resource.get("invoice_id", "").replace("am-", "")

    # Prefer matching by PayPal order id; fallback to custom_id
    order = None
    if paypal_order_id:
        order = Order.objects.filter(external_id=paypal_order_id, gateway="paypal").first()
    if not order and custom_id:
        try:
            order = Order.objects.get(id=int(custom_id), gateway="paypal")
        except Exception:
            order = None

    if not order or order.status == "paid":
        return HttpResponse(status=200)

    # Convert value to cents
    try:
        paid_cents = int(Decimal(value) * 100)
    except Exception:
        paid_cents = 0

    # Recompute expected from snapshot (server truth)
    expected = 0
    for oi in OrderItem.objects.filter(order=order):
        expected += int(oi.unit_amount) * int(oi.quantity)

    if currency == order.currency and paid_cents == expected:
        order.status = "paid"
        # If your model has paypal_capture_id, you can store it:
        # order.paypal_capture_id = resource.get("id", "")
        order.save(update_fields=["status"])
    else:
        meta = getattr(order, "metadata", {}) or {}
        meta["mismatch"] = {"got": paid_cents, "exp": expected, "currency": currency}
        order.status = "failed"
        # If the model has a JSONField named metadata:
        try:
            order.metadata = meta
            order.save(update_fields=["status", "metadata"])
        except Exception:
            order.save(update_fields=["status"])

    return HttpResponse(status=200)
# ===================== END PAYPAL (REST) =====================
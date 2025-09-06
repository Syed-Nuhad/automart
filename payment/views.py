# ===================== START: payments/views.py =====================
import json
import requests  # <-- NEW: using REST calls for PayPal

# ---------- Stripe ----------
import stripe
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
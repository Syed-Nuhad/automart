# ===================== START: payments/views.py =====================
import json
import requests  # <-- NEW: using REST calls for PayPal

from django.conf import settings
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required

from .models import Order, OrderItem
from .utils import collect_checkout_items

# ---------- Stripe ----------
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# ---------- PayPal (SDK-free REST) ----------
# Use Sandbox for testing; switch to "https://api-m.paypal.com" for live.
PAYPAL_API_BASE = "https://api-m.sandbox.paypal.com"


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
    context = {
        "items": items,
        "total_cents": total,
        "currency": (settings.PAYMENT_CURRENCY or "usd").upper(),
        "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
        "PAYPAL_CLIENT_ID": settings.PAYPAL_CLIENT_ID,
    }
    return render(request, "payments/checkout.html", context)


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

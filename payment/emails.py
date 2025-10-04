# payment/emails.py
from __future__ import annotations
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def _fmt_money(cents: int, currency: str = "usd") -> str:
    amt = (Decimal(int(cents)) / Decimal("100")).quantize(Decimal("0.01"))
    code = (currency or "usd").upper()
    symbol = "$" if code == "USD" else ""
    return f"{symbol}{amt} {code}" if not symbol else f"{symbol}{amt}"


def _idempotency_key(order_id: int) -> str:
    return f"order_email_sent:{order_id}"


def send_order_emails(order) -> None:
    """
    Send: (1) receipt to buyer, (2) notification to staff.
    Idempotent via cache, so safe to call multiple times.
    """
    if not getattr(order, "id", None):
        return
    if getattr(order, "status", "") != "paid":
        return

    # idempotency without adding DB fields
    key = _idempotency_key(order.id)
    if cache.get(key):
        return

    context = {
        "order": order,
        "items": list(order.items.all()),
        "money": _fmt_money,
        "site_name": getattr(settings, "SITE_NAME", "AutoMart"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", settings.DEFAULT_FROM_EMAIL),
    }

    # ----- Buyer receipt -----
    to_email = (getattr(order, "email", None) or getattr(order, "payer_email", None) or "").strip()
    if to_email:
        subject = render_to_string("payment/emails/receipt_subject.txt", context).strip()
        html_body = render_to_string("payment/emails/receipt_body.html", context)
        text_body = render_to_string("payment/emails/receipt_body.txt", context)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[to_email],
            reply_to=[getattr(settings, "SUPPORT_EMAIL", to_email)],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)

    # ----- Staff / admin notify -----
    staff_to = getattr(settings, "ORDER_NOTIFICATION_EMAIL", None)
    if staff_to:
        staff_ctx = {**context, "show_raw": True}
        subject = render_to_string("payment/emails/admin_subject.txt", staff_ctx).strip()
        html_body = render_to_string("payment/emails/admin_body.html", staff_ctx)
        text_body = render_to_string("payment/emails/admin_body.txt", staff_ctx)

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[staff_to],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=True)

    # mark as sent for 24h
    cache.set(key, True, timeout=60 * 60 * 24)










######################################################################
######################################################################
######################################################################
######################################################################
######################################################################
######################################################################
######################################################################
######################################################################
######################################################################


# payment/emails.py
from decimal import Decimal
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

def _fmt_money(cents: int, currency: str = "usd") -> str:
    amt = (Decimal(int(cents)) / Decimal("100")).quantize(Decimal("0.01"))
    code = (currency or "USD").upper()
    symbol = "$" if code == "USD" else ""
    return f"{symbol}{amt} {code}" if not symbol else f"{symbol}{amt}"

def send_order_receipt(order) -> None:
    """
    Sends a customer receipt (and optional staff notification) once the order is paid.
    Safe to call multiple times; if email delivery fails we don't raise.
    """
    if not getattr(order, "email", ""):
        # nothing to send to
        return

    site_name = getattr(settings, "SITE_NAME", "AutoMart")
    subject = f"{site_name} receipt for {getattr(order, 'display_number', None) or f'Order #{order.id}'}"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or settings.EMAIL_HOST_USER
    to = [order.email]

    ctx = {
        "site_name": site_name,
        "order": order,
        "items": list(order.items.all()),
        "fmt": _fmt_money,
    }

    # Render both formats
    html = render_to_string("payment/email_receipt.html", ctx)
    text = render_to_string("payment/email_receipt.txt", ctx)

    try:
        msg = EmailMultiAlternatives(subject, text, from_email, to)
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=True)
    except Exception:
        pass

    # Optional: staff notification
    staff_to = getattr(settings, "ORDER_NOTIFICATION_EMAIL", None)
    if staff_to:
        try:
            staff_subject = f"[New Paid Order] {getattr(order, 'display_number', None) or f'#{order.id}'}"
            smsg = EmailMultiAlternatives(staff_subject, text, from_email, [staff_to])
            smsg.attach_alternative(html, "text/html")
            smsg.send(fail_silently=True)
        except Exception:
            pass

# payment/notifications.py
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string

def _order_ctx(order):
    return {
        "order": order,
        "items": order.items.all(),
        "site_name": getattr(settings, "SITE_NAME", "AutoMart"),
        "site_domain": getattr(settings, "SITE_DOMAIN", ""),
    }

def send_order_receipt(order):
    """Email the buyer a receipt. Safe to call multiple times."""
    to = []
    if getattr(order, "email", ""):
        to = [order.email]
    elif getattr(order, "user", None) and getattr(order.user, "email", ""):
        to = [order.user.email]
    if not to:
        return  # nowhere to send

    subject = f"{getattr(settings,'SITE_NAME','AutoMart')} receipt {order.display_number}"
    ctx = _order_ctx(order)
    text_body = render_to_string("payment/emails/receipt.txt", ctx)
    html_body = render_to_string("payment/emails/receipt.html", ctx)

    msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, to)
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)

def notify_admin_paid(order):
    """Ping your team on paid orders (optional)."""
    admin_to = getattr(settings, "ORDER_NOTIFICATION_EMAIL", None)
    if not admin_to:
        return
    subject = f"Paid order {order.display_number}"
    body = render_to_string("payment/emails/admin_paid.txt", _order_ctx(order))
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [admin_to], fail_silently=True)

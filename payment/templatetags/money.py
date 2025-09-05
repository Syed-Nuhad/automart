# =================== START: payments/templatetags/money.py ===================
from django import template

register = template.Library()

@register.filter
def cents_to_money(value):
    """
    Convert integer cents to '12.34' string (no currency symbol).
    Safe even if value is None or not int.
    """
    try:
        cents = int(value)
    except (TypeError, ValueError):
        return "0.00"
    return f"{cents/100:.2f}"
# =================== END: payments/templatetags/money.py ===================

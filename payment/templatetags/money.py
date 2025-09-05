# =================== START: payments/templatetags/money.py ===================
from django import template

register = template.Library()

@register.filter
def cents_to_money(value):
    try:
        return f"{int(value)/100:.2f}"
    except Exception:
        return "0.00"
# =================== END: payments/templatetags/money.py ===================

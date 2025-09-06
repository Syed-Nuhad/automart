# =================== START: payments/templatetags/money.py ===================
from django import template

register = template.Library()

RATES = {"USD": 1.0, "BDT": 110.0, "EUR": 0.92}

@register.filter
def cents_to_money(value):
    try:
        return f"{int(value)/100:.2f}"
    except Exception:
        return "0.00"

@register.filter
def cents_to_money_c(value_cents, currency="USD"):
    try:
        cents = int(value_cents or 0)
        usd_amount = cents / 100.0
        rate = float(RATES.get((currency or "USD").upper(), 1.0))
        return f"{usd_amount * rate:.2f}"
    except Exception:
        return "0.00"
# =================== END: payments/templatetags/money.py ===================

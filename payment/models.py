from django.conf import settings
from django.db import models

# Create your models here.
class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("canceled", "Canceled"),
        ("failed", "Failed"),
    ]
    GATEWAY_CHOICES = [
        ("stripe", "Stripe"),
        ("paypal", "PayPal"),
    ]

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    email        = models.EmailField(blank=True)
    currency     = models.CharField(max_length=10, default="usd")
    total_amount = models.PositiveIntegerField(default=0)  # store in cents
    status       = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    gateway      = models.CharField(max_length=12, choices=GATEWAY_CHOICES, blank=True)
    external_id  = models.CharField(max_length=128, blank=True)  # Stripe session id or PayPal order id
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id} ({self.status})"

class OrderItem(models.Model):
    order        = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product_id   = models.CharField(max_length=64, blank=True)  # your product PK/slug
    product_name = models.CharField(max_length=256)
    unit_amount  = models.PositiveIntegerField()  # cents
    quantity     = models.PositiveIntegerField(default=1)
    subtotal     = models.PositiveIntegerField(default=0)  # cents

    def save(self, *args, **kwargs):
        self.subtotal = self.unit_amount * self.quantity
        super().save(*args, **kwargs)
# ===================== END: payments/models.py =====================
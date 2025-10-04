from django.conf import settings
from django.db import models
from django.utils import timezone


# Create your models here.
class Order(models.Model):
    STATUS_CHOICES = [("pending","Pending"),("paid","Paid"),("canceled","Canceled"),("failed","Failed"),("refunded", "Refunded")]
    GATEWAY_CHOICES = [("stripe","Stripe"),("paypal","PayPal")]

    user         = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="payment_orders")
    email        = models.EmailField(blank=True)
    currency     = models.CharField(max_length=10, default="usd")
    total_amount = models.PositiveIntegerField(default=0)  # cents
    status       = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    gateway      = models.CharField(max_length=12, choices=GATEWAY_CHOICES, blank=True)
    external_id  = models.CharField(max_length=128, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    # Evidence
    paypal_capture_id = models.CharField(max_length=64, blank=True, null=True)
    payer_id         = models.CharField(max_length=64, blank=True, null=True)
    payer_email      = models.EmailField(blank=True, null=True)
    gateway_response = models.JSONField(blank=True, null=True, default=dict)
    paid_at          = models.DateTimeField(blank=True, null=True)
    refund_id        = models.CharField(max_length=64, blank=True, null=True)
    refund_amount    = models.PositiveIntegerField(default=0)  # cents
    refund_status    = models.CharField(max_length=64, blank=True, default="")
    refunded_at      = models.DateTimeField(blank=True, null=True)
    refund_response  = models.JSONField(blank=True, null=True, default=dict)

    def mark_refunded(self, amount_cents: int, evidence: dict | None = None):
        from django.utils import timezone
        self.status = "refunded"
        self.refund_amount = int(amount_cents or 0)
        self.refunded_at = self.refunded_at or timezone.now()
        if evidence:
            self.refund_status = evidence.get("status", "") or self.refund_status
            self.refund_id = evidence.get("id") or self.refund_id
            self.refund_response = evidence
        self.save(update_fields=[
            "status","refund_amount","refunded_at","refund_status","refund_id","refund_response"
        ])
    # Friendly number — allow NULL (so the UNIQUE index won’t collide during migration)
    order_number = models.CharField(
        max_length=24,
        unique=True,
        null=True,          # ← keep NULL during migration
        blank=True,
        default=None,       # ← IMPORTANT: not ""
        help_text="Human-friendly number, e.g. AM-000123",
    )

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)  # first save to get PK
        if (creating or not self.order_number) and self.pk and not self.order_number:
            self.order_number = f"AM-{self.pk:06d}"
            super().save(update_fields=["order_number"])

    @property
    def display_number(self) -> str:
        return self.order_number or (f"AM-{self.pk:06d}" if self.pk else "#?")

    def __str__(self) -> str:
        return f"Order {self.display_number} ({self.status})"

    def mark_paid(self, evidence: dict | None = None):
        self.status = "paid"
        if evidence:
            cap = None
            try:
                cap = (evidence.get("purchase_units", [{}])[0]
                               .get("payments", {}).get("captures", [{}])[0]
                               .get("id"))
            except Exception:
                cap = cap or evidence.get("id")
            if cap and not self.paypal_capture_id:
                self.paypal_capture_id = cap

            payer = evidence.get("payer", {}) or {}
            self.payer_id = self.payer_id or payer.get("payer_id") or payer.get("id")
            self.payer_email = self.payer_email or payer.get("email_address")
            self.gateway_response = evidence

        if not self.paid_at:
            self.paid_at = timezone.now()

        self.save(update_fields=["status","paid_at","paypal_capture_id","payer_id","payer_email","gateway_response"])



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
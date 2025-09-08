

from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Max
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import FieldError
import hashlib, json

from models.models import Car


# Create your models here.
class Seller(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seller_account",          # CHANGED (unique)
        related_query_name="seller_account",    # CHANGED (unique)
    )
    display_name = models.CharField(max_length=120, blank=True)  # or whatever you use
    # 🔽 NEW FIELDS
    is_verified = models.BooleanField(default=False, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="verified_sellers"
    )
    verification_note = models.CharField(max_length=255, blank=True)

    def set_verified(self, by_user=None, note:str=""):
        self.is_verified = True
        self.verified_at = timezone.now()
        self.verified_by = by_user
        self.verification_note = note
        self.save(update_fields=["is_verified","verified_at","verified_by","verification_note"])

    def unset_verified(self):
        self.is_verified = False
        self.verified_at = None
        self.verified_by = None
        self.verification_note = ""
        self.save(update_fields=["is_verified","verified_at","verified_by","verification_note"])

    def __str__(self):
        return self.display_name or f"Seller #{self.pk}"
# =================== END: Seller verification fields ===================



class CarListing(models.Model):
    CONDITION_CHOICES = [
        ('new', 'New'),
        ('used', 'Used'),
        ('certified', 'Certified Pre-Owned'),
    ]

    TRANSMISSION_CHOICES = [
        ('auto', 'Automatic'),
        ('manual', 'Manual'),
        ('cvt', 'CVT'),
        ('other', 'Other'),
    ]

    FUEL_CHOICES = [
        ('petrol', 'Petrol'),
        ('diesel', 'Diesel'),
        ('hybrid', 'Hybrid'),
        ('electric', 'Electric'),
        ('cng', 'CNG'),
        ('other', 'Other'),
    ]

    # who is selling
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='car_listings'
    )

    # basics
    title = models.CharField(max_length=150)
    make = models.CharField(max_length=80)
    model = models.CharField(max_length=80)
    year = models.PositiveIntegerField()
    mileage_km = models.PositiveIntegerField(default=0)

    condition = models.CharField(max_length=12, choices=CONDITION_CHOICES, default='used')
    transmission = models.CharField(max_length=10, choices=TRANSMISSION_CHOICES, default='auto')
    fuel_type = models.CharField(max_length=12, choices=FUEL_CHOICES, default='petrol')

    price = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)

    # contact/location
    location = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_email = models.EmailField(blank=True)

    # publishing workflow
    is_published = models.BooleanField(default=False)  # require moderation toggle
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # SEO
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} — {self.make} {self.model} {self.year}'

    def save(self, *args, **kwargs):
        if not self.slug:
            base = f'{self.title}-{self.make}-{self.model}-{self.year}'
            self.slug = slugify(base)[:175]
        # default contact email to user’s email if not filled
        if not self.contact_email and self.seller and getattr(self.seller, "email", ""):
            self.contact_email = self.seller.email
        super().save(*args, **kwargs)


def listing_upload_path(instance, filename):
    # media/listings/<listing_id>/<filename>
    return f'listings/{instance.listing_id}/{filename}'


class CarPhoto(models.Model):
    listing = models.ForeignKey(CarListing, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to=listing_upload_path)
    alt_text = models.CharField(max_length=120, blank=True)
    is_cover = models.BooleanField(default=False)  # one can be cover

    uploaded_at = models.DateTimeField(auto_now_add=True)
    constraints = [
        models.UniqueConstraint(
            fields=['listing'],
            condition=models.Q(is_cover=True),
            name='unique_cover_per_listing'
        )
    ]
    class Meta:
        ordering = ['-is_cover', '-uploaded_at']

    def __str__(self):
        return f'Photo for {self.listing_id} (cover={self.is_cover})'




class SellerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seller_profile",  # KEEP this (distinct from seller_account)
        related_query_name="seller_profile",
    )
    STATUS = [
        ("DRAFT", "Draft"),
        ("PENDING", "Pending review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]

    # public profile
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    dealership_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)          # public phone
    whatsapp = models.CharField(max_length=30, blank=True)       # optional
    # business/contact
    address_line1 = models.CharField(max_length=160, blank=True)
    city = models.CharField(max_length=64, blank=True)
    state = models.CharField(max_length=64, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=64, blank=True)
    tax_id = models.CharField(max_length=64, blank=True)         # VAT/TIN/etc.
    # verification docs
    id_document = models.FileField(upload_to="kyc/", blank=True, null=True)
    dealer_license = models.FileField(upload_to="kyc/", blank=True, null=True)

    terms_accepted_at = models.DateTimeField(blank=True, null=True)
    verification_status = models.CharField(max_length=10, choices=STATUS, default="DRAFT")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"SellerProfile({self.user})"

    @property
    def is_verified(self) -> bool:
        return self.verification_status == "APPROVED"
    @property
    def profile_picture(self):
        return self.avatar


class SavedSearch(models.Model):
    FREQ_DAILY  = "DAILY"
    FREQ_WEEKLY = "WEEKLY"
    FREQ_CHOICES = [(FREQ_DAILY, "Daily"), (FREQ_WEEKLY, "Weekly")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_searches")
    name = models.CharField(max_length=120, blank=True)
    query_json = models.JSONField(default=dict)
    params = models.JSONField(default=dict)
    params_hash = models.CharField(max_length=40, db_index=True)
    frequency = models.CharField(max_length=10, choices=FREQ_CHOICES, default=FREQ_DAILY)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # 👉 Only watermark we maintain without any background job
    last_seen_car_created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = (("user", "params_hash"),)
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or f"SavedSearch #{self.pk}"

    def set_params(self, raw_params: dict):
        allow = {
            "make", "model_name", "body_type", "transmission", "fuel",
            "price_min", "price_max", "mileage_max",
            "is_featured", "is_new", "is_certified", "is_hot",
        }
        cleaned = {k: v for k, v in raw_params.items() if k in allow and v not in ("", None)}
        for k, v in list(cleaned.items()):
            if isinstance(v, str):
                cleaned[k] = v.strip()
        for b in ["is_featured","is_new","is_certified","is_hot"]:
            if b in cleaned:
                cleaned[b] = str(cleaned[b]).lower() in ("1","true","on","yes")
        self.params = cleaned
        self.params_hash = hashlib.sha1(json.dumps(cleaned, sort_keys=True).encode("utf-8")).hexdigest()

    def queryset(self):
        from .models import Car
        p  = self.params or {}
        qs = Car.objects.all()
        if "make" in p:           qs = qs.filter(make__name__iexact=p["make"])
        if "model_name" in p:     qs = qs.filter(model_name__iexact=p["model_name"])
        if "body_type" in p:      qs = qs.filter(body_type__name__iexact=p["body_type"])
        if "transmission" in p:   qs = qs.filter(transmission=p["transmission"])
        if "fuel" in p:           qs = qs.filter(fuel=p["fuel"])
        if "price_min" in p:      qs = qs.filter(price__gte=p["price_min"] or 0)
        if "price_max" in p:      qs = qs.filter(price__lte=p["price_max"])
        if "mileage_max" in p:    qs = qs.filter(mileage__lte=p["mileage_max"])
        if p.get("is_featured"):  qs = qs.filter(is_featured=True)
        if p.get("is_new"):       qs = qs.filter(is_new=True)
        if p.get("is_certified"): qs = qs.filter(is_certified=True)
        if p.get("is_hot"):       qs = qs.filter(is_hot=True)
        return qs

    def new_matches_qs(self):
        qs = self.queryset()
        if self.last_seen_car_created_at:
            qs = qs.filter(created__gt=self.last_seen_car_created_at)
        return qs

    def newest_car_created(self):
        return self.queryset().aggregate(mx=Max("created"))["mx"]


class SavedSearchHit(models.Model):
    saved_search = models.ForeignKey(SavedSearch, on_delete=models.CASCADE, related_name="hits")
    car = models.ForeignKey(Car, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    notified = models.BooleanField(default=True)  # True if an alert was sent for this hit
    last_seen_car_created_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        unique_together = (('saved_search', 'car'),)
        indexes = [
            models.Index(fields=['saved_search', 'created_at']),
        ]

    def __str__(self):
        return f"Hit for {self.saved_search.name or 'Search'} – Car #{self.car.id}"


    @staticmethod
    def hash_for(params: dict) -> str:
        """
        Stable SHA-1 over normalized params dict.
        """
        return hashlib.sha1(
            json.dumps(params or {}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def set_params(self, params: dict) -> None:
        """
        Normalize and store params + params_hash.
        Allowed keys match your filters.
        """
        allowed = {
            "make", "model_name", "body_type", "transmission", "fuel",
            "price_min", "price_max", "mileage_max",
            "is_featured", "is_new", "is_certified", "is_hot",
        }
        cleaned = {}
        for k, v in (params or {}).items():
            if k in allowed:
                s = str(v).strip()
                if s != "":
                    cleaned[k] = s
        self.params = cleaned
        self.params_hash = self.hash_for(cleaned)

    def queryset(self):
        """
        Build the base queryset from self.params using your field names:
          make, model_name, body_type, transmission, fuel,
          price_min, price_max, mileage_max, is_featured, is_new, is_certified, is_hot
        NOTE: This references CarListing defined earlier in this file.
        """
        # CarListing is defined above in this same module
        qs = CarListing.objects.filter(is_active=True)
        p = (self.params or self.query_json or {})  # keep backward-compat

        # helpers
        def to_int(v):
            try:
                return int(str(v).replace(",", ""))
            except Exception:
                return None

        def truthy(key):
            return str(p.get(key, "")).lower() in {"1", "true", "yes", "on"}

        # make (works whether CharField or FK to a Make with 'name')
        if p.get("make"):
            val = p["make"]
            try:
                qs = qs.filter(make__name__iexact=val)
            except FieldError:
                try:
                    qs = qs.filter(make__iexact=val)
                except FieldError:
                    pass

        # exact text fields
        if p.get("model_name"):
            qs = qs.filter(model_name__iexact=p["model_name"])
        if p.get("body_type"):
            qs = qs.filter(body_type__iexact=p["body_type"])
        if p.get("transmission"):
            qs = qs.filter(transmission__iexact=p["transmission"])
        if p.get("fuel"):
            qs = qs.filter(fuel__iexact=p["fuel"])

        # numeric ranges
        v = to_int(p.get("price_min"))
        if v is not None:
            qs = qs.filter(price__gte=v)
        v = to_int(p.get("price_max"))
        if v is not None:
            qs = qs.filter(price__lte=v)
        v = to_int(p.get("mileage_max"))
        if v is not None:
            qs = qs.filter(mileage__lte=v)

        # boolean flags
        if truthy("is_featured"):
            qs = qs.filter(is_featured=True)
        if truthy("is_new"):
            qs = qs.filter(is_new=True)
        if truthy("is_certified"):
            qs = qs.filter(is_certified=True)
        if truthy("is_hot"):
            qs = qs.filter(is_hot=True)

        # ordering: prefer '-created' if that field exists, else '-id'
        has_created = any(f.name == "created" for f in CarListing._meta.fields)
        return qs.order_by("-created" if has_created else "-id")

    def new_matches_qs(self):
        """
        Return only listings newer than the watermark.
        If no watermark, return the base queryset.
        """
        qs = self.queryset()
        has_created = any(f.name == "created" for f in CarListing._meta.fields)
        if self.last_seen_car_created_at and has_created:
            qs = qs.filter(created__gt=self.last_seen_car_created_at)
        return qs


class Cart(models.Model):
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def items(self):
        return self.cartitem_set.select_related("car")

    def subtotal_cents(self):
        return sum(i.line_total_cents() for i in self.items())

    def __str__(self): return f"Cart#{self.pk}"

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE)
    car  = models.ForeignKey(Car, on_delete=models.PROTECT)   # CHANGED
    qty  = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(10)])
    unit_price_cents = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if self.unit_price_cents == 0:
            price = float(self.car.price or 0)
            self.unit_price_cents = int(round(price * 100))
        super().save(*args, **kwargs)

class Order(models.Model):
    STATUS = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
        ("canceled", "Canceled"),
    ]
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="marketplace_orders")
    created = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=STATUS, default="pending")

    # snapshot totals (cents)
    subtotal_cents = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=10, default="usd")

    # PSP refs
    stripe_payment_intent = models.CharField(max_length=64, blank=True, db_index=True)
    stripe_checkout_session = models.CharField(max_length=64, blank=True, db_index=True)
    paypal_order_id = models.CharField(max_length=64, blank=True, db_index=True)
    paypal_capture_id = models.CharField(max_length=64, blank=True, db_index=True)

    # idempotency keys (what we used when creating charges)
    stripe_idempotency_key = models.CharField(max_length=80, blank=True)
    paypal_request_id = models.CharField(max_length=80, blank=True)

    # audit
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    def recompute_subtotal(self):
        self.subtotal_cents = sum(oi.line_total_cents for oi in self.items.all())
        return self.subtotal_cents

    def __str__(self): return f"Order#{self.pk} {self.status}"



class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    car   = models.ForeignKey(Car, on_delete=models.PROTECT)  # CHANGED
    title = models.CharField(max_length=255)
    unit_price_cents = models.PositiveIntegerField()
    qty = models.PositiveIntegerField(default=1)
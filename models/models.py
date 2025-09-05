# models/models.py
from django.conf import settings
from django.contrib import admin
from django.db import models
from django.db.models import Count, Avg, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify



class Make(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    class Meta: ordering = ["name"]
    def __str__(self): return self.name
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class BodyType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    class Meta:
        verbose_name = "Body type"
        verbose_name_plural = "Body types"
        ordering = ["name"]
    def __str__(self): return self.name
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

class Car(models.Model):
    TRANSMISSION_CHOICES = [("Automatic","Automatic"),("Manual","Manual"),("CVT","CVT")]
    FUEL_CHOICES = [("Petrol","Petrol"),("Diesel","Diesel"),("Hybrid","Hybrid"),("Electric","Electric")]

    # basic
    title = models.CharField(max_length=200)
    make = models.ForeignKey(Make, on_delete=models.PROTECT, related_name="cars")
    model_name = models.CharField(max_length=120, blank=True)
    body_type = models.ForeignKey(BodyType, on_delete=models.SET_NULL, null=True, blank=True, related_name="cars")

    # specs
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    mileage = models.PositiveIntegerField(null=True, blank=True, help_text="Miles")
    transmission = models.CharField(max_length=20, choices=TRANSMISSION_CHOICES, blank=True)
    fuel = models.CharField(max_length=20, choices=FUEL_CHOICES, blank=True)

    # media
    cover = models.ImageField(upload_to="cars/covers/", null=True, blank=True)

    # flags
    is_featured = models.BooleanField(default=False, help_text="Show this car in the Featured section")
    is_new = models.BooleanField(default=False)
    is_certified = models.BooleanField(default=False)
    is_hot = models.BooleanField(default=False)

    # extra
    overview = models.TextField(blank=True)
    history = models.TextField(blank=True)
    seller_name = models.CharField(max_length=200, blank=True)
    seller_meta = models.CharField(max_length=200, blank=True)
    seller_email = models.EmailField(blank=True)   # <-- ADD THIS
    seller_phone = models.CharField(max_length=32, blank=True)  # e.g. "+1 555 123 4567"
    seller_image = models.ImageField(upload_to="profiles/", blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    @admin.display(description="Rating")
    def rating_summary(self, obj):
        agg = CarReview.aggregate_for_car(obj.id)
        avg = agg.get("avg") or 0.0
        cnt = agg.get("count") or 0
        return f"{avg:.1f} ({cnt})"
    class Meta: ordering = ["-created",]
    def __str__(self): return self.title

    @property
    def seller_avatar(self) -> str | None:
        """
        Best-available seller avatar URL for this car.
        Priority: car.seller_image → seller.profile_image → car.seller_photo
        Returns None if nothing is available.
        """
        # 1) Car-level seller_image
        if getattr(self, "seller_image", None):
            try:
                return self.seller_image.url
            except Exception:
                pass

        # 2) Related Seller.profile_image (if you have a Seller relation + field)
        seller = getattr(self, "seller", None)
        if seller and getattr(seller, "profile_image", None):
            try:
                return seller.profile_image.url
            except Exception:
                pass

        # 3) Car-level seller_photo (if you use it)
        if getattr(self, "seller_photo", None):
            try:
                return self.seller_photo.url
            except Exception:
                pass

        return None
    def get_absolute_url(self): return reverse("car_detail", args=[self.pk])

class CarImage(models.Model):
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="cars/gallery/")
    alt = models.CharField(max_length=200, blank=True)
    def __str__(self): return f"Image for {self.car} ({self.pk})"


class HeroSlide(models.Model):
    image = models.ImageField(upload_to="hero/")
    is_active = models.BooleanField(default=True)
    ordering = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["ordering"]

    def __str__(self):
        return f"Slide {self.pk}"





class TestDriveRequest(models.Model):
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="test_drives")
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    preferred_date = models.DateField(null=True, blank=True)
    preferred_time = models.TimeField(null=True, blank=True)
    message = models.TextField(blank=True)

    seller_email_snapshot = models.EmailField(blank=True)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Test drive for {self.car} by {self.full_name}"

class CarReview(models.Model):
    car        = models.ForeignKey('Car', on_delete=models.CASCADE, related_name='reviews')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subject    = models.CharField(max_length=100, blank=True)
    review     = models.TextField(max_length=500, blank=True)
    rating     = models.FloatField()  # allowed values like 0.5, 1.0, 1.5 ... 5.0
    ip         = models.CharField(max_length=45, blank=True)
    status     = models.BooleanField(default=True)  # approved/visible
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['car', 'status']),
            models.Index(fields=['car', 'created_at']),
        ]
        ordering = ['-created_at']  # newest first
        verbose_name = 'Car review'
        verbose_name_plural = 'Car reviews'

    def __str__(self):
        return self.subject or f"Review #{self.pk}"

    @classmethod
    def aggregate_for_car(cls, car_id: int):
        """
        Aggregate approved reviews for a car.

        Returns dict:
          {
            'rating_avg':  float (rounded to 1 decimal),
            'rating_count': int,
            'rating_dist': {5:int,4:int,3:int,2:int,1:int},  # bucket by whole-star
            'top_positive': CarReview|None,  # best among rating >= 3
            'top_critical': CarReview|None,  # worst among rating < 3
          }
        """
        qs = (
            cls.objects
               .filter(car_id=car_id, status=True)
               .select_related('user')
        )

        agg = qs.aggregate(
            avg=Avg('rating'),
            count=Count('id'),
            # bucket distribution (half-up ranges)
            star5=Count('id', filter=Q(rating__gte=4.75)),
            star4=Count('id', filter=Q(rating__gte=3.75, rating__lt=4.75)),
            star3=Count('id', filter=Q(rating__gte=2.75, rating__lt=3.75)),
            star2=Count('id', filter=Q(rating__gte=1.75, rating__lt=2.75)),
            star1=Count('id', filter=Q(rating__gte=0.50, rating__lt=1.75)),
        )

        # pick representative “top” reviews without assuming extra fields
        top_positive = qs.filter(rating__gte=3).order_by('-rating', '-created_at').first()
        top_critical = qs.filter(rating__lt=3).order_by('rating', '-created_at').first()

        return {
            'rating_avg': round(agg['avg'] or 0.0, 1),
            'rating_count': int(agg['count'] or 0),
            'rating_dist': {
                5: int(agg['star5'] or 0),
                4: int(agg['star4'] or 0),
                3: int(agg['star3'] or 0),
                2: int(agg['star2'] or 0),
                1: int(agg['star1'] or 0),
            },
            'top_positive': top_positive,
            'top_critical': top_critical,
        }


class ReviewFeedback(models.Model):
    ACTION_HELPFUL = "helpful"
    ACTION_REPORT  = "report"
    ACTIONS = (
        (ACTION_HELPFUL, "Helpful"),
        (ACTION_REPORT,  "Report"),
    )

    review     = models.ForeignKey('CarReview', on_delete=models.CASCADE, related_name='feedback')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='review_feedback')
    action     = models.CharField(max_length=7, choices=ACTIONS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['review','user','action'], name='uniq_feedback_per_user_per_action')
        ]

    def __str__(self):
        return f"{self.user_id} {self.action} review {self.review_id}"

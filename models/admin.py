from . import models as m
from .models import HeroSlide
from django.contrib import admin
from django.apps import apps









class CarImageInline(admin.TabularInline):
    model = m.CarImage
    extra = 1

@admin.register(m.Car)
class CarAdmin(admin.ModelAdmin):
    list_display = (
        "title","make","body_type","price","mileage",
        "transmission","fuel","is_featured","is_new","is_certified","is_hot",
        "seller_phone",  # <- optional but handy
        "created",
    )
    list_filter = (
        "is_featured","is_new","is_certified","is_hot",
        "make","body_type","transmission","fuel","created",
    )
    search_fields = ("title","model_name","seller_name","seller_phone")

    inlines = [CarImageInline]

    fieldsets = (
        ("Basic Info", {"fields": ("title","make","model_name","body_type")}),
        ("Specs", {"fields": ("price","mileage","transmission","fuel")}),
        ("Media", {"fields": ("cover",)}),
        ("Flags / Badges", {"fields": ("is_featured","is_new","is_certified","is_hot")}),
        ("Content", {"fields": ("overview","history")}),
        # ↓↓↓ Add these so you can actually input them in admin
        ("Seller", {"fields": ("seller_name","seller_meta","seller_phone","seller_email","seller_image")}),
    )



@admin.register(m.Make)
class MakeAdmin(admin.ModelAdmin):
    list_display = ("name","slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

@admin.register(m.BodyType)
class BodyTypeAdmin(admin.ModelAdmin):
    list_display = ("name","slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(HeroSlide)
class HeroSlideAdmin(admin.ModelAdmin):
    list_display = ("__str__", "is_active", "ordering")
    list_editable = ("is_active", "ordering")





@admin.register(m.CarReview)
class ReviewAdmin(admin.ModelAdmin):
    list_display  = ("id", "car", "user", "rating", "status", "created_at")
    list_filter   = ("status", "rating", "created_at")
    search_fields = ("user__username", "subject", "review")
    autocomplete_fields = ("car", "user")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

@admin.register(m.ReviewFeedback)
class ReviewFeedbackAdmin(admin.ModelAdmin):
    list_display  = ("id", "review", "user", "action", "created_at")
    list_filter   = ("action", "created_at")
    search_fields = ("review__subject", "user__username")
    autocomplete_fields = ("review", "user")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"


@admin.display(description="Rating")
def rating_summary(self):
    CarReview = apps.get_model("reviews", "CarReview")  # <-- adjust app label if different
    agg = CarReview.aggregate_for_car(self.id)
    avg = agg.get("avg") or 0.0
    cnt = agg.get("count") or 0
    return f"{avg:.1f} ({cnt})"
# marketplace/admin.py
from django.contrib import admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import CarListing, CarPhoto, SellerProfile, SavedSearch, Seller

# Admin site titles
admin.site.site_header = _("Automart Admin")
admin.site.site_title = _("Automart Admin")
admin.site.index_title = _("Dashboard")


class CarPhotoInline(admin.TabularInline):
    model = CarPhoto
    extra = 1


@admin.register(CarListing)
class CarListingAdmin(admin.ModelAdmin):
    # Use a computed column "model_label" so we don't depend on a specific field name
    list_display = ("title", "make", "model_label", "year", "price", "seller", "is_published", "created_at")
    list_filter = ("is_published", "condition", "fuel_type", "transmission", "year", "created_at")
    search_fields = (
        "title",
        "make__name",          # FK name
        "model_name",          # if you have it
        "model",               # if you have it
        "description",
        "location",
        "seller__username",
        "seller__email",
    )
    prepopulated_fields = {"slug": ("title",)}
    inlines = [CarPhotoInline]
    autocomplete_fields = ("seller",)

    @admin.display(description=_("Model"))
    def model_label(self, obj):
        # Try common possibilities and fall back to em dash
        return (
            getattr(obj, "model_name", None)
            or getattr(obj, "model", None)
            or getattr(getattr(obj, "model_ref", None), "name", None)
            or "—"
        )


@admin.register(CarPhoto)
class CarPhotoAdmin(admin.ModelAdmin):
    list_display = ("listing", "is_cover", "uploaded_at")
    list_filter = ("is_cover", "uploaded_at")


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "dealership_name", "phone", "verification_status", "created_at")
    list_filter = ("verification_status", "created_at")
    search_fields = ("user__username", "dealership_name", "phone", "tax_id")

    actions = ["approve_selected", "reject_selected"]

    @admin.action(description=_("Approve selected sellers"))
    def approve_selected(self, request, queryset):
        queryset.update(verification_status="APPROVED")

    @admin.action(description=_("Reject selected sellers"))
    def reject_selected(self, request, queryset):
        queryset.update(verification_status="REJECTED")


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "name", "frequency", "is_active",
                    "created_at", "last_seen_car_created_at", "new_count")
    list_filter = ("is_active", "frequency", "created_at")
    search_fields = ("name", "user__username", "params_hash")
    readonly_fields = ("params_hash", "created_at", "last_seen_car_created_at")
    fieldsets = (
        (_("Basic"), {"fields": ("user", "name", "frequency", "is_active")}),
        (_("Filters"), {"fields": ("params",)}),
        (_("System"), {"fields": ("params_hash", "last_seen_car_created_at", "created_at")}),
    )

    @admin.display(description=_("New matches"))
    def new_count(self, obj):
        try:
            return obj.new_matches_qs().count()
        except Exception:
            return "—"


@admin.action(description=_("Mark selected sellers as VERIFIED"))
def mark_verified(modeladmin, request, queryset):
    queryset.update(is_verified=True, verified_at=timezone.now(), verified_by=request.user)

@admin.action(description=_("Mark selected sellers as UNVERIFIED"))
def mark_unverified(modeladmin, request, queryset):
    queryset.update(is_verified=False, verified_at=None, verified_by=None, verification_note="")

@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "is_verified", "verified_at", "verified_by")
    list_filter = ("is_verified",)
    search_fields = ("display_name", "user__username", "user__email")
    actions = [mark_verified, mark_unverified]

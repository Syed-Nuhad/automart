# Register your models here.
from datetime import timezone

from django.contrib import admin
from .models import CarListing, CarPhoto, SellerProfile, SavedSearch, Seller


class CarPhotoInline(admin.TabularInline):
    model = CarPhoto
    extra = 1

@admin.register(CarListing)
class CarListingAdmin(admin.ModelAdmin):
    list_display = ('title', 'make', 'model', 'year', 'price', 'seller', 'is_published', 'created_at')
    list_filter = ('is_published', 'condition', 'fuel_type', 'transmission', 'year', 'created_at')
    search_fields = ('title', 'make', 'model', 'description', 'location', 'seller__username', 'seller__email')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [CarPhotoInline]
    autocomplete_fields = ('seller',)

@admin.register(CarPhoto)
class CarPhotoAdmin(admin.ModelAdmin):
    list_display = ('listing', 'is_cover', 'uploaded_at')
    list_filter = ('is_cover', 'uploaded_at')



@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "dealership_name", "phone", "verification_status", "created_at")
    list_filter = ("verification_status", "created_at")
    search_fields = ("user__username", "dealership_name", "phone", "tax_id")

    actions = ["approve_selected", "reject_selected"]

    def approve_selected(self, request, queryset):
        queryset.update(verification_status="APPROVED")
    approve_selected.short_description = "Approve selected sellers"

    def reject_selected(self, request, queryset):
        queryset.update(verification_status="REJECTED")
    reject_selected.short_description = "Reject selected sellers"


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "name", "frequency", "is_active",
        "created_at", "last_seen_car_created_at", "new_count",
    )
    list_filter = ("is_active", "frequency", "created_at")
    search_fields = ("name", "user__username", "params_hash")
    readonly_fields = ("params_hash", "created_at", "last_seen_car_created_at")
    fieldsets = (
        ("Basic", {"fields": ("user", "name", "frequency", "is_active")}),
        ("Filters", {"fields": ("params",)}),
        ("System", {"fields": ("params_hash", "last_seen_car_created_at", "created_at")}),
    )

    @admin.display(description="New matches")
    def new_count(self, obj):
        # safe count; avoids crashing the admin if something goes wrong
        try:
            return obj.new_matches_qs().count()
        except Exception:
            return "-"



# ----- SellerAdmin (MUST be registered; MUST have search_fields for autocomplete) -----
@admin.action(description="Mark selected sellers as VERIFIED")
def mark_verified(modeladmin, request, queryset):
    queryset.update(is_verified=True, verified_at=timezone.now(), verified_by=request.user)

@admin.action(description="Mark selected sellers as UNVERIFIED")
def mark_unverified(modeladmin, request, queryset):
    queryset.update(is_verified=False, verified_at=None, verified_by=None, verification_note="")

@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "is_verified", "verified_at", "verified_by")
    list_filter = ("is_verified",)
    search_fields = ("display_name", "user__username", "user__email")  # REQUIRED for autocomplete
    actions = [mark_verified, mark_unverified]


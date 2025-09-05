from django.contrib import admin

from payment.models import OrderItem, Order


# Register your models here.
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product_id", "product_name", "unit_amount", "quantity", "subtotal")

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "email", "gateway", "status", "currency", "total_amount", "created_at")
    list_filter  = ("status", "gateway", "currency", "created_at")
    search_fields = ("id", "email", "external_id")
    readonly_fields = ("external_id", "created_at", "updated_at")
    inlines = [OrderItemInline]
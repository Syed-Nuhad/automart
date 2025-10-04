# payment/admin.py
from django.contrib import admin
from django.utils.html import format_html
import json

from .models import Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product_name", "unit_amount", "quantity", "subtotal")
    readonly_fields = ("product_name", "unit_amount", "quantity", "subtotal")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    inlines = [OrderItemInline]

    list_display = (
        "display_number", "status", "gateway",
        "total_amount_money", "currency",
        "user", "created_at", "paid_at",
    )
    list_filter = ("status", "gateway", "currency", "created_at", "paid_at")
    search_fields = ("order_number", "external_id", "email", "payer_email")
    ordering = ("-created_at",)

    readonly_fields = (
        "order_number", "external_id", "created_at", "updated_at",
        "gateway_response_pretty",
        "paypal_capture_id", "payer_id", "payer_email", "paid_at",
        "total_amount",
    )

    fieldsets = (
        ("Order", {
            "fields": (
                "order_number", "status", "gateway", "currency", "total_amount",
                "external_id", "user", "email",
                "created_at", "updated_at", "paid_at",
            )
        }),
        ("Payer & Evidence", {
            "classes": ("collapse",),
            "fields": ("paypal_capture_id", "payer_id", "payer_email", "gateway_response_pretty"),
        }),
    )

    def total_amount_money(self, obj):
        # show cents as money (e.g. 12345 -> 123.45)
        cents = int(obj.total_amount or 0)
        return f"{cents//100:,}.{cents%100:02d}"
    total_amount_money.short_description = "Total"

    def gateway_response_pretty(self, obj):
        if not getattr(obj, "gateway_response", None):
            return "—"
        try:
            pretty = json.dumps(obj.gateway_response, indent=2, sort_keys=True)
        except Exception:
            pretty = str(obj.gateway_response)
        # <pre> prevents long JSON from breaking layout
        return format_html("<pre style='white-space:pre-wrap'>{}</pre>", pretty)
    gateway_response_pretty.short_description = "Gateway response (raw)"


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "unit_amount", "quantity", "subtotal")
    search_fields = ("product_name",)
    list_filter = ()
    ordering = ("-id",)
    readonly_fields = ("subtotal",)

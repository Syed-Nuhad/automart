
from django import template

register = template.Library()

@register.inclusion_tag("components/verified_badge.html")
def verified_badge(seller, size="sm", label=True, text="Trusted"):
    """
    Usage: {% verified_badge car.seller %}  or  {% verified_badge seller size='md' %}
    size: 'sm' | 'md' | 'lg'
    """
    show = bool(getattr(seller, "is_verified", False))
    pad = {"sm": ("px-2 py-1","small", 14), "md": ("px-2 py-1","",16), "lg": ("px-3 py-2","",18)}
    pad_cls, font_cls, svg_px = pad.get(size, pad["sm"])
    return {"show": show, "pad_cls": pad_cls, "font_cls": font_cls, "svg_px": svg_px, "label": label, "text": text}
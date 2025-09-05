
from django import template
from marketplace.models import SellerProfile

register = template.Library()

@register.filter
def is_seller(user):
    return getattr(user, "is_authenticated", False) and \
           SellerProfile.objects.filter(user_id=user.id).exists()
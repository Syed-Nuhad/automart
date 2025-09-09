# automart/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from models import views as v
from marketplace import views as mviews
from django.contrib.auth import views as auth_views
from payment import views as payment_views
from payment.views import set_currency
from preferences import views as pref_views
from django.conf.urls.i18n import set_language

urlpatterns = [
    path("admin/", admin.site.urls),

    # Home + details
    path("", v.index, name="home"),
    path("car/<int:pk>/", v.car_detail, name="car_detail"),

    # Wishlist / Compare / Finance
    path("wishlist/<int:pk>/toggle/", v.toggle_wishlist, name="toggle_wishlist"),
    path("wishlist/", v.wishlist_page, name="wishlist_page"),
    path("wishlist/clear/", v.clear_wishlist, name="clear_wishlist"),
    path("compare/<int:pk>/toggle/", v.toggle_compare, name="toggle_compare"),
    path("compare/", v.compare_page, name="compare_page"),
    path("finance/offers/", v.finance_offers, name="finance_offers"),
    path("api/counters/", v.nav_counters, name="nav_counters"),
    path("car/<int:pk>/test-drive/", v.test_drive, name="test_drive"),
    path("car/<int:pk>/share/", v.share_car, name="share_car"),
    path("car/<int:pk>/reviews.json", v.reviews_json, name="reviews_json"),
    path("car/<int:pk>/reviews/add", v.add_review, name="add_review"),
    path("car/<int:pk>/reviews/submit", v.add_review_form, name="add_review_form"),
    path("review/<int:rid>/helpful", v.review_mark_helpful, name="review_mark_helpful"),
    path("review/<int:rid>/report",  v.review_report,      name="review_report"),
    path("car/<int:pk>/review/submit", v.submit_review, name="submit_review"),

    # Sellers
    path("seller/become/", mviews.seller_become, name="seller_become"),
    path("seller/account/", mviews.seller_account_edit, name="seller_account_edit"),

    # ---- CART ----
    path("cart/", mviews.cart_view, name="cart"),
    path("cart/add/<int:car_id>/", mviews.cart_add, name="cart_add"),
    path("cart/update/<int:item_id>/", mviews.cart_update, name="cart_update"),
    path("cart/remove/<int:item_id>/", mviews.cart_remove, name="cart_remove"),

    # ---- PAYPAL ONLY ----
    path("checkout/paypal/start/",  payment_views.paypal_start,  name="paypal_start"),
    path("checkout/paypal/return/", payment_views.paypal_return, name="paypal_return"),
    path("api/paypal/create/",      payment_views.api_paypal_create_order,  name="api_paypal_create_order"),
    path("api/paypal/capture/",     payment_views.api_paypal_capture_order, name="api_paypal_capture_order"),
    path("webhooks/paypal/",        payment_views.paypal_webhook,           name="paypal_webhook"),
    path("checkout/success/",       payment_views.checkout_success,         name="checkout_success"),
    path("checkout/canceled/",      payment_views.checkout_cancel,          name="checkout_canceled"),

    # Auth + prefs
    path("accounts/login/",  auth_views.LoginView.as_view(template_name="auth/login.html"), name="login"),
    path("accounts/signup/", v.signup, name="signup"),
    path("logout/",          auth_views.LogoutView.as_view(next_page="home"), name="logout"),
    path("set-currency/",    set_currency, name="set_currency"),
    path("settings/",        pref_views.settings_page, name="settings_page"),
    path("settings/update/", pref_views.update_settings, name="update_settings"),
    path("i18n/setlang/",    set_language, name="set_language"),
    path("i18n/test/",       pref_views.i18n_test, name="i18n_test"),

    # Marketplace
    path("marketplace/", include("marketplace.urls")),

    #
    path("dealers/map/", mviews.dealer_map, name="dealer_map"),
    path("api/dealers.json", mviews.dealers_json, name="dealers_json"),
    path("api/dealers/", mviews.dealers_geojson, name="dealers_geojson"),
    path("car/<int:pk>/geo.json", v.car_geo, name="car_geo"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

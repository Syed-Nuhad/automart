from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from marketplace import views
from models import views as v
from django.contrib.auth import views as auth_views

from payment import views as payment_views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", v.index, name="home"),
    path("", include("marketplace.urls")),
    path("car/<int:pk>/", v.car_detail, name="car_detail"),

    # Wishlist
    path("wishlist/<int:pk>/toggle/", v.toggle_wishlist, name="toggle_wishlist"),
    path("wishlist/", v.wishlist_page, name="wishlist_page"),

    # Compare
    path("compare/<int:pk>/toggle/", v.toggle_compare, name="toggle_compare"),
    path("compare/", v.compare_page, name="compare_page"),

    # Finance
    path("finance/offers/", v.finance_offers, name="finance_offers"),

    # Navbar counters API
    path("api/counters/", v.nav_counters, name="nav_counters"),
    path("wishlist/clear/", v.clear_wishlist, name="clear_wishlist"),  # optional
    path("car/<int:pk>/test-drive/", v.test_drive, name="test_drive"),

    # auth
    path("accounts/login/", auth_views.LoginView.as_view(template_name="auth/login.html"), name="login"),
    path("accounts/signup/", v.signup, name="signup"),

    path("logout/", auth_views.LogoutView.as_view(next_page="home"), name="logout"),  # <-- logout
    path("car/<int:pk>/share/", v.share_car, name="share_car"),
    path("car/<int:pk>/reviews.json", v.reviews_json, name="reviews_json"),
    path("car/<int:pk>/reviews/add", v.add_review, name="add_review"),
    path('marketplace/', include('marketplace.urls')),
    path("car/<int:pk>/reviews/submit", v.add_review_form, name="add_review_form"),

    path('review/<int:rid>/helpful', v.review_mark_helpful, name='review_mark_helpful'),
    path('review/<int:rid>/report',  v.review_report,      name='review_report'),
    path("car/<int:pk>/review/submit", v.submit_review, name="submit_review"),
    path("seller/become/", views.seller_become, name="seller_become"),
    path("seller/account/", views.seller_account_edit, name="seller_account_edit"),




    path("checkout/", payment_views.checkout_page, name="checkout_page"),
    path("api/stripe/session/", payment_views.api_create_stripe_session, name="api_create_stripe_session"),
    path("webhooks/stripe/", payment_views.stripe_webhook, name="stripe_webhook"),

    path("api/paypal/create/", payment_views.api_paypal_create_order, name="api_paypal_create_order"),
    path("api/paypal/capture/", payment_views.api_paypal_capture_order, name="api_paypal_capture_order"),

    path("checkout/success/", payment_views.checkout_success, name="checkout_success"),
    path("checkout/cancel/",  payment_views.checkout_cancel,  name="checkout_cancel"),
]



if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

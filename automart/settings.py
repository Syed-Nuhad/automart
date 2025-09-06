import os
from pathlib import Path
from django.contrib.messages import constants as messages
from dotenv import load_dotenv
load_dotenv()



SECRET_KEY = "django-insecure-=#*0(l90m765b-t#h+8o^e^%tw3!4d6dz(f-w6wp^#fkcv$_39"
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", os.getenv("HOST", "")]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # app
    "models",
    'marketplace',
    "payment",
    "preferences"
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",   # after sessions, before common
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "automart.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # <-- templates folder
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "marketplace.context_processors.seller_flags",
                "payment.context_processors.cart_meta",
                "payment.context_processors.cart_meta",
                "payment.context_processors.currency_meta",
            ],
        },
    },
]

WSGI_APPLICATION = "automart.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]



# Fallbacks if a car has no seller_email:
SALES_TEAM_EMAIL = "dont@example.com"

USE_I18N = True
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("bn", "বাংলা"),
    ("ar", "العربية"),
]
LOCALE_PATHS = [ BASE_DIR / "locale" ]

TIME_ZONE = "UTC"
USE_TZ = True

# Static files (CSS, JS, images)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]      # dev source
STATIC_ROOT = BASE_DIR / "staticfiles"        # collectstatic destination (prod)

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Email info

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "syedpcfirm@gmail.com"
EMAIL_HOST_PASSWORD = "uanv icbn xrum vqww"  # Gmail App Password
DEFAULT_FROM_EMAIL = "AutoMart <syedpcfirm@gmail.com>"
# uanv icbn xrum vqww
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
LOGOUT_REDIRECT_URL = "home"

BASE_DIR = Path(__file__).resolve().parent.parent

# Payments

# Toggle sandbox/live for PayPal API base used in views.py
PAYPAL_ENVIRONMENT = os.getenv("PAYPAL_ENV", "sandbox")  # 'sandbox' or 'live'
PAYPAL_API_BASE    = "https://api-m.paypal.com" if PAYPAL_ENVIRONMENT == "live" else "https://api-m.sandbox.paypal.com"



PAYPAL_CLIENT_ID     = os.getenv("PAYPAL_CLIENT_ID", "AXcoTkzjuLBB9DiaFF5H5-4OXtdoPHiZ2LhdWq0PPqt9_ZVJHhaFpIQY9rCwpeKMNU1af8op8TVfWnxV")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "ELRkcoi05qFqse1K1PCkM3bEphVH6WQx7gy8d6rLie8TctUhzamD4CKCMJPlLJNl9mOxdgkApX_lMFCm")
PAYMENT_CURRENCY     = os.getenv("PAYMENT_CURRENCY", "usd")

# Optional: where to send users after success/cancel (these can be URL names too)
CHECKOUT_SUCCESS_URL_NAME = "checkout_success"
CHECKOUT_CANCEL_URL_NAME  = "checkout_cancel"


CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # add your public domain / tunnel below (example):
    # "https://your-domain.com",
    # "https://*.ngrok-free.app",
]


# Stripe
STRIPE_PUBLIC_KEY      = os.getenv("STRIPE_PUBLIC_KEY", "pk_test_***")
STRIPE_SECRET_KEY      = os.getenv("STRIPE_SECRET_KEY", "sk_test_***")
STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_***")

PAYPAL_API_BASE = (
    "https://api-m.paypal.com"
    if PAYPAL_ENVIRONMENT == "live"
    else "https://api-m.sandbox.paypal.com"
)
from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import activate, get_language
from django.views.decorators.http import require_http_methods

THEME_CHOICES = ["auto", "light", "dark"]
CURRENCY_CHOICES = ["USD", "BDT", "EUR"]  # extend later if needed

@require_http_methods(["GET"])
def settings_page(request):
    ctx = {
        "theme": request.session.get("theme", "auto"),
        "currency": request.session.get("currency", "USD"),
        "language": getattr(request, "LANGUAGE_CODE", get_language()) or settings.LANGUAGE_CODE,
        "LANG_CHOICES": settings.LANGUAGES,
        "CURR_CHOICES": CURRENCY_CHOICES,
        "THEME_CHOICES": THEME_CHOICES,
    }
    return render(request, "preferences/settings.html", ctx)

@require_http_methods(["POST"])
def update_settings(request):
    theme = (request.POST.get("theme") or "auto").lower()
    currency = (request.POST.get("currency") or "USD").upper()
    language = (request.POST.get("language") or settings.LANGUAGE_CODE)

    if theme not in THEME_CHOICES:
        theme = "auto"
    if currency not in CURRENCY_CHOICES:
        currency = "USD"
    valid_langs = {code for code, _ in settings.LANGUAGES}
    if language not in valid_langs:
        language = settings.LANGUAGE_CODE

    # Save to session
    request.session["theme"] = theme
    request.session["currency"] = currency

    # Set language cookie so LocaleMiddleware picks it up
    resp = HttpResponseRedirect(request.META.get("HTTP_REFERER") or "/settings/")
    resp.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
    )
    activate(language)  # apply immediately this request
    return resp
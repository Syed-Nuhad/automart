from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import transaction
from django.conf import settings
from .models import Cart, CartItem
from .models import CarListing, SellerProfile, SavedSearch
from .forms import CarListingForm, PhotoFormSet, SellerProfileForm, CarPhotoFormSet, SellerUserForm, \
    SellerOnboardingForm


@login_required
def sell_car(request):
    """Create a listing; remains pending (is_published=False)."""
    if request.method == 'POST':
        form = CarListingForm(request.POST)
        formset = PhotoFormSet(request.POST, request.FILES)
        if form.is_valid() and formset.is_valid():
            listing = form.save(commit=False)
            listing.seller = request.user
            listing.save()
            formset.instance = listing
            formset.save()
            messages.success(request, "✅ Submitted. Check it under My Listings (pending approval).")
            return redirect('marketplace:my_listings')
        messages.error(request, "Please fix the errors below and submit again.")
    else:
        form = CarListingForm()
        formset = PhotoFormSet()
    return render(request, 'marketplace/sell_car.html', {'form': form, 'formset': formset})


@login_required
def my_listings(request):
    """Seller dashboard – shows all listings (published or not)."""
    listings = (CarListing.objects
                .filter(seller=request.user)
                .prefetch_related('photos')
                .order_by('-created_at'))
    return render(request, 'marketplace/my_listings.html', {'listings': listings})


# views.py
from decimal import Decimal, InvalidOperation
from django.db.models import Q
from django.shortcuts import render
from .models import Car  # adjust import to your app

FUEL_ALIASES = {
    "petrol": "Petrol",
    "diesel": "Diesel",
    "hybrid": "Hybrid",
    "electric": "Electric",
    "cng": "CNG",
}
TRANS_ALIASES = {
    "auto": "Automatic",
    "automatic": "Automatic",
    "manual": "Manual",
    "cvt": "CVT",
}





def browse_listings(request):  # keep same name so your navbar link still works
    q          = (request.GET.get("q") or "").strip()
    make       = (request.GET.get("make") or "").strip()
    model      = (request.GET.get("model") or "").strip()
    price_min  = (request.GET.get("price_min") or "").strip()
    price_max  = (request.GET.get("price_max") or "").strip()
    mileage_max= (request.GET.get("mileage_max") or "").strip()
    fuel       = (request.GET.get("fuel") or "").strip().lower()   # 'petrol','diesel',...
    trans      = (request.GET.get("trans") or "").strip().lower()  # 'manual','auto','cvt'

    qs = (Car.objects
          .select_related("make", "body_type")
          .prefetch_related("images")
          .all())

    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(make__name__icontains=q) |
            Q(model_name__icontains=q) |
            Q(overview__icontains=q) |
            Q(history__icontains=q)
        )

    if make:
        qs = qs.filter(make__name__icontains=make)
    if model:
        qs = qs.filter(model_name__icontains=model)

    # map query values to your Car.choices (title-case)
    fuel_map  = {"petrol":"Petrol","diesel":"Diesel","hybrid":"Hybrid","electric":"Electric"}
    trans_map = {"manual":"Manual","auto":"Automatic","automatic":"Automatic","cvt":"CVT"}
    if fuel in fuel_map:
        qs = qs.filter(fuel=fuel_map[fuel])
    if trans in trans_map:
        qs = qs.filter(transmission=trans_map[trans])

    if price_min:
        try: qs = qs.filter(price__gte=Decimal(price_min))
        except: pass
    if price_max:
        try: qs = qs.filter(price__lte=Decimal(price_max))
        except: pass
    if mileage_max:
        try: qs = qs.filter(mileage__lte=int(mileage_max))
        except: pass

    # optional flags (work if you pass ?is_new=1 etc.)
    if request.GET.get("is_featured"):   qs = qs.filter(is_featured=True)
    if request.GET.get("is_new"):        qs = qs.filter(is_new=True)
    if request.GET.get("is_certified"):  qs = qs.filter(is_certified=True)
    if request.GET.get("is_hot"):        qs = qs.filter(is_hot=True)

    paginator = Paginator(qs, 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    query = {
        "q": q, "make": make, "model": model,
        "price_min": price_min, "price_max": price_max,
        "mileage_max": mileage_max, "fuel": fuel, "trans": trans,
    }
    return render(request, "marketplace/listings.html", {"page_obj": page_obj, "query": query})


def listing_detail(request, slug):
    obj = get_object_or_404(CarListing.objects.prefetch_related("photos"), slug=slug)
    return render(request, "marketplace/listing_detail.html", {"listing": obj})



# ---------- STEP 3: NEW ----------
@login_required
def edit_listing(request, slug):
    """Owner edits their listing + photos."""
    listing = get_object_or_404(CarListing, slug=slug, seller=request.user)
    if request.method == 'POST':
        form = CarListingForm(request.POST, instance=listing)
        formset = PhotoFormSet(request.POST, request.FILES, instance=listing)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "✅ Listing updated.")
            return redirect('marketplace:listing_detail', slug=listing.slug)
        messages.error(request, "Please fix the errors below.")
    else:
        form = CarListingForm(instance=listing)
        formset = PhotoFormSet(instance=listing)

    return render(request, 'marketplace/edit_listing.html', {
        'form': form,
        'formset': formset,
        'listing': listing,
    })


@login_required
def delete_listing(request, slug):
    """Owner deletes their listing (confirm page -> POST)."""
    listing = get_object_or_404(CarListing, slug=slug, seller=request.user)
    if request.method == 'POST':
        title = listing.title
        listing.delete()
        messages.success(request, f"🗑️ '{title}' deleted.")
        return redirect('marketplace:my_listings')
    return render(request, 'marketplace/confirm_delete.html', {'listing': listing})


@staff_member_required
@require_POST
def toggle_publish(request, slug):
    """Staff-only moderation toggle."""
    listing = get_object_or_404(CarListing, slug=slug)
    listing.is_published = not listing.is_published
    listing.save()
    state = "published" if listing.is_published else "unpublished"
    messages.success(request, f"✅ Listing {state}.")
    return redirect('marketplace:listing_detail', slug=listing.slug)


@login_required(login_url='login')
def edit_listing(request, pk):
    listing = get_object_or_404(CarListing, pk=pk, seller=request.user)
    profile, _ = SellerProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        profile_form = SellerProfileForm(request.POST, request.FILES, instance=profile)
        form = CarListingForm(request.POST, instance=listing)
        formset = CarPhotoFormSet(request.POST, request.FILES, instance=listing)

        if profile_form.is_valid() and form.is_valid() and formset.is_valid():
            profile_form.save()
            form.save()
            photos = formset.save(commit=False)
            for p in photos:
                p.save()
            formset.save_m2m()

            if not listing.photos.filter(is_cover=True).exists():
                first = listing.photos.order_by('uploaded_at').first()
                if first:
                    first.is_cover = True
                    first.save(update_fields=['is_cover'])

            messages.success(request, "Listing updated.")
            return redirect('marketplace:my_listings')
        messages.error(request, "Please fix the errors below.")
    else:
        profile_form = SellerProfileForm(instance=profile)
        form = CarListingForm(instance=listing)
        formset = CarPhotoFormSet(instance=listing)

    return render(request, 'marketplace/sell_car.html', {
        'profile_form': profile_form,
        'form': form,
        'formset': formset,
        'is_edit': True,
    })

@login_required(login_url='login')
def delete_listing(request, pk):
    listing = get_object_or_404(CarListing, pk=pk, seller=request.user)
    if request.method == 'POST':
        listing.delete()
        messages.success(request, "Listing deleted.")
        return redirect('marketplace:my_listings')
    return render(request, 'marketplace/confirm_delete.html', {'listing': listing})


# ---------- STAFF: PUBLISH/UNPUBLISH QUICK ACTIONS ----------

def staff_check(u): return u.is_authenticated and u.is_staff

@user_passes_test(staff_check, login_url='login')
def publish_listing(request, pk):
    listing = get_object_or_404(CarListing, pk=pk)
    listing.is_published = True
    listing.save(update_fields=['is_published'])
    messages.success(request, f"Published: {listing.title}")
    return redirect(request.GET.get('next') or 'marketplace:listings')

@user_passes_test(staff_check, login_url='login')
def unpublish_listing(request, pk):
    listing = get_object_or_404(CarListing, pk=pk)
    listing.is_published = False
    listing.save(update_fields=['is_published'])
    messages.info(request, f"Unpublished: {listing.title}")
    return redirect(request.GET.get('next') or 'marketplace:listings')

@login_required(login_url='login')
def sell_success(request):
    return render(request, 'marketplace/sell_success.html')




def _ensure_is_seller(user) -> SellerProfile:
    """
    Gate access to sellers only:
    A user counts as a seller if they already have a SellerProfile.
    (Do NOT auto-create here; otherwise every user becomes a 'seller'.)
    """
    if not user.is_authenticated:
        raise PermissionDenied("Not authenticated.")
    try:
        return user.seller_profile  # OneToOne related_name
    except SellerProfile.DoesNotExist:
        raise PermissionDenied("Seller profile required.")

@login_required
def seller_account_edit(request):
    profile = _ensure_is_seller(request.user)

    if request.method == "POST":
        uform = SellerUserForm(request.POST, instance=request.user)
        pform = SellerProfileForm(request.POST, request.FILES, instance=profile)
        if uform.is_valid() and pform.is_valid():
            uform.save()
            pform.save()
            messages.success(request, "Your seller account has been updated.")
            return redirect("seller_account_edit")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        uform = SellerUserForm(instance=request.user)
        pform = SellerProfileForm(instance=profile)

    return render(request, "seller_account_edit.html", {
        "uform": uform,
        "pform": pform,
        "profile": profile,
    })


@login_required
def seller_become(request):
    profile, _ = SellerProfile.objects.get_or_create(user=request.user)

    # If already approved, go to account page
    if profile.is_verified:
        return redirect("seller_account_edit")

    if request.method == "POST":
        form = SellerOnboardingForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            p = form.save(commit=False)
            # mark acceptance time
            if form.cleaned_data.get("accept_terms"):
                p.terms_accepted_at = timezone.now()
            # kick to review
            p.verification_status = "PENDING"
            p.save()
            messages.success(request, "Submitted for review. You’ll be notified when approved.")
            return redirect("seller_account_edit")
    else:
        form = SellerOnboardingForm(instance=profile)

    return render(request, "seller_become.html", {"form": form, "profile": profile})

@login_required
def seller_account_edit(request):
    # your existing edit view; keep it.
    profile, _ = SellerProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        uform = SellerUserForm(request.POST, instance=request.user)
        pform = SellerProfileForm(request.POST, request.FILES, instance=profile)
        if uform.is_valid() and pform.is_valid():
            uform.save(); pform.save()
            messages.success(request, "Seller profile updated.")
            return redirect("seller_account_edit")
    else:
        uform = SellerUserForm(instance=request.user)
        pform = SellerProfileForm(instance=profile)

    return render(request, "seller_account_edit.html", {
        "profile": profile, "uform": uform, "pform": pform
    })


@login_required
def saved_search_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    # Capture filters that your UI uses
    fields = [
        "q","make","model_name","body_type","transmission","fuel",
        "price_min","price_max","mileage_max","is_featured","is_new","is_certified","is_hot",
    ]
    payload = {k: request.POST.get(k) for k in fields if request.POST.get(k) not in (None, "")}

    ss = SavedSearch.objects.create(
        user=request.user,
        name=request.POST.get("name") or "My search",
        query_json=payload,               # JSONField or TextField(json.dumps(...))
        created_at=timezone.now(),
    )
    messages.success(request, "Search saved.")
    return redirect("marketplace:saved_search_list")

@login_required
def saved_search_list(request):
    searches = SavedSearch.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "marketplace/saved_search_list.html", {"searches": searches})





def _get_session_key(request):
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key

def _get_or_create_cart(request):
    sk = _get_session_key(request)
    cart, _ = Cart.objects.get_or_create(
        user=request.user if request.user.is_authenticated else None,
        session_key=sk
    )
    return cart

def cart_view(request):
    cart = _get_or_create_cart(request)
    items = cart.items()
    subtotal_cents = cart.subtotal_cents()
    return render(request, "payment/cart.html", {
        "cart": cart,
        "items": items,
        "subtotal_cents": subtotal_cents,
        "subtotal": subtotal_cents / 100.0,
        "currency": getattr(settings, "DEFAULT_CURRENCY", "usd").upper(),
    })



@require_POST
@transaction.atomic
def cart_add(request, car_id):
    cart = _get_or_create_cart(request)

    from models.models import Car
    car = get_object_or_404(Car, pk=car_id)

    # Add once only; don't auto-increment here
    item, created = CartItem.objects.select_for_update().get_or_create(
        cart=cart, car=car, defaults={"qty": 1}
    )

    # AJAX path (preferred)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "already": (not created),
            "cart_count": cart.items().count(),   # distinct cars
        })

    # Non-AJAX fallback → back to where user was
    return redirect(request.META.get("HTTP_REFERER") or "home")


@require_POST
@transaction.atomic
def cart_update(request, item_id):
    cart = _get_or_create_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    qty = int(request.POST.get("qty", 1))
    qty = 1 if qty < 1 else 10 if qty > 10 else qty
    item.qty = qty
    item.save()
    messages.info(request, "Cart updated.")
    return redirect("cart")

@require_POST
@transaction.atomic
def cart_remove(request, item_id):
    cart = _get_or_create_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    messages.warning(request, "Removed from cart.")
    return redirect("cart")

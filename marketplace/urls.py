# marketplace/urls.py
from django.urls import path
from . import views
from . import view_saved_searches as ssv

app_name = "marketplace"

urlpatterns = [
    # Create/success
    path("sell/", views.sell_car, name="sell_car"),
    path("sell/success/", views.sell_success, name="sell_success"),

    # Owner dashboard
    path("me/", views.my_listings, name="my_listings"),
    path("me/<int:pk>/edit/", views.edit_listing, name="edit_listing"),
    path("me/<int:pk>/delete/", views.delete_listing, name="delete_listing"),

    # Staff moderation
    path("admin/publish/<int:pk>/", views.publish_listing, name="publish_listing"),
    path("admin/unpublish/<int:pk>/", views.unpublish_listing, name="unpublish_listing"),

    # Browse & account
    path("browse/", views.browse_listings, name="browse_listings"),
    path("account/seller/", views.seller_account_edit, name="seller_account_edit"),

    # Saved searches
    path("saved-searches/", ssv.saved_search_list, name="saved_search_list"),
    path("saved-search/create/", ssv.saved_search_create, name="saved_search_create"),
    path("saved-search/<int:pk>/delete/", ssv.saved_search_delete, name="saved_search_delete"),
    path("saved-searches/<int:pk>/new", ssv.saved_search_new, name="saved_search_new"),
    path("saved-searches/<int:pk>/mark-read", ssv.saved_search_mark_read, name="saved_search_mark_read"),

    # Listing detail routes (scoped under /listing/)
    path("listing/<slug:slug>/", views.listing_detail, name="listing_detail"),
    path("listing/<slug:slug>/edit/", views.edit_listing, name="edit_listing_slug"),
    path("listing/<slug:slug>/delete/", views.delete_listing, name="delete_listing_slug"),
    path("listing/<slug:slug>/publish-toggle/", views.toggle_publish, name="toggle_publish_slug"),

    path("saved-searches/", ssv.saved_search_list, name="saved_search_list"),
    path("saved-search/create/", ssv.saved_search_create, name="saved_search_create"),
    path("saved-search/<int:pk>/delete/", ssv.saved_search_delete, name="saved_search_delete"),
    path("saved-searches/<int:pk>/new", ssv.saved_search_new, name="saved_search_new"),
    path("saved-searches/<int:pk>/mark-read", ssv.saved_search_mark_read, name="saved_search_mark_read"),
]

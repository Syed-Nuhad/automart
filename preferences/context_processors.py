
def ui_currency(request):
    # USD/BDT/EUR … display currency for templates
    return {"currency": request.session.get("currency", "USD")}
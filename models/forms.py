# models/forms.py
from django import forms
from .models import TestDriveRequest
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _






class TradeInForm(forms.Form):
    make = forms.CharField(label=_("Make"))
    model = forms.CharField(label=_("Model"))
    year = forms.IntegerField(label=_("Year"))
    mileage = forms.IntegerField(label=_("Mileage"), help_text=_("Enter total miles on the car."))

class TestDriveForm(forms.ModelForm):
    class Meta:
        model = TestDriveRequest
        fields = [
            "full_name",
            "email",
            "phone",
            "preferred_date",
            "preferred_time",
            "message",
        ]
        widgets = {
            "full_name":      forms.TextInput(attrs={"class": "form-control", "placeholder": "Your name"}),
            "email":          forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
            "phone":          forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional", "inputmode": "tel"}),
            "preferred_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "preferred_time": forms.TimeInput(attrs={"type": "time", "class": "form-control"}),
            "message":        forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Anything we should know?"}),
        }
        labels = {
            "message": "Notes (optional)",
        }



class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
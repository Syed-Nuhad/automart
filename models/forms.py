# models/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import TestDriveRequest

# models/forms.py
from django import forms
from .models import TestDriveRequest

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
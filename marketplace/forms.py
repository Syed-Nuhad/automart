from django import forms
from django.contrib.auth.models import User
from django.forms import inlineformset_factory
from .models import CarListing, CarPhoto, SellerProfile


class CarListingForm(forms.ModelForm):
    class Meta:
        model = CarListing
        fields = [
            'title','make','model','year','mileage_km',
            'condition','transmission','fuel_type',
            'price','description','location','contact_phone','contact_email',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Toyota Axio X Smart Edition'}),
            'make': forms.TextInput(attrs={'placeholder': 'e.g. Toyota'}),
            'model': forms.TextInput(attrs={'placeholder': 'e.g. Axio'}),
            'year': forms.NumberInput(attrs={'min': 1950, 'max': 2100}),
            'mileage_km': forms.NumberInput(attrs={'min': 0}),
            'price': forms.NumberInput(attrs={'min': 0, 'step': '0.01'}),
            'description': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Condition, service history, extras…'}),
            'location': forms.TextInput(attrs={'placeholder': 'e.g. Dhaka, Bangladesh'}),
            'contact_phone': forms.TextInput(attrs={'placeholder': '+8801XXXXXXXXX'}),
            'contact_email': forms.EmailInput(attrs={'placeholder': 'your@email.com'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            if isinstance(f.widget, (forms.TextInput, forms.NumberInput, forms.EmailInput, forms.Textarea)):
                f.widget.attrs.setdefault('class', 'form-control')
            elif isinstance(f.widget, forms.Select):
                f.widget.attrs.setdefault('class', 'form-select')

    def clean_year(self):
        y = self.cleaned_data['year']
        if y < 1950 or y > 2100:
            raise forms.ValidationError("Please enter a valid year.")
        return y

    def clean_price(self):
        p = self.cleaned_data['price']
        if p <= 0:
            raise forms.ValidationError("Price must be greater than 0.")
        return p

class CarPhotoForm(forms.ModelForm):
    class Meta:
        model = CarPhoto
        fields = ['image','alt_text','is_cover']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['image'].widget.attrs.setdefault('class', 'form-control')
        self.fields['alt_text'].widget.attrs.setdefault('class', 'form-control')
        self.fields['is_cover'].widget.attrs.setdefault('class', 'form-check-input')
    def clean_image(self):
        img = self.cleaned_data.get('image')
        if not img:
            return img
        if img.size > 5 * 1024 * 1024:  # 5MB
            raise forms.ValidationError("Image must be ≤ 5 MB.")
        valid = {'image/jpeg','image/png','image/webp'}
        if hasattr(img, 'content_type') and img.content_type not in valid:
            raise forms.ValidationError("Only JPEG, PNG or WEBP images are allowed.")
        return img
PhotoFormSet = inlineformset_factory(
    CarListing, CarPhoto, form=CarPhotoForm, extra=4, can_delete=True, max_num=10, validate_max=True
)
# Up to 5 photos; can delete; server-side cover selection allowed
CarPhotoFormSet = inlineformset_factory(
    CarListing, CarPhoto,
    form=CarPhotoForm,
    fields=['image', 'alt_text', 'is_cover'],
    extra=5,            # show 5 empty file inputs
    max_num=5,          # enforce maximum
    can_delete=True
)

class SellerOnboardingForm(forms.ModelForm):
    accept_terms = forms.BooleanField(
        required=True,
        label="I agree to the Seller Terms & Conditions"
    )

    class Meta:
        model = SellerProfile
        fields = [
            "dealership_name", "phone", "whatsapp",
            "address_line1", "city", "state", "postal_code", "country",
            "tax_id", "id_document", "dealer_license", "avatar",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # style by widget type
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.update({"class": "form-check-input"})
            elif isinstance(w, (forms.ClearableFileInput, forms.FileInput)):
                # file inputs
                w.attrs.update({"class": "form-control"})
            else:
                # text inputs / selects / textareas
                existing = w.attrs.get("class", "")
                w.attrs["class"] = (existing + " form-control").strip()

        # make sure accept_terms is a checkbox with correct class
        if "accept_terms" in self.fields:
            self.fields["accept_terms"].widget = forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            )

        # placeholders & useful input attributes
        placeholders = {
            "phone": "+800 1976250250",
            "whatsapp": "+800 1976250250",
            "dealership_name": "Your dealership / business name",
            "address_line1": "Address",
            "city": "City",
            "state": "State/Region",
            "postal_code": "Postal code",
            "country": "Country",
            "tax_id": "Tax/VAT ID (optional)",
        }
        for field_name, ph in placeholders.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.setdefault("placeholder", ph)

        if "phone" in self.fields:
            self.fields["phone"].widget.attrs.setdefault("autocomplete", "tel")
            self.fields["phone"].widget.attrs.setdefault("inputmode", "tel")
        if "whatsapp" in self.fields:
            self.fields["whatsapp"].widget.attrs.setdefault("inputmode", "tel")
        if "avatar" in self.fields:
            self.fields["avatar"].widget.attrs.setdefault("accept", "image/*")


class SellerUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.update({"class": "form-control"})

class SellerProfileForm(forms.ModelForm):
    class Meta:
        model = SellerProfile
        fields = ["avatar", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["avatar"].widget.attrs.update({"class": "form-control"})
        self.fields["phone"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "+800 1976250250",
            "autocomplete": "tel",
        })
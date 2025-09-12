from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate
from .models import User, Vehicle, Payment, Booking, DrivingLicense, Location
from datetime import datetime, timedelta

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=15, required=True)
    user_type = forms.ChoiceField(choices=User.USER_TYPES, required=True)
    location = forms.CharField(max_length=100, required=False)

    class Meta:
        model = User
        fields = ('username', 'email', 'phone_number', 'user_type', 'location', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ['make', 'model', 'year', 'category', 'condition', 'mileage', 'daily_rate', 'photo', 'description']
        widgets = {
            'make': forms.TextInput(attrs={'class': 'form-control'}),
            'model': forms.TextInput(attrs={'class': 'form-control'}),
            'year': forms.NumberInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'condition': forms.Select(attrs={'class': 'form-control'}),
            'mileage': forms.NumberInput(attrs={'class': 'form-control'}),
            'daily_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class VehicleApprovalForm(forms.Form):
    ACTION_CHOICES = (
        ('approve', 'Approve'),
        ('decline', 'Decline'),
    )
    
    action = forms.ChoiceField(choices=ACTION_CHOICES, widget=forms.RadioSelect)
    admin_notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        required=False,
        help_text="Optional notes (required when declining)"
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        admin_notes = cleaned_data.get('admin_notes')

        if action == 'decline' and not admin_notes:
            raise forms.ValidationError("Please provide a reason for declining this vehicle.")

        return cleaned_data

class LicenseVerificationForm(forms.Form):
    ACTION_CHOICES = (
        ('verify', 'Verify'),
        ('reject', 'Reject'),
    )
    
    action = forms.ChoiceField(choices=ACTION_CHOICES, widget=forms.RadioSelect)
    admin_notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        required=False,
        help_text="Optional notes (required when rejecting)"
    )

    def clean(self):
        cleaned_data = super().clean()
        action = cleaned_data.get('action')
        admin_notes = cleaned_data.get('admin_notes')

        if action == 'reject' and not admin_notes:
            raise forms.ValidationError("Please provide a reason for rejecting this license.")

        return cleaned_data

class VehicleSearchForm(forms.Form):
    pickup_location = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_active=True),
        empty_label="Select pickup location",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    dropoff_location = forms.ModelChoiceField(
        queryset=Location.objects.filter(is_active=True),
        empty_label="Select dropoff location",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    pickup_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )
    dropoff_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )
    category = forms.ChoiceField(
        choices=[('', 'Any Category')] + list(Vehicle.CATEGORY_CHOICES),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def clean(self):
        cleaned_data = super().clean()
        pickup_date = cleaned_data.get('pickup_date')
        dropoff_date = cleaned_data.get('dropoff_date')

        if pickup_date and dropoff_date:
            if pickup_date >= dropoff_date:
                raise forms.ValidationError("Dropoff date must be after pickup date.")
            if pickup_date < datetime.now():
                raise forms.ValidationError("Pickup date cannot be in the past.")

        return cleaned_data

class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['pickup_location', 'dropoff_location', 'start_date', 'end_date', 'drive_type']
        widgets = {
            'pickup_location': forms.Select(attrs={'class': 'form-control'}),
            'dropoff_location': forms.Select(attrs={'class': 'form-control'}),
            'start_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'end_date': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'drive_type': forms.Select(attrs={'class': 'form-control'}),
        }

class DrivingLicenseForm(forms.ModelForm):
    class Meta:
        model = DrivingLicense
        fields = ['license_number', 'expiry_date', 'license_image']
        widgets = {
            'license_number': forms.TextInput(attrs={'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'license_image': forms.FileInput(attrs={'class': 'form-control'}),
        }

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['email', 'phone_number']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number']
        if not phone.startswith('254'):
            raise forms.ValidationError("Phone number must start with 254")
        if len(phone) != 12:
            raise forms.ValidationError("Phone number must be 12 digits long")
        return phone

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import datetime, timedelta
from django.utils import timezone
import uuid
from django.contrib.auth.models import User
from cloudinary.models import CloudinaryField  # type: ignore # Replace ImageField with this

class User(AbstractUser):
    USER_TYPES = (
        ('client', 'Client'),
        ('owner', 'Vehicle Owner'),
        ('admin', 'Admin'),
    )
    user_type = models.CharField(max_length=10, choices=USER_TYPES, default='client')
    phone_number = models.CharField(max_length=15, blank=True)
    location = models.CharField(max_length=100, blank=True)
    driving_license_number = models.CharField(max_length=50, blank=True)
    license_expiry_date = models.DateField(null=True, blank=True)
    years_of_experience = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'carhire_user'

class Location(models.Model):
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name}, {self.city}"

class Vehicle(models.Model):
    CONDITION_CHOICES = (
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
    )
    
    CATEGORY_CHOICES = (
        ('sedan', 'Sedan'),
        ('suv', 'SUV'),
        ('hatchback', 'Hatchback'),
        ('pickup', 'Pickup Truck'),
        ('van', 'Van'),
        ('luxury', 'Luxury'),
    )

    APPROVAL_STATUS_CHOICES = (
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
    )

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vehicles')
    make = models.CharField(max_length=50)
    model = models.CharField(max_length=50)
    year = models.IntegerField(validators=[MinValueValidator(1990), MaxValueValidator(2025)])
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES)
    mileage = models.IntegerField(validators=[MinValueValidator(0)])
    daily_rate = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Changed from ImageField to CloudinaryField
    photo = CloudinaryField(
        'vehicle_photo',  # Public ID prefix for Cloudinary
        folder='vehicles/',  # Organizes files in Cloudinary
        blank=True,
        null=True,  # Optional: Allow null in DB if photo not required
        transformation={'quality': 'auto:good'},  # Auto-optimize images
        format='jpg'  # Convert to JPG by default
    )
    
    description = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)
    approval_status = models.CharField(max_length=10, choices=APPROVAL_STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True, help_text="Admin notes for approval/decline")
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_vehicles')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.year} {self.make} {self.model}"

    def is_available_for_dates(self, start_date, end_date):
        """Check if vehicle is available for the given date range"""
        if not self.is_approved or self.approval_status != 'approved':
            return False
            
        overlapping_bookings = self.bookings.filter(
            status__in=['confirmed', 'active'],
            start_date__lt=end_date,
            end_date__gt=start_date
        )
        return not overlapping_bookings.exists()

    def update_availability(self):
        """Update vehicle availability based on current bookings"""
        now = timezone.now()
        active_bookings = self.bookings.filter(
            status__in=['confirmed', 'active'],
            start_date__lte=now,
            end_date__gt=now
        )
        
        # Check if there are any active bookings
        if active_bookings.exists():
            self.is_available = False
        else:
            # Check if there are any future bookings
            future_bookings = self.bookings.filter(
                status__in=['confirmed'],
                start_date__gt=now
            )
            self.is_available = not future_bookings.exists()
        
        self.save(update_fields=['is_available'])

class Booking(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Payment'),
        ('confirmed', 'Confirmed'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    DRIVE_TYPE_CHOICES = (
        ('self', 'Self Drive'),
        ('chauffeur', 'With Chauffeur'),
    )

    booking_id = models.UUIDField(default=uuid.uuid4, editable=False)
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='bookings')
    pickup_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='pickup_bookings')
    dropoff_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='dropoff_bookings')
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    drive_type = models.CharField(max_length=10, choices=DRIVE_TYPE_CHOICES)
    total_days = models.IntegerField()
    vehicle_cost = models.DecimalField(max_digits=10, decimal_places=2)
    chauffeur_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Booking {self.booking_id} - {self.vehicle}"

    def save(self, *args, **kwargs):
        if not self.total_days:
            delta = self.end_date.date() - self.start_date.date()
            self.total_days = max(1, delta.days)
        
        self.vehicle_cost = self.vehicle.daily_rate * self.total_days
        
        if self.drive_type == 'chauffeur':
            self.chauffeur_cost = 1000 * self.total_days
        else:
            self.chauffeur_cost = 0
            
        self.total_cost = self.vehicle_cost + self.chauffeur_cost
        super().save(*args, **kwargs)
        
        # Update vehicle availability after saving booking
        self.vehicle.update_availability()

    def is_expired(self):
        """Check if booking period has ended"""
        return timezone.now() > self.end_date

    def update_status_if_expired(self):
        """Update booking status to completed if period has ended"""
        if self.status == 'active' and self.is_expired():
            self.status = 'completed'
            self.save(update_fields=['status'])
            # Update vehicle availability
            self.vehicle.update_availability()

class Payment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    email = models.EmailField(blank=True, null=True)
    mpesa_transaction_id = models.CharField(max_length=50, blank=True)
    phone_number = models.CharField(max_length=15)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Paystack specific fields
    paystack_reference = models.CharField(max_length=100, blank=True)
    paystack_access_code = models.CharField(max_length=100, blank=True)
    mpesa_transaction_id = models.CharField(max_length=100, blank=True)
    gateway_response = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Payment {self.paystack_reference} - {self.status}"


class DrivingLicense(models.Model):
    VERIFICATION_STATUS_CHOICES = (
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='license')
    license_number = models.CharField(max_length=50)
    expiry_date = models.DateField()
    license_image = models.ImageField(upload_to='licenses/')
    is_verified = models.BooleanField(default=False)
    verification_status = models.CharField(max_length=10, choices=VERIFICATION_STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True, help_text="Admin notes for verification/rejection")
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_licenses')
    verified_at = models.DateTimeField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"License for {self.user.username}"

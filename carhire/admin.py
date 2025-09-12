from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Vehicle, Booking, Payment, Location, DrivingLicense

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'user_type', 'phone_number', 'is_active')
    list_filter = ('user_type', 'is_active', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {
            'fields': ('user_type', 'phone_number', 'location', 'driving_license_number', 
                      'license_expiry_date', 'years_of_experience')
        }),
    )

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ('make', 'model', 'year', 'owner', 'daily_rate', 'condition', 'is_approved', 'is_available')
    list_filter = ('make', 'condition', 'is_approved', 'is_available', 'category')
    search_fields = ('make', 'model', 'owner__username')
    actions = ['approve_vehicles', 'disapprove_vehicles']

    def approve_vehicles(self, request, queryset):
        queryset.update(is_approved=True)
    approve_vehicles.short_description = "Approve selected vehicles"

    def disapprove_vehicles(self, request, queryset):
        queryset.update(is_approved=False)
    disapprove_vehicles.short_description = "Disapprove selected vehicles"

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('booking_id', 'client', 'vehicle', 'start_date', 'end_date', 'total_cost', 'status')
    list_filter = ('status', 'drive_type', 'created_at')
    search_fields = ('booking_id', 'client__username', 'vehicle__make', 'vehicle__model')
    readonly_fields = ('booking_id', 'total_cost', 'vehicle_cost', 'chauffeur_cost')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('booking', 'amount', 'status', 'mpesa_transaction_id', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('booking__booking_id', 'mpesa_transaction_id')

admin.site.register(User, CustomUserAdmin)
admin.site.register(Location)
admin.site.register(DrivingLicense)

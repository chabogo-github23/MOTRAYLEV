import os
import sys
import django
from datetime import datetime

# Add the project directory to the Python path
sys.path.append('/path/to/MOTREYLEV/MOT')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'motraylev.settings')
django.setup()

from django.utils import timezone
from carhire.models import Vehicle, Booking

def update_all_vehicle_availability():
    """Update availability status for all vehicles based on current bookings"""
    
    print("Updating vehicle availability...")
    
    # Update all expired bookings first
    expired_bookings = Booking.objects.filter(
        status='active',
        end_date__lt=timezone.now()
    )
    
    for booking in expired_bookings:
        booking.status = 'completed'
        booking.save()
        print(f"Updated booking {booking.booking_id} to completed")
    
    # Update vehicle availability
    vehicles = Vehicle.objects.all()
    for vehicle in vehicles:
        vehicle.update_availability()
        print(f"Updated availability for {vehicle}")
    
    print("Vehicle availability update completed!")

if __name__ == '__main__':
    update_all_vehicle_availability()

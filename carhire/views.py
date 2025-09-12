from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.utils import timezone
from django.template.loader import get_template
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import requests
from datetime import datetime, timedelta
import uuid
from django.contrib.auth.views import PasswordResetView, PasswordResetConfirmView
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes

from .models import User, Vehicle, Booking, Payment, Location, DrivingLicense
from .forms import (UserRegistrationForm, VehicleForm, VehicleSearchForm, 
                   BookingForm, DrivingLicenseForm, PaymentForm, 
                   VehicleApprovalForm, LicenseVerificationForm)

from .utils import paystack
from django.urls import reverse
import logging
logger = logging.getLogger(__name__)

def home(request):
    """Home page with search functionality"""
    search_form = VehicleSearchForm()
    featured_vehicles = Vehicle.objects.filter(is_approved=True, approval_status='approved', is_available=True)[:6]
    
    context = {
        'search_form': search_form,
        'featured_vehicles': featured_vehicles,
    }
    return render(request, 'carhire/home.html', context)

def register(request):
    """User registration"""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}!')
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required
def dashboard(request):
    """Dashboard for different user types"""
    user = request.user
    context = {'user': user}
    
    if user.user_type == 'owner':
        vehicles = Vehicle.objects.filter(owner=user)
        # Get all bookings first (no slice yet)
        all_bookings = Booking.objects.filter(vehicle__owner=user).order_by('-created_at')
        
        # Calculate total earnings before slicing
        total_earnings = all_bookings.filter(status='completed').aggregate(
            total=Sum('total_cost'))['total'] or 0
        
        # Now take the slice for recent bookings
        recent_bookings = all_bookings[:5]
        
        context.update({
            'vehicles': vehicles,
            'recent_bookings': recent_bookings,
            'total_vehicles': vehicles.count(),
            'total_earnings': total_earnings,
        })
        return render(request, 'carhire/owner_dashboard.html', context)
    
    elif user.user_type == 'client':
        all_bookings = Booking.objects.filter(client=user).order_by('-created_at')
        recent_bookings = all_bookings[:5]
        context.update({
            'recent_bookings': recent_bookings,
            'total_bookings': all_bookings.count(),  # Count all, not just the sliced ones
        })
        return render(request, 'carhire/client_dashboard.html', context)
    
    elif user.user_type == 'admin':
        total_users = User.objects.count()
        total_vehicles = Vehicle.objects.count()
        total_bookings = Booking.objects.count()
        pending_vehicle_approvals = Vehicle.objects.filter(approval_status='pending').count()
        pending_license_verifications = DrivingLicense.objects.filter(verification_status='pending').count()
        
        context.update({
            'total_users': total_users,
            'total_vehicles': total_vehicles,
            'total_bookings': total_bookings,
            'pending_vehicle_approvals': pending_vehicle_approvals,
            'pending_license_verifications': pending_license_verifications,
        })
        return render(request, 'carhire/admin_dashboard.html', context)
    
    return render(request, 'carhire/dashboard.html', context)

@login_required
def add_vehicle(request):
    """Add new vehicle (Owner only)"""
    if request.user.user_type != 'owner':
        messages.error(request, 'Only vehicle owners can add vehicles.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = VehicleForm(request.POST, request.FILES)
        if form.is_valid():
            vehicle = form.save(commit=False)
            vehicle.owner = request.user
            vehicle.approval_status = 'pending'
            vehicle.save()
            messages.success(request, 'Vehicle added successfully! Awaiting admin approval.')
            return redirect('my_vehicles')
    else:
        form = VehicleForm()
    
    return render(request, 'carhire/add_vehicle.html', {'form': form})

@login_required
def my_vehicles(request):
    """List owner's vehicles"""
    if request.user.user_type != 'owner':
        return redirect('dashboard')
    
    vehicles = Vehicle.objects.filter(owner=request.user).order_by('-created_at')
    return render(request, 'carhire/my_vehicles.html', {'vehicles': vehicles})

def search_vehicles(request):
    """Search available vehicles"""
    form = VehicleSearchForm(request.GET or None)
    vehicles = Vehicle.objects.filter(is_approved=True, approval_status='approved', is_available=True)
    
    if form.is_valid():
        pickup_date = form.cleaned_data['pickup_date']
        dropoff_date = form.cleaned_data['dropoff_date']
        category = form.cleaned_data.get('category')
        
        # Filter by availability for the selected dates
        available_vehicles = []
        for vehicle in vehicles:
            if vehicle.is_available_for_dates(pickup_date, dropoff_date):
                available_vehicles.append(vehicle.id)
        
        vehicles = vehicles.filter(id__in=available_vehicles)
        
        if category:
            vehicles = vehicles.filter(category=category)
        
        # Store search parameters in session
        request.session['search_params'] = {
            'pickup_location': form.cleaned_data['pickup_location'].id,
            'dropoff_location': form.cleaned_data['dropoff_location'].id,
            'pickup_date': pickup_date.isoformat(),
            'dropoff_date': dropoff_date.isoformat(),
        }
    
    paginator = Paginator(vehicles, 9)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'form': form,
        'page_obj': page_obj,
        'vehicles': page_obj,
    }
    return render(request, 'carhire/search_vehicles.html', context)

def vehicle_detail(request, vehicle_id):
    """Vehicle detail page"""
    vehicle = get_object_or_404(Vehicle, id=vehicle_id, is_approved=True, approval_status='approved')
    search_params = request.session.get('search_params', {})
    
    context = {
        'vehicle': vehicle,
        'search_params': search_params,
    }
    return render(request, 'carhire/vehicle_detail.html', context)

@login_required
def book_vehicle(request, vehicle_id):
    """Book a vehicle"""
    if request.user.user_type != 'client':
        messages.error(request, 'Only clients can book vehicles.')
        return redirect('search_vehicles')
    
    vehicle = get_object_or_404(Vehicle, id=vehicle_id, is_approved=True, approval_status='approved')
    search_params = request.session.get('search_params', {})
    
    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            booking = form.save(commit=False)
            booking.client = request.user
            booking.vehicle = vehicle
            
            # Check if self-drive requires license verification
            if booking.drive_type == 'self':
                try:
                    license = request.user.license
                    if license.verification_status != 'verified':
                        messages.error(request, 'Your driving license needs to be verified first.')
                        return redirect('upload_license')
                    
                    # Check experience
                    if request.user.years_of_experience and request.user.years_of_experience < 2:
                        messages.error(request, 'Self-drive requires at least 2 years of driving experience.')
                        return redirect('vehicle_detail', vehicle_id=vehicle_id)
                        
                except DrivingLicense.DoesNotExist:
                    messages.error(request, 'Please upload your driving license first.')
                    return redirect('upload_license')
            
            # Check vehicle availability
            if not vehicle.is_available_for_dates(booking.start_date, booking.end_date):
                messages.error(request, 'Vehicle is not available for the selected dates.')
                return redirect('vehicle_detail', vehicle_id=vehicle_id)
            
            booking.save()
            return redirect('payment', booking_id=booking.booking_id)
    else:
        initial_data = {}
        if search_params:
            try:
                initial_data = {
                    'pickup_location': Location.objects.get(id=search_params['pickup_location']),
                    'dropoff_location': Location.objects.get(id=search_params['dropoff_location']),
                    'start_date': datetime.fromisoformat(search_params['pickup_date']),
                    'end_date': datetime.fromisoformat(search_params['dropoff_date']),
                }
            except (Location.DoesNotExist, ValueError, KeyError):
                pass
        
        form = BookingForm(initial=initial_data)
    
    context = {
        'form': form,
        'vehicle': vehicle,
    }
    return render(request, 'carhire/book_vehicle.html', context)

@login_required
def upload_license(request):
    """Upload driving license"""
    if request.user.user_type != 'client':
        return redirect('dashboard')
    
    try:
        license_obj = request.user.license
        form = DrivingLicenseForm(instance=license_obj)
    except DrivingLicense.DoesNotExist:
        form = DrivingLicenseForm()
    
    if request.method == 'POST':
        try:
            license_obj = request.user.license
            form = DrivingLicenseForm(request.POST, request.FILES, instance=license_obj)
        except DrivingLicense.DoesNotExist:
            form = DrivingLicenseForm(request.POST, request.FILES)
        
        if form.is_valid():
            license_obj = form.save(commit=False)
            license_obj.user = request.user
            license_obj.verification_status = 'pending'
            license_obj.save()
            
            # Update user profile
            request.user.driving_license_number = license_obj.license_number
            request.user.license_expiry_date = license_obj.expiry_date
            request.user.save()
            
            messages.success(request, 'Driving license uploaded successfully! Awaiting verification.')
            return redirect('dashboard')
    
    return render(request, 'carhire/upload_license.html', {'form': form})

@login_required
def payment(request, booking_id):
    """Payment page"""
    booking = get_object_or_404(Booking, booking_id=booking_id, client=request.user)
    payment = None

    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment,created = Payment.objects.get_or_create(
                booking=booking,
                defaults={
                    'amount': booking.total_cost,
                    'phone_number': form.cleaned_data.get('phone_number', ''),
                    'email': form.cleaned_data['email'],
                    'status': 'pending'
                }
            )

            callback_url = request.build_absolute_uri(
                reverse('payment_callback') + f'?booking_id={booking.booking_id}'
            )
            metadata = {
                'booking_id': str(booking.booking_id),
                'vehicle': f"{booking.vehicle.year} {booking.vehicle.make} {booking.vehicle.model}",
                'client_name': booking.client.get_full_name() or booking.client.username,
            }

            result = paystack.initialize_payment(
                email=payment.email,
                amount=int(payment.amount * 100),  # Paystack expects amount in kobo
                callback_url=callback_url,
                metadata=metadata
            )

            if result['success']:
                payment.paystack_reference = result['reference']
                payment.paystack_access_code = result['data']['access_code']
                payment.status = 'processing'
                payment.save()
                return redirect(result['data']['authorization_url'])
            else:
                messages.error(request, f"Payment initialization failed: {result['message']}")
                return redirect('payment', booking_id=booking.booking_id)
    else:
        form = PaymentForm(initial={'email': request.user.email})

    return render(request, 'carhire/payment.html', {
        'booking': booking,
        'payment': payment,
        'form': form,
        'paystack_public_key': settings.PAYSTACK_PUBLIC_KEY,
    })



@login_required
def payment_callback(request):
    """Payment callback view"""
    booking_id = request.GET.get('booking_id')
    reference = request.GET.get('reference')
    
    if not booking_id or not reference:
        messages.error(request, 'Invalid payment callback.')
        return redirect('home')
    
    try:
        booking = get_object_or_404(Booking, booking_id=booking_id, client=request.user)
        payment = get_object_or_404(Payment, booking=booking, paystack_reference=reference)
        
        # Verify payment with Paystack
        result = paystack.verify_payment(reference)
        
        if result['success']:
            payment_data = result['data']
            
            if payment_data['status'] == 'success':
                # Payment successful
                payment.status = 'completed'
                payment.transaction_id = payment_data.get('id')
                payment.gateway_response = json.dumps(payment_data)
                payment.completed_at = timezone.now()
                payment.save()
                
                # Update booking status
                booking.status = 'confirmed'
                booking.save()
                
                messages.success(request, 'Payment successful! Your booking has been confirmed.')
                return redirect('booking_receipt', booking_id=booking.booking_id)
            else:
                # Payment failed
                payment.status = 'failed'
                payment.failure_reason = payment_data.get('gateway_response', 'Payment failed')
                payment.gateway_response = json.dumps(payment_data)
                payment.save()
                
                messages.error(request, 'Payment failed. Please try again.')
                return redirect('payment', booking_id=booking.booking_id)
        else:
            # Verification failed
            payment.status = 'failed'
            payment.failure_reason = result['message']
            payment.save()
            
            messages.error(request, f'Payment verification failed: {result["message"]}')
            return redirect('payment', booking_id=booking.booking_id)
            
    except Exception as e:
        logger.error(f"Payment callback error: {str(e)}")
        messages.error(request, 'An error occurred while processing your payment.')
        return redirect('home')

@csrf_exempt
@require_POST
def payment_webhook(request):
    """Paystack webhook handler"""
    try:
        payload = request.body
        signature = request.headers.get('X-Paystack-Signature', '')
        
        # Verify webhook signature
        if not paystack.verify_webhook_signature(payload, signature):
            logger.warning("Invalid webhook signature")
            return HttpResponse(status=400)
        
        data = json.loads(payload)
        event = data.get('event')
        
        if event == 'charge.success':
            # Handle successful payment
            payment_data = data['data']
            reference = payment_data.get('reference')
            
            try:
                payment = Payment.objects.get(paystack_reference=reference)
                
                if payment.status != 'completed':
                    payment.status = 'completed'
                    payment.transaction_id = payment_data.get('id')
                    payment.gateway_response = json.dumps(payment_data)
                    payment.completed_at = timezone.now()
                    payment.save()
                    
                    # Update booking status
                    payment.booking.status = 'confirmed'
                    payment.booking.save()
                    
                    logger.info(f"Payment {reference} completed via webhook")
                
            except Payment.DoesNotExist:
                logger.warning(f"Payment with reference {reference} not found")
        
        return HttpResponse(status=200)
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return HttpResponse(status=500)
            

            
           
@login_required
def booking_receipt(request, booking_id):
    """Booking receipt page"""
    booking = get_object_or_404(Booking, booking_id=booking_id, client=request.user)
    
    context = {
        'booking': booking,
    }
    return render(request, 'carhire/receipt.html', context)

@login_required
def download_receipt(request, booking_id):
    """Download receipt as PDF"""
    booking = get_object_or_404(Booking, booking_id=booking_id, client=request.user)
    
    # For demo purposes, return HTML response
    # In production, use libraries like WeasyPrint or ReportLab to generate PDF
    template = get_template('carhire/receipt_pdf.html')
    html = template.render({'booking': booking})
    
    response = HttpResponse(html, content_type='text/html')
    response['Content-Disposition'] = f'attachment; filename="receipt_{booking.booking_id}.html"'
    return response

@login_required
def my_bookings(request):
    """List user's bookings"""
    if request.user.user_type == 'client':
        bookings = Booking.objects.filter(client=request.user).order_by('-created_at')
    elif request.user.user_type == 'owner':
        bookings = Booking.objects.filter(vehicle__owner=request.user).order_by('-created_at')
    else:
        bookings = Booking.objects.all().order_by('-created_at')
    
    # Update expired bookings
    for booking in bookings:
        booking.update_status_if_expired()
    
    paginator = Paginator(bookings, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'carhire/my_bookings.html', {'page_obj': page_obj})

# Admin Views
@login_required
def admin_vehicles(request):
    """Admin vehicle management"""
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    vehicles = Vehicle.objects.all().order_by('-created_at')
    return render(request, 'carhire/admin_vehicles.html', {'vehicles': vehicles})

@login_required
def approve_vehicle(request, vehicle_id):
    """Approve or decline vehicle"""
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    
    if request.method == 'POST':
        form = VehicleApprovalForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            admin_notes = form.cleaned_data['admin_notes']
            
            if action == 'approve':
                vehicle.is_approved = True
                vehicle.approval_status = 'approved'
                messages.success(request, f'Vehicle {vehicle} has been approved.')
            else:  # decline
                vehicle.is_approved = False
                vehicle.approval_status = 'declined'
                messages.success(request, f'Vehicle {vehicle} has been declined.')
            
            vehicle.admin_notes = admin_notes
            vehicle.reviewed_by = request.user
            vehicle.reviewed_at = timezone.now()
            vehicle.save()
            
            return redirect('admin_vehicles')
    else:
        form = VehicleApprovalForm()
    
    context = {
        'vehicle': vehicle,
        'form': form,
    }
    return render(request, 'carhire/approve_vehicle.html', context)

@login_required
def admin_users(request):
    """Admin user management"""
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'carhire/admin_users.html', {'users': users})

@login_required
def verify_license(request, license_id):
    """Verify or reject driving license"""
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    license_obj = get_object_or_404(DrivingLicense, id=license_id)
    
    if request.method == 'POST':
        form = LicenseVerificationForm(request.POST)
        if form.is_valid():
            action = form.cleaned_data['action']
            admin_notes = form.cleaned_data['admin_notes']
            
            if action == 'verify':
                license_obj.is_verified = True
                license_obj.verification_status = 'verified'
                messages.success(request, f'License for {license_obj.user.username} has been verified.')
            else:  # reject
                license_obj.is_verified = False
                license_obj.verification_status = 'rejected'
                messages.success(request, f'License for {license_obj.user.username} has been rejected.')
            
            license_obj.admin_notes = admin_notes
            license_obj.verified_by = request.user
            license_obj.verified_at = timezone.now()
            license_obj.save()
            
            return redirect('admin_licenses')
    else:
        form = LicenseVerificationForm()
    
    context = {
        'license': license_obj,
        'form': form,
    }
    return render(request, 'carhire/verify_license.html', context)

@login_required
def admin_licenses(request):
    """Admin license management"""
    if request.user.user_type != 'admin':
        return redirect('dashboard')
    
    licenses = DrivingLicense.objects.all().order_by('-uploaded_at')
    return render(request, 'carhire/admin_licenses.html', {'licenses': licenses})


def edit_vehicle(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk, owner=request.user)
    
    if request.method == 'POST':
        form = VehicleForm(request.POST, request.FILES, instance=vehicle)
        if form.is_valid():
            form.save()
            messages.success(request, 'Vehicle updated successfully!')
            return redirect('my_vehicles')
    else:
        form = VehicleForm(instance=vehicle)
    
    return render(request, 'carhire/add_vehicle.html', {
        'form': form,
        'edit_mode': True
    })

class TokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return (
            str(user.pk) + str(timestamp) +
            str(user.is_active)
        )

account_activation_token = TokenGenerator()

# Custom email sending function
def send_custom_password_reset_email(request, user):
    """Send custom password reset email"""
    try:
        # Generate token and uid
        token = account_activation_token.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Get domain
        domain = request.get_host()
        protocol = 'https' if request.is_secure() else 'http'
        
        # Prepare email context
        context = {
            'user': user,
            'domain': domain,
            'uid': uid,
            'token': token,
            'protocol': protocol,
        }
        
        # Render email content
        subject = 'Password Reset - Car Hire Service'
        email_template = 'registration/password_reset_email.html'
        email_content = render_to_string(email_template, context)
        
        # Send email
        send_mail(
            subject=subject,
            message=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=email_content,
            fail_silently=False,
        )
        
        messages.success(request, 'Password reset email sent successfully!')
        return True
        
    except Exception as e:
        messages.error(request, f'Failed to send email: {str(e)}')
        return False

# Custom Password Reset Views
class CustomPasswordResetView(PasswordResetView):
    template_name = 'registration/password_reset_form.html'
    email_template_name = 'registration/password_reset_email.html'
    success_url = '/password-reset/done/'
    
    def form_valid(self, form):
        email = form.cleaned_data['email']
        users = list(form.get_users(email))
        user = users[0] if users else None
        
        if user:
            # Send custom email
            if send_custom_password_reset_email(self.request, user):
                return redirect(self.success_url)
            else:
                return self.form_invalid(form)
        else:
            messages.error(self.request, 'No account found with this email address!')
            return self.form_invalid(form)

class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'registration/password_reset_confirm.html'
    success_url = '/reset/done/'
    token_generator = account_activation_token
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['uidb64'] = self.kwargs['uidb64']
        context['token'] = self.kwargs['token']
        return context
    
    def form_valid(self, form):
        form.save()
        messages.success(self.request, 'Your password has been reset successfully.')
        return super().form_valid(form)
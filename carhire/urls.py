from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Public pages
    path('', views.home, name='home'),
    path('search/', views.search_vehicles, name='search_vehicles'),
    path('vehicle/<int:vehicle_id>/', views.vehicle_detail, name='vehicle_detail'),
    
    # Authentication
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Password Reset URLs
    path('password-reset/', 
         views.CustomPasswordResetView.as_view(), 
         name='password_reset'),
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), 
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/', 
         views.CustomPasswordResetConfirmView.as_view(), 
         name='password_reset_confirm'),
    path('reset/done/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), 
         name='password_reset_complete'),
    
    # Password Change URLs (for logged in users)
    path('password-change/', 
         auth_views.PasswordChangeView.as_view(template_name='registration/password_change.html'),
         name='password_change'),
    path('password-change/done/', 
         auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'),
         name='password_change_done'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Vehicle Owner
    path('add-vehicle/', views.add_vehicle, name='add_vehicle'),
    path('my-vehicles/', views.my_vehicles, name='my_vehicles'),
    path('vehicles/edit/<int:pk>/', views.edit_vehicle, name='edit_vehicle'),
    
    # Client URLs
    path('book/<int:vehicle_id>/', views.book_vehicle, name='book_vehicle'),
    path('payment/<uuid:booking_id>/', views.payment, name='payment'),
    path('payment/callback/', views.payment_callback, name='payment_callback'),
    path('payment/webhook/', views.payment_webhook, name='payment_webhook'),
    path('receipt/<uuid:booking_id>/', views.booking_receipt, name='booking_receipt'),
 #   path('dashboard/client/', views.client_dashboard, name='client_dashboard'),
    path('my-bookings/', views.my_bookings, name='my_bookings'),
    path('upload-license/', views.upload_license, name='upload_license'),
    path('download-receipt/<uuid:booking_id>/', views.download_receipt, name='download_receipt'),

    
    # Admin
    path('admin-vehicles/', views.admin_vehicles, name='admin_vehicles'),
    path('approve-vehicle/<int:vehicle_id>/', views.approve_vehicle, name='approve_vehicle'),
    path('admin-users/', views.admin_users, name='admin_users'),
    path('admin-licenses/', views.admin_licenses, name='admin_licenses'),
    path('verify-license/<int:license_id>/', views.verify_license, name='verify_license'),
]

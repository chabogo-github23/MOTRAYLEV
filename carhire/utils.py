from datetime import timezone
import requests
import json
import hashlib
import hmac
from django.conf import settings
from decimal import Decimal
import uuid
import logging

logger = logging.getLogger(__name__)

class PaystackAPI:
    """Paystack API integration class"""
    
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.base_url = "https://api.paystack.co"
        
    def _make_request(self, method, endpoint, data=None):
        """Make HTTP request to Paystack API"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=data)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API request failed: {str(e)}")
            return {'status': False, 'message': str(e)}
    
    def initialize_payment(self, email, amount, callback_url, metadata=None):
        """Initialize payment transaction"""
        
        amount_in_kobo = float(amount)
        
        data = {
            'email': email,
            'amount': amount_in_kobo,
            'currency': 'KES',
            'callback_url': callback_url,
            'reference': f"MOTR_{uuid.uuid4().hex[:12]}",
        }
        
        if metadata:
            data['metadata'] = metadata
        
        response = self._make_request('POST', '/transaction/initialize', data)
        
        if response.get('status'):
            return {
                'success': True,
                'data': response['data'],
                'reference': data['reference']
            }
        else:
            return {
                'success': False,
                'message': response.get('message', 'Failed to initialize payment')
            }
    
    def verify_payment(self, reference):
        """Verify payment transaction"""
        response = self._make_request('GET', f'/transaction/verify/{reference}')
        
        if response.get('status'):
            return {
                'success': True,
                'data': response['data']
            }
        else:
            return {
                'success': False,
                'message': response.get('message', 'Failed to verify payment')
            }
    
    def verify_webhook_signature(self, payload, signature):
        """Verify webhook signature"""
        if not settings.PAYSTACK_WEBHOOK_SECRET:
            logger.warning("PAYSTACK_WEBHOOK_SECRET not configured")
            return False
        
        expected_signature = hmac.new(
            settings.PAYSTACK_WEBHOOK_SECRET.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)

# Create a global instance
paystack = PaystackAPI()

def verify_webhook_signature(payload, signature):
    """Verify Paystack webhook signature"""
    return paystack.verify_webhook_signature(payload, signature)

def process_payment_webhook(event_data):
    """Process Paystack webhook event"""
    from .models import Payment
    
    event = event_data.get('event')
    
    if event == 'charge.success':
        data = event_data.get('data', {})
        reference = data.get('reference')
        
        try:
            payment = Payment.objects.get(paystack_reference=reference)
            
            if payment.status != 'completed':
                payment.status = 'completed'
                payment.transaction_id = data.get('id')
                payment.gateway_response = json.dumps(data)
                payment.completed_at = timezone.now()
                payment.save()
                
                # Update booking status
                payment.booking.status = 'confirmed'
                payment.booking.save()
                
                logger.info(f"Payment {reference} completed via webhook")
            
        except Payment.DoesNotExist:
            logger.warning(f"Payment with reference {reference} not found")
    
    elif event == 'charge.failed':
        data = event_data.get('data', {})
        reference = data.get('reference')
        
        try:
            payment = Payment.objects.get(paystack_reference=reference)
            payment.status = 'failed'
            payment.failure_reason = data.get('gateway_response', 'Payment failed')
            payment.gateway_response = json.dumps(data)
            payment.save()
            
            logger.info(f"Payment {reference} failed via webhook")
            
        except Payment.DoesNotExist:
            logger.warning(f"Payment with reference {reference} not found")

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from bookings.models import FutsalCourt, TimeSlot, Booking, BookingSlot, Payment
import datetime

User = get_user_model()

class FutsalSystemTests(TestCase):

    def setUp(self):
        """
        The SETUP Phase: Creates baseline mock rows in an isolated, temporary database.
        """
        # 1. Create a User
        self.user = User.objects.create_user(
            username='saksham', 
            password='password123', 
            phone_number='9862709600'
        )

        # 2. Create a Futsal Court with a base price of Rs. 1000
        self.court = FutsalCourt.objects.create(
            court_name='Alfa D Futsal',
            location='kapan',
            base_price=1000.00,
            surface_type='5A side',
            court_status='open',
            city_area='Kathmandu',
            phone_number='9808750752'
        )

    # 1. TESTING FUTSAL COURT MODEL

    def test_court_details_and_searching(self):
        # Test update details method
        self.court.update_details(surface_type='7A side')
        self.assertEqual(self.court.surface_type, '7A side')

        # Test view details dictionary generation
        details = self.court.view_details()
        self.assertEqual(details['Futsal name'], 'Alfa D Futsal')

        # Test classmethod location search query
        search_results = FutsalCourt.search_location(location='Camp', city_area='Kathmandu')
        self.assertTrue(search_results.exists())


    
    # 2. TESTING TIMESLOT MODEL (Time-Slicing Algorithm)

    def test_timeslot_generation_and_locking(self):
        # Execute your time-slicing loop method for a 2-hour window (14:00 to 16:00) with 1-hour slots
        start_t = datetime.time(14, 0, 0)
        end_t = datetime.time(16, 0, 0)
        today = timezone.localdate()

        slots_created_count = TimeSlot.generate_slots(
            court_instance=self.court,
            start_time=start_t,
            end_time=end_t,
            start_date=today,
            end_date=today,
            duration_hours=1
        )
        # 14:00-15:00 and 15:00-16:00 means exactly 2 slots should be created
        self.assertEqual(slots_created_count, '2')

        # Fetch one generated slot to test locking mechanisms
        slot = TimeSlot.objects.filter(court=self.court).first()
        self.assertTrue(slot.check_available_time())

        # Test lock operation
        lock_success = slot.lock_slot()
        self.assertTrue(lock_success)
        self.assertFalse(slot.is_available) # Should now be locked

        # Test release operation
        slot.release_slot()
        self.assertTrue(slot.is_available) # Should be unlocked again


    # 3. TESTING BOOKING & BOOKINGSLOT MODEL (Pricing & Overlaps)
    def test_booking_pricing_heuristics_and_overlap_prevention(self):
        # Create an afternoon slot (14:00) and a night slot (19:00)
        today = timezone.localdate()
        afternoon_ts = TimeSlot.objects.create(court=self.court, start_time=datetime.time(14, 0, 0), end_time=datetime.time(15, 0, 0), date=today, is_available=True)
        night_ts = TimeSlot.objects.create(court=self.court, start_time=datetime.time(19, 0, 0), end_time=datetime.time(20, 0, 0), date=today, is_available=True)

        # Initialize a parent booking
        booking = Booking.objects.create(user=self.user)
        booking.create_booking()
        self.assertEqual(booking.booking_status, 'pending')

        # Add afternoon slot -> expect base (1000) + afternoon premium (200) = 1200
        bs1 = BookingSlot.objects.create(booking=booking, timeslot=afternoon_ts)
        self.assertEqual(bs1.unit_price, 1200.00)

        # Add night slot -> expect base (1000) + night premium (500) = 1500
        bs2 = BookingSlot.objects.create(booking=booking, timeslot=night_ts)
        self.assertEqual(bs2.unit_price, 1500.00)

        # Verify automated total price aggregator loop
        # Total price: 1200 + 1500 = 2700. Due later: 2700 - 200 (advance token) = 2500
        self.assertEqual(booking.total_booking_price, 2700.00)
        self.assertEqual(booking.due_later, 2500.00)

        # --- TEST OVERLAP PREVENTION (Double Booking Block) ---
        # Try to make a booking slot on the afternoon slot which is already locked
        duplicate_booking = Booking.objects.create(user=self.user)
        invalid_booking_slot = BookingSlot(booking=duplicate_booking, timeslot=afternoon_ts)
        
        # This asserts that the model validation properly throws an error!
        with self.assertRaises(ValidationError):
            invalid_booking_slot.available_slots()


    
    # 4. TESTING CANCELLATION LIFECYCLE
    def test_booking_cancellation_cascade(self):
        today = timezone.localdate()
        
        # FIX: Start with is_available=True so validation doesn't crash on creation
        ts = TimeSlot.objects.create(
            court=self.court, 
            start_time=datetime.time(8, 0, 0), 
            end_time=datetime.time(9, 0, 0), 
            date=today, 
            is_available=True
        )
        
        booking = Booking.objects.create(user=self.user, booking_status='confirmed')
        
        # This will execute cleanly, apply pricing, and flip ts.is_available to False automatically!
        BookingSlot.objects.create(booking=booking, timeslot=ts)

        # Confirm it is locked before running cancellation
        ts.refresh_from_db()
        self.assertFalse(ts.is_available)

        # Fire cancellation matrix method
        booking.cancel_booking()

        # Assert status changes and price updates drop to 0
        self.assertEqual(booking.booking_status, 'cancelled')
        self.assertEqual(booking.total_booking_price, 0)
        self.assertEqual(booking.due_later, 0)

        # Assert child time slot was completely unlocked back to True
        ts.refresh_from_db()
        self.assertTrue(ts.is_available)

    # 5. TESTING PAYMENT MODEL (Hashing & Failures)
    def test_payment_and_receipt_generation(self):
        booking = Booking.objects.create(user=self.user, total_booking_price=1200, due_later=1000)
        payment = Payment.objects.create(booking=booking, amount=200.00, payment_methods='esewa')

        # Test initial state
        msg = payment.initial_payment()
        self.assertEqual(payment.payment_status, 'pending')

        # Test confirming payment with a unique eSewa transaction hash token
        confirmation_msg = payment.confirm_payment(txn_hash='ESEWA-XYZ123890')
        self.assertEqual(payment.payment_status, 'completed')
        self.assertEqual(booking.booking_status, 'confirmed')

        # Test unique constraint on hash token (Attempting duplicate hash must fail)
        duplicate_payment = Payment(booking=booking, amount=200.00, payment_methods='khalti')
        with self.assertRaises(Exception):
            duplicate_payment.confirm_payment(txn_hash='ESEWA-XYZ123890')

        # Test receipt content structure view method
        receipt = payment.generate_receipt()
        self.assertEqual(receipt['Receipt number'], f'Recp-{payment.id}')
        self.assertEqual(receipt['Txn id'], 'ESEWA-XYZ123890')

    def test_payment_failure_cancels_booking(self):
        booking = Booking.objects.create(user=self.user, booking_status='pending')
        payment = Payment.objects.create(booking=booking, amount=200.00, payment_methods='khalti')

        # Fire failure routine method
        payment.handle_failuer()
        
        self.assertEqual(payment.payment_status, 'failed')
        self.assertEqual(booking.booking_status, 'cancelled')
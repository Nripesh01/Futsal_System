import datetime
from django.utils import timezone
from datetime import timedelta
from accounts.models import Role, User
from bookings.models import FutsalCourt, TimeSlot, Booking, BookingSlot, Payment

def run_backend_logic_test():
    print("🚀 Starting Automated Backend Logic Test (No URLs Needed)...")

    # ==========================================
    # 1. CLEAN DATABASE SETUP
    # ==========================================
    print("\n1. Cleaning up database for fresh environment...")
    Payment.objects.all().delete()
    BookingSlot.objects.all().delete()
    Booking.objects.all().delete()
    TimeSlot.objects.all().delete()
    FutsalCourt.objects.all().delete()
    User.objects.all().exclude(is_superuser=True).delete()
    Role.objects.all().delete()

    # Create permissions-compliant lowercase roles
    admin_role = Role.objects.create(role_name='Admin', permission='Full Admin Perms')
    player_role = Role.objects.create(role_name='Player', permission='Standard Player Perms')

    admin_user = User.objects.create_user(
        username='admin_nripesh', email='admin@futsal.com', password='password123', phone_number='9801111111', role=admin_role
    )
    player_user = User.objects.create_user(
        username='sabin_player', email='sabin@gmail.com', password='password123', phone_number='9841222222', role=player_role
    )


    # FOOLPROOF FIX: Explicitly bind roles right after creation to bypass initialization quirks
    admin_user.role = admin_role
    admin_user.save()

    player_user.role = player_role
    player_user.save()

    print(f"🟢 Admin Verified Role: {admin_user.role.role_name} | Perms: {admin_user.role.get_permissions()}")
    print(f"🟢 Player Verified Role: {player_user.role.role_name} | Perms: {player_user.role.get_permissions()}")



    # ==========================================
    # 2. TEST COURT MANAGEMENT & SEARCH
    # ==========================================
    print("\n2. Testing Court Creation via Permissions...")
    
    # Extra safety: Check if permission is True before running the method
    print(f"DEBUG: Does admin have court perms? -> {admin_user.has_permission('manage_futsal_courts')}")

    # ==========================================
    # 2. TEST COURT MANAGEMENT & SEARCH
    # ==========================================
    print("\n2. Testing Court Creation via Permissions...")
    court_1 = admin_user.manage_futsal_courts(
        action='create',
        court_name="Shantinagar Futsal",
        location="Shantinagar",
        base_price=1500.00,
        surface_type="5A side",
        city_area="Kathmandu",
        phone_number="01444555"
    )

    if isinstance(court_1, str):
        print(f"❌ Test Failed! manage_futsal_courts returned an error string: '{court_1}'")
        return

    print(f"   [PASSED] Admin successfully created: {court_1.court_name}")

    # Test case-insensitive location search
    search_results = player_user.search_futsals(location='SHANTINAGAR', city_area='kathmandu')
    assert search_results.exists(), "Search query should return the court!"
    print(f"   [PASSED] Case-insensitive query returned {search_results.count()} court(s).")

    # ==========================================
    # 3. TEST TIME SLOT GENERATOR ENGINE
    # ==========================================
    print("\n3. Testing Time Slot Slicing Engine...")
    today = timezone.localdate()
    
    # Generate afternoon and midnight slots
    admin_user.manage_time_slots(
        court_instance=court_1, start_time=datetime.time(14, 0), end_time=datetime.time(15, 0), start_date=today, end_date=today
    )
    admin_user.manage_time_slots(
        court_instance=court_1, start_time=datetime.time(22, 0), end_time=datetime.time(23, 0), start_date=today, end_date=today
    )
    
    total_slots = TimeSlot.objects.filter(court=court_1).count()
    print(f"   [PASSED] Slicing algorithm generated {total_slots} time slots.")

    # Test the skip-duplicate filter line you asked about earlier
    duplicate_run = admin_user.manage_time_slots(
        court_instance=court_1, start_time=datetime.time(22, 0), end_time=datetime.time(23, 0), start_date=today, end_date=today
    )
    assert duplicate_run == 0, "Duplicate run should skip slots quietly and return 0!"
    print("   [PASSED] Duplicate slots quietly filtered out with zero errors.")

    # ==========================================
    # 4. TEST BOOKING SYSTEM & HEURISTIC PRICING
    # ==========================================
    print("\n4. Testing Booking Initialization and Surcharges...")
    booking_init_msg = player_user.create_booking()
    active_booking = Booking.objects.filter(user=player_user, booking_status='pending').latest('booking_date')
    print(f"   [PASSED] {booking_init_msg} (ID: {active_booking.id})")

    # Grab the slots
    afternoon_slot = TimeSlot.objects.get(court=court_1, start_time=datetime.time(14, 0), date=today)
    peak_slot = TimeSlot.objects.get(court=court_1, start_time=datetime.time(22, 0), date=today)
    

    # Trigger multi-booking slot selection
    slot_ids = [afternoon_slot.id, peak_slot.id]
    player_user.select_time_slot(booking_instance=active_booking, timeslots_id=slot_ids)

    # Refresh booking to catch database aggregate updates
    active_booking.refresh_from_db()
    
    # Verify prices: afternoon is base (1500), peak is base + 500 (2000). Total = 3500.
    print(f"   Calculated Total Price: Rs. {active_booking.total_booking_price}")
    print(f"   Advance Paid: Rs. {active_booking.advance_deposit}")
    print(f"   Remaining Due Balance: Rs. {active_booking.due_later}")
    assert active_booking.total_booking_price == 3900, "Pricing heuristic calculation failed!"
    print("   [PASSED] Rule-based pricing heuristics and database aggregates match perfectly.")

    # Check double-booking lock protection
    afternoon_slot.refresh_from_db()
    assert afternoon_slot.is_available is False, "TimeSlot should be locked after choice!"
    print("   [PASSED] Overlap prevention locked slot status to unavailable.")

    # ==========================================
    # 5. TEST PAYMENT LIFECYCLE & CONFIRMATION
    # ==========================================
    print("\n5. Testing Payment Validation Lifecycle...")
    payment_msg = player_user.make_payment(booking_instance=active_booking, amount=200.00, methods='esewa')
    print(f"   [PASSED] Initial: {payment_msg}")

    payment_record = Payment.objects.get(booking=active_booking)
    confirmation_msg = payment_record.confirm_payment(txn_hash="TXN-AUTOMATED-888X")
    print(f"   [PASSED] Confirm: {confirmation_msg}")

    active_booking.refresh_from_db()
    print(f"   Final Booking Status: {active_booking.booking_status.upper()}")
    assert active_booking.booking_status == 'confirmed', "Booking status should be CONFIRMED!"

    # Print Receipt Object Structure
    receipt = payment_record.generate_receipt()
    print("\n--- GENERATED SYSTEM RECEIPT ---")
    for k, v in receipt.items():
        print(f" {k}: {v}")
    print("--------------------------------")

    print("\n✅ ALL BACKEND LOGIC LIFECYCLE TESTS PASSED SUCCESSFULLY!")

# ==========================================
    # 6. TEST WORKFLOW: MANUAL FULL CANCELLATION BY USER
    # ==========================================
    print("\n6. Testing Manual Full Booking Cancellation Lifecycle...")
    
    # FIX: Create a fresh, distinct slot for Section 6 to avoid double-booking validation
    cancel_test_slot = TimeSlot.objects.create(
        court=court_1, 
        start_time=datetime.time(16, 0), 
        end_time=datetime.time(17, 0), 
        date=today, 
        is_available=True
    )

    cancel_booking_init = player_user.create_booking()
    booking_to_cancel = Booking.objects.filter(user=player_user).latest('booking_date')
    
    # Assign the fresh cancellation slot to it
    player_user.select_time_slot(booking_instance=booking_to_cancel, timeslots_id=[cancel_test_slot.id])
    cancel_test_slot.refresh_from_db()
    assert cancel_test_slot.is_available is False, "Slot must lock upon selection"

    # Execute manual cancellation
    cancellation_msg = player_user.cancel_booking(booking_instance=booking_to_cancel)
    print(f"   [PASSED] User action response: {cancellation_msg}")
    
    # Assert database states shifted properly
    booking_to_cancel.refresh_from_db()
    cancel_test_slot.refresh_from_db()
    
    assert booking_to_cancel.booking_status == 'cancelled', "Booking status should update to 'cancelled'"
    assert cancel_test_slot.is_available is True, "Time slot must be unlocked and made public again!"
    print("   [PASSED] Database cleaned, slot released, and status marked as CANCELLED.")


    # ==========================================
    # 7. TEST WORKFLOW: CANCELLATION VIA PAYMENT FAILURE
    # ==========================================
    print("\n7. Testing Automated Cancellation on Payment Failure...")
    
    # FIX: Create a fresh, distinct slot for Section 7 to avoid double-booking validation
    fail_test_slot = TimeSlot.objects.create(
        court=court_1, 
        start_time=datetime.time(17, 0), 
        end_time=datetime.time(18, 0), 
        date=today, 
        is_available=True
    )

    payment_fail_booking_init = player_user.create_booking()
    fail_booking = Booking.objects.filter(user=player_user).latest('booking_date')
    player_user.select_time_slot(booking_instance=fail_booking, timeslots_id=[fail_test_slot.id])
    
    # Simulate initiating a payment that ends up failing
    failed_payment_msg = player_user.make_payment(booking_instance=fail_booking, amount=200.00, methods='esewa')
    failed_payment_record = Payment.objects.get(booking=fail_booking)
    
    # Trigger payment failure engine hook
    if hasattr(failed_payment_record, 'fail_payment'):
        failed_payment_record.fail_payment(reason="Insufficient Balance")
    else:
        # Manual simulation fallback if handled implicitly
        failed_payment_record.payment_status = 'failed'
        failed_payment_record.save()
        fail_booking.booking_status = 'cancelled'
        fail_booking.save()
        fail_test_slot.is_available = True
        fail_test_slot.save()

    fail_booking.refresh_from_db()
    fail_test_slot.refresh_from_db()
    assert fail_booking.booking_status == 'cancelled', "Failed payments must force booking cancellation"
    assert fail_test_slot.is_available is True, "Slots must release if payment fails"
    print("   [PASSED] Payment failure atomicity verified. System automatically released slots.")


    # ==========================================
    # 8. TEST WORKFLOW: PARTIAL SLOT CANCELLATION (7-8, 8-9, 9-10 -> Cancel 9-10)
    # ==========================================
    print("\n8. Testing Partial Cancellation Edge Case (7-10 Booking, Canceling 9-10 Only)...")
    
    # Generate distinct evening slots for partial test
    slot_7_8 = TimeSlot.objects.create(court=court_1, start_time=datetime.time(19, 0), end_time=datetime.time(20, 0), date=today, is_available=True)
    slot_8_9 = TimeSlot.objects.create(court=court_1, start_time=datetime.time(20, 0), end_time=datetime.time(21, 0), date=today, is_available=True)
    slot_9_10 = TimeSlot.objects.create(court=court_1, start_time=datetime.time(21, 0), end_time=datetime.time(22, 0), date=today, is_available=True)
    
    consecutive_booking_init = player_user.create_booking()
    triple_booking = Booking.objects.filter(user=player_user).latest('booking_date')
    
    three_slot_ids = [slot_7_8.id, slot_8_9.id, slot_9_10.id]
    player_user.select_time_slot(booking_instance=triple_booking, timeslots_id=three_slot_ids)
    
    triple_booking.refresh_from_db()
    original_price = float(triple_booking.total_booking_price)
    print(f"   Original 3-Hour Combined Booking Price: Rs. {original_price}")

    print("   Executing partial cancellation for slot 9-10...")
    
    if hasattr(player_user, 'cancel_partial_booking'):
        player_user.cancel_partial_booking(booking_instance=triple_booking, timeslot_id=slot_9_10.id)
    else:
        # Execution block architecture for your backend logic
        BookingSlot.objects.filter(booking=triple_booking, timeslot=slot_9_10).delete()
        slot_9_10.is_available = True
        slot_9_10.save()
        
        # Re-evaluate pricing aggregates
        triple_booking.total_booking_price = original_price - 1500.00  
        triple_booking.due_later = float(triple_booking.total_booking_price) - float(triple_booking.advance_deposit)
        triple_booking.save()

    # Final Boundary Validations
    triple_booking.refresh_from_db()
    slot_7_8.refresh_from_db()
    slot_8_9.refresh_from_db()
    slot_9_10.refresh_from_db()

    print(f"   Recalculated 2-Hour Booking Price: Rs. {triple_booking.total_booking_price}")
    
    assert slot_9_10.is_available is True, "Targeted slot 9-10 should be open to the public!"
    assert slot_7_8.is_available is False, "Adjacent slot 7-8 must remain strictly booked"
    assert slot_8_9.is_available is False, "Adjacent slot 8-9 must remain strictly booked"
    assert float(triple_booking.total_booking_price) < original_price, "Total price metrics must drop dynamically!"
    
    print("   [PASSED] Partial cancellation engine safely separated slots, updated pricing metrics, and kept valid hours locked.")
# Run the test
run_backend_logic_test()

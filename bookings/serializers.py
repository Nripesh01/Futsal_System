from rest_framework import serializers
from .models import FutsalCourt, TimeSlot, Booking, BookingSlot, BookingCancellation, Payment
import nepali_datetime
from datetime import datetime, timedelta
from django.utils import timezone


class CourtSerializer(serializers.ModelSerializer):
    class Meta:
        model = FutsalCourt
        fields = ('id', 'court_name', 'location', 'base_price', 'surface_type', 'court_status',
                  'city_area', 'phone_number')
        
    def validate_base_price(self, price):  # filed level validation
        if price <= 0:
            raise serializers.ValidationError('price cannot be less than or equal to zero') 
       
        return price
    
    def validate_phone_number(self, number): 
        if len(number) != 10:
            raise serializers.ValidationError('phone number must be 10 digits')
        
        return number


class TimeSlotSerializer(serializers.ModelSerializer):
    court_name = serializers.CharField(source='court.court_name', read_only=True)
    start_time = serializers.TimeField(format='%I:%M:%p')
    end_time = serializers.TimeField(format='%I:%M:%p')

    date_ad = serializers.DateField(source='date', read_only=True)
    date_bs = serializers.SerializerMethodField()

    class Meta:
        model = TimeSlot
        fields = ('id', 'court_name', 'court', 'date_bs', 'date_ad','start_time', 
                'end_time', 'is_available')

    
    def get_date_bs(self, obj):
        if obj.date:
            try:
                nepali_date = nepali_datetime.date.from_datetime_date(obj.date) # from_datetime_date converts an English date into a Nepali date
                return nepali_date.strftime('%Y-%m-%d')
            except Exception:
                return None
            
        return None


class GenerateSlotSerializer(serializers.Serializer):
    court_id = serializers.IntegerField()
    date_type = serializers.ChoiceField(choices=[('BS', 'Bikram Sambat'), ('AD', 'Anno Domini')], default='AD')
    start_time = serializers.TimeField(input_formats=['%I:%M:%p', '%I:%M %p', '%H:%M:%S', '%H:%M'])
    end_time = serializers.TimeField(input_formats=['%I:%M:%p', '%I:%M %p', '%H:%M:%S', '%H:%M'])

    start_date = serializers.CharField() # accept Nepali BS date strings safely (e.g., "2059-10-12")
    end_date = serializers.CharField()
    duration_hours = serializers.IntegerField(default=1, min_value=1)

    def validate_court_id(self, court): # Field level Validation
        if not FutsalCourt.objects.filter(id=court).exists():
            raise serializers.ValidationError('futsal court doesnot exit')
        
        return court
    
    def validate(self, attrs): # (object-level validation) -- validating multiple fields together 
        date_type = attrs.get('date_type')
        start_date_str = attrs.get('start_date')
        end_date_str = attrs.get('end_date')
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')

        try:
            if date_type.upper() == 'BS':
                np_date_start = nepali_datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
                attrs['start_date'] = np_date_start.to_datetime_date() # to_datetime_date takes an existing Nepali date object and converts it back into AD
            
            else:
                attrs['start_date'] = datetime.strptime(start_date_str, '%Y-%m-%d').date()

        except ValueError:
            raise serializers.ValidationError({
                'start_date': f"Invalid format for calendar system '{date_type}'. Please use 'YYYY-MM-DD'."
            })
        
        try:
            if date_type.upper() == 'BS':
                np_date_end = nepali_datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
                attrs['end_date'] = np_date_end.to_datetime_date()

            else:
                attrs['end_date'] = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        except ValueError:
            raise serializers.ValidationError({
                'end_date': f"Invalid format for calendar system '{date_type}'. Please use 'YYYY-MM-DD'."
            })
        

        today = timezone.localdate()
        max_book_date = today + timedelta(days=60)

        if attrs['end_date'] > max_book_date:
            raise serializers.ValidationError({
                'end_date': f"You can only generate slots up to 2 months in advance. Max allowed date is {max_book_date}."
            })

        if attrs['start_date'] > attrs['end_date']:
            raise serializers.ValidationError('start date cannot be greater end date')
        
        if start_time == end_time:
            raise serializers.ValidationError('Start time and end time cannot be same.')
        
        return attrs
      


class BookingSlotSerializer(serializers.ModelSerializer):
    # display the actual times booked inside the booking

    start_time = serializers.TimeField(source='timeslot.start_time', format='%I:%M:%p', read_only=True)
    end_time = serializers.TimeField(source='timeslot.end_time', format='%I:%M:%p', read_only=True)
    date = serializers.DateField(source='timeslot.date', read_only=True)

    class Meta:
        model = BookingSlot
        fields = ('id', 'timeslot','start_time', 'end_time', 'date', 'unit_price')


class BookingSerializer(serializers.ModelSerializer):
    booking_slots = BookingSlotSerializer(many=True, read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    court_name = serializers.SerializerMethodField()
    booking_date = serializers.DateTimeField(format='%Y-%m-%d %I:%M %p', read_only=True)

    class Meta:
        model = Booking
        fields = ('id', 'username', 'court_name', 'booking_date', 'advance_deposit', 'due_later',
                  'total_booking_price', 'booking_status', 'booking_slots')
        
    def get_court_name(self, obj):
        slots = list(obj.booking_slots.all()) # here list forcing Django to hit the database immediately
        if slots:
            return slots[0].timeslot.court.court_name
        
        return None
    

class CreateBookingSerializer(serializers.Serializer):
    timeslot_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)

    def validate_timeslot_ids(self, value):
        slots = TimeSlot.objects.filter(id__in=value)

        if slots.count() != len(value):
            raise serializers.ValidationError('slots do not exist')
        
        for slot in slots:
            if not slot.is_available:
                raise serializers.ValidationError(f"TimeSlot {slot.id} is already booked.")

        unique_court_id = slots.values_list('court_id', flat=True).distinct() # distinct() removes all duplicate items from that list, keeping only the unique values.

        if unique_court_id.count() > 1:
            raise serializers.ValidationError('You cannot book slots from different courts in one time.')    
        
        return value

    

class BookingCancellationSerializer(serializers.ModelSerializer):
    # Format the date beautifully for your frontend
    cancelled_at = serializers.DateTimeField(format='%Y-%m-%d %I:%M %p', read_only=True)

    class Meta:
        model = BookingCancellation
        fields = ('id', 'user', 'booking_id', 'court_name', 'slot_date', 'slot_range', 
                'cancellation_type', 'cancelled_at')
        
        

class PaymentVerifySerializer(serializers.Serializer):
    transaction_hash = serializers.CharField(max_length=100, required=True)
    payment_methods = serializers.ChoiceField(choices=Payment.methods, required=True)


class BookingPaymentSerializer(serializers.ModelSerializer):
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = ('id', 'booking_status', 'total_booking_price', 'advance_deposit', 'due_later', 'payment_details')

    def get_payment_details(self, obj):
        payment = getattr(obj, 'payments', None)

        if payment:
            return {
                "payment_id": payment.id,
                "payment_status" : payment.payment_status,
                "method" : payment.payment_methods,
                "transaction_hash" : payment.transaction_hash
            }
        
        return None
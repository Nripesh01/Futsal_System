from django.db import models, transaction
from django.conf import settings
from django.db.models import Q
from datetime import timedelta, datetime # datetime standard Python library for handling time.
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone
from django.contrib.auth import get_user_model
User = get_user_model()



class FutsalCourt(models.Model):
    owners = models.ForeignKey(User, on_delete=models.CASCADE, related_name='courts')
    court_name = models.CharField(max_length=50)
    location = models.CharField(max_length=50, help_text='Shantinagar, Kathmandu')
    base_price = models.DecimalField(max_digits=10, decimal_places=2, help_text='morning/mid/night rate')
    surface_type = models.CharField(max_length=50, help_text='5A, 7A side futsal')
    # image = models.ImageField(upload_to='futsal_image/', null=True, blank=True)
  
    status = [
        ('open', 'Open'),
        ('maintenance', 'Maintenance'),
        ('closed', 'Closed'),
        ('school', 'School events'),
        ('booked', 'tournament events is going on')
    ]
    court_status = models.CharField(max_length=100, choices=status, default='open')
    city_area = models.CharField(max_length=30, help_text='Kathmandu, Lalitpur, Bhaktapur')
    phone_number = models.CharField(max_length=10)

    def __str__(self):
        return f'{self.court_name}, {self.city_area} managed by {self.owners.username}'
    
    def update_details(self, **kwargs):
        for field, value in kwargs.items():
            setattr(self, field, value)
            
        self.save()  
        return f'Court {self.id} updated successfully'

    def view_details(self):
        return {
            'Futsal name': self.court_name,
            'Location': self.location,
            'city_area': self.city_area,
            'Base price': self.base_price,
            'Surface type': self.surface_type,
            'status': self.court_status,
            'Phone number': self.phone_number
        }

    @classmethod
    def search_location(cls, location, city_area):
        queryset = cls.objects.all()
        
        if location and city_area:
            return cls.objects.filter(
                Q(location__icontains=location) |
                Q(city_area__icontains=city_area) 
            )
        
        if location:
            return queryset.filter(location__icontains=location)
        
        if city_area:
            return queryset.filter(city_area__icontains=city_area)
        
        return queryset
        
        

class TimeSlot(models.Model):
    court = models.ForeignKey(FutsalCourt, on_delete=models.CASCADE, related_name='timeslots')
    start_time = models.TimeField()
    end_time = models.TimeField()
    date = models.DateField(null=True, blank=True)
    is_available = models.BooleanField(default=True)
    

    def __str__(self):
        return f"{self.court.court_name} : {self.start_time.strftime('%I: %M: %p')} - {self.end_time.strftime('%I: %M: %p')}"

    
    def check_available_time(self):
           return self.is_available is True
    

    @classmethod
    def generate_slots(cls, court_instance, start_time, end_time, start_date=None, end_date=None, duration_hours=1, is_available=True):
        
        if start_date is None:
            start_date = timezone.localdate()
        
        if end_date is None:
            end_date = timezone.localdate()
        
        if start_date > end_date:
            raise ValueError('Start date cannot be after end date')
        

        slots = cls.objects.filter(
            court = court_instance,
            date__gte = start_date,
            date__lte = end_date + timedelta(days=1)
        ).values_list('date', 'start_time')

        existing_slots = set(slots)
        

        slot_lists = []
        current_date = start_date

        with transaction.atomic():

            while current_date <= end_date:

                # make_aware is the process of taking a "dumb" time and making it a "smart" time.

                start_dt = timezone.make_aware(datetime.combine(current_date, start_time))
                end_dt = timezone.make_aware(datetime.combine(current_date, end_time))

                # combine is a function inside the datetime library.
                # time-slicing algorithm
                
                if end_time <= start_time:
                    end_dt += timedelta(days=1)


                while start_dt < end_dt:
                    next_slot = start_dt + timedelta(hours=duration_hours)

                    if next_slot > end_dt:
                        break

                    cal_date = start_dt.date()
                    start_t = start_dt.time()

                    if (cal_date, start_t) not in existing_slots:

                        slot_lists.append(
                            cls(
                                court = court_instance,
                                start_time = start_t,
                                end_time = next_slot.time(),
                                date = cal_date,
                                is_available = is_available
                        ) )

                    
                    start_dt = next_slot
                
                current_date += timedelta(days=1)
            
            if slot_lists:
                cls.objects.bulk_create(slot_lists)

        return len(slot_lists) 
       
    
    # overlap (double booking) prevention 
    def lock_slot(self):
        if self.is_available:
            self.is_available = False
            self.save(update_fields=['is_available'])
            return True
        return False
    

    def release_slot(self):
        self.is_available = True
        self.save(update_fields=['is_available'])

    
    def delete(self, *args, **kwargs):
        active_booking = self.booking_times.filter(booking__booking_status__in=['pending', 'confirmed']).exists()

        if active_booking:
            raise ValidationError({"error" : "Cannot delete this slot because it is currently tied to an active or confirmed booking. "
                "Please cancel the customer's booking first."})
        
        super().delete(*args, **kwargs)


    
    @classmethod
    def get_court_time(cls, court_id):
        return cls.objects.filter(court_id=court_id)
    


class Booking(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    booking_date = models.DateTimeField(auto_now_add=True)
    total_booking_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    advance_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=300) # advance pay to lock slot
    due_later = models.DecimalField(max_digits=10, decimal_places=2, default=0) # Remaining amount paid by losers later
    
    status = [
        ('pending', 'PENDING'),
        ('confirmed', 'CONFIRMED'),
        ('cancelled', 'CANCELLED')
    ]

    booking_status = models.CharField(max_length=20, choices=status ,default='pending')

    def __str__(self):
        return f'Booking {self.id} by {self.user.username}'
    
    @classmethod
    def expired_booking(cls):

        expired_time = timezone.now() - timedelta(minutes=3)
        expired_booking = cls.objects.filter(booking_status='pending', booking_date__lt=expired_time)
            
        if expired_booking.exists():
                with transaction.atomic():

                    for old_booking in expired_booking:
                        for slot in old_booking.booking_slots.all():
                            slot.timeslot.release_slot()

                        old_booking.booking_status = 'cancelled'
                        old_booking.save()  

    
    def create_booking(self):
        self.booking_status = 'pending' # pending: logic side, We have the record, but don't let the user play yet because they haven't paid
        self.save()
        return f'Booking for {self.user.username} is pending'
    
    
    def confirm_booking(self):
        if self.booking_status != 'cancelled':
            self.booking_status = 'confirmed'
            self.save()
            return True
        return False
    
    
    def cancel_booking(self):

        with transaction.atomic():

            self.booking_status = 'cancelled'
            self.save()
         
            for booking_slot in self.booking_slots.select_related('timeslot').all():
                booking_slot.timeslot.release_slot()

        return 'Booking Cancelled'
    

    def update_total_price(self):
        from decimal import Decimal

        total = self.booking_slots.aggregate(Sum('unit_price'))['unit_price__sum'] or 0
        # aggregate : "to combine multiple rows of data into a single summary value."

        total_decimal = Decimal(str(total))
        advance_decimal = Decimal(str(self.advance_deposit))

        self.total_booking_price = total

        self.due_later = max(Decimal('0.00'), total_decimal - advance_decimal)
        # max() function compares two values and picks the largest one.
        self.save()

        return f'total price : {self.total_booking_price} and due : {self.due_later}' 

    
    def view_bookings(self):
        return {
            'id' : self.id,
            'user': self.user.username,
            'date': self.booking_date.strftime('%m-%d %H'),
            # strftime: "String Format Time." It is a Python function that takes date (which the computer understands) and turns it into a "String" (which humans and React understand).
            'total':self.total_booking_price,
            'deposite': self.advance_deposit,
            'due': self.due_later,
            'status': self.booking_status
        }



class BookingSlot(models.Model):
    timeslot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name='booking_times')
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='booking_slots')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
      

    def __str__(self):
        return f'{self.id}, {self.booking.user.username}'

    # overlap prevention
    def available_slots(self):
        if not self.timeslot.is_available:
            raise ValidationError(f'Slots {self.timeslot} is already booked')
        return True
    
    # rule-based heuristic for determing pricing 
    def calculate_slot_price(self):
        base = self.timeslot.court.base_price
        hour = self.timeslot.start_time.hour
        
        if hour >= 22 or hour < 5:
            return base + 700

        elif 18 <= hour < 22:
            return base + 500
        
        elif 13 <= hour < 18:
            return base + 200
        
        return base
    

    def save(self, *args, **kwargs):
        if not self.id:
            self.available_slots()

            if not self.unit_price:
                self.unit_price = self.calculate_slot_price()

            self.timeslot.lock_slot()
        
        super().save(*args, **kwargs)
        
        self.booking.update_total_price()


    def delete(self, *args, **kwargs):
        self.timeslot.release_slot()
        super().delete(*args, **kwargs)
        self.booking.update_total_price()

    
    # greedy search
    @classmethod
    def multiple_booking(cls, booking_instance, timeslots_id):

        with transaction.atomic():
            locked_slots = TimeSlot.objects.select_for_update().filter(id__in=timeslots_id)

            slots_created = []

            for slot in locked_slots:
                new_slot = cls.objects.create(
                    booking = booking_instance,
                    timeslot = slot
                )    
                
                slots_created.append(new_slot)
        
            return slots_created



class BookingCancellation(models.Model):
    CANCELLATION_CHOICES = [
        ('sinlge', 'single slot cancellation'),
        ('entire', 'entire slot cancellation')
    ]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='booking_cancellation')
    booking_id = models.IntegerField()
    court_name = models.CharField(max_length=150)
    slot_date = models.DateField()
    slot_range = models.CharField(max_length=100) # 4-5..
    cancellation_type = models.CharField(max_length=20, choices=CANCELLATION_CHOICES)
    cancelled_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_cancellation_type_display()}] Booking {self.booking_id} by {self.user.username if self.user else 'Deleted User'}"



class Payment(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)

    methods = [
        ('esewa', 'ESEWA'),
        ('khalti', 'KHALTI'),
        ('bank', 'BANK'),
        ('cash', 'CASH')
    ]

    payment_methods = models.CharField(max_length=50, choices=methods)

    status = [
        ('pending', 'PENDING'),
        ('completed', 'COMPLETED'),
        ('failed', 'FAILED')
    ]

    payment_status = models.CharField(max_length=20, choices=status, default='pending')

    # hashing logic, unique=True, from same esewa id cannot used twice
    transaction_hash = models.CharField(max_length=100, unique=True, null=True, blank=True)


    def __str__(self):
        return f'Pay {self.id} for booking {self.booking.id}'
    

    def initial_payment(self):
        self.payment_status = 'pending'
        self.save()
        return f'Payment {self.amount} pays via {self.payment_methods} esewa is pending'
    
    # hashing logic 
    def confirm_payment(self, txn_hash):
        self.payment_status = 'completed'
        self.transaction_hash = txn_hash
        self.save()

        is_confirmed = self.booking.confirm_booking()

        if is_confirmed:
            return 'Advance pay confirmed and futsal booked'
        else:
            return 'Payment received, but booking was already cancelled!'


    def handle_failuer(self):
        if self.payment_status != 'completed':
            with transaction.atomic():
                self.payment_status = 'failed'
                self.save()

                self.booking.cancel_booking()

            return 'Payment Failed'



    def generate_receipt(self):
        if self.payment_status == 'completed':
            return {
                'Player name': self.booking.user.username,
                'Receipt number': f'Recp-{self.id}',
                'Advance amount': self.amount,
                'Remaining Due (Loser Pays)': self.booking.due_later,
                'Method': self.payment_methods,
                'Txn id': self.transaction_hash,
                'Date': self.payment_date.strftime('%Y-%m-%d'),
                'total amount': self.booking.total_booking_price
            }

        return 'Receipt not available for unpaid transactions.'

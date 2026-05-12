from django.db import models, transaction
from django.conf import settings
from django.db.models import Q
from datetime import timedelta, datetime
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils import timezone



class FutsalCourt(models.Model):
    court = models.CharField(max_length=50)
    location = models.CharField(max_length=50, help_text='Shantinagar, Kathmandu')
    base_price = models.DecimalField(max_digits=10, decimal_places=2, help_text='morning/mid/night rate')
    surface_type = models.CharField(max_length=50, help_text='5A, 7A side futsal')

    COURT_STATUS = [
        ('open', 'OPEN'),
        ('maintenance', 'MAINTENANCE'),
        ('closed', 'CLOSED')
    ]
    status = models.CharField(max_length=100, choices=COURT_STATUS, default='open')

    city_area = models.CharField(max_length=50, help_text='Kathmandu, Lalitpur, Bhaktapur')
    phone_number = models.CharField(max_length=10)

    def __str__(self):
        return f'{self.court}, {self.city_area}'
    

    def update_details(self, **kwargs):
        for field, value in kwargs.items():
            setattr(self, field, value)
            self.save()
            
        return f'Court {self.id} updated successfully'

     
    def view_details(self):
        return {
           'Futsal name': self.court,
             'Location': self.location,
             'city_area': self.city_area,
             'Base price': self.base_price,
             'Surface type': self.surface_type,
             'status': self.status,
             'Phone number': self.phone_number
            }
    

    @classmethod
    def search_location(cls, location, city_area):
        return cls.objects.filter(
            Q(court__icontains=location) |
            Q(city_area__icontains=city_area) 
        )




class TimeSlot(models.Model):
    court = models.ForeignKey(FutsalCourt, on_delete=models.CASCADE, related_name='timeslots')
    start_time = models.TimeField()
    end_time = models.TimeField()
    date = models.DateField(null=True, blank=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.court.court} futsal : {self.start_time.strftime('%I: %M: %p')} - {self.end_time.strftime('%I: %M: %p')}"

    
    def check_available_time(self):
           return self.is_available is True
    

    @classmethod
    def generate_slots(cls, court_instance, start_time, end_time, book_date=None, duration_hours=1):
        
        if book_date is None:
            book_date = timezone.localdate()
        
        # make_aware is the process of taking a "dumb" time and making it a "smart" time.
        current_dt = timezone.make_aware(datetime.combine(book_date, start_time))
        end_dt = timezone.make_aware(datetime.combine(book_date, end_time))

        slot_list = []
        
        with transaction.atomic():
            while current_dt < end_dt:
                next_slot = current_dt + timedelta(hours=duration_hours)

                if next_slot > end_dt:
                    break

                slots = cls.objects.create(
                    court = court_instance,
                    start_time = current_dt.time(),
                    end_time = next_slot.time(),
                    date = book_date,
                    is_available = True
                )
 
                slot_list.append(slots)
                current_dt = next_slot
        
        return f'{len(slot_list)}'
    
    
    # overlap prevention
    def lock_slot(self):
        if self.is_available:
            self.is_available = False
            self.save()
            return True
        return False
    
    def release_slot(self):
        self.is_available = True
        self.save()

    
    @classmethod
    def get_slot_time(cls, court_id):
        return cls.objects.filter(court_id=court_id)
    



class Booking(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    booking_date = models.DateTimeField(auto_now_add=True)
    total_booking_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    STATUS_CHOICES = [
        ('pending', 'PENDING'),
        ('confirmed', 'CONFIRMED'),
        ('cancelled', 'CANCELLED')
    ]

    booking_status = models.CharField(max_length=20, default='pending')

    def __str__(self):
        return f'Booking {self.id} by {self.user.username}'
    
    
    def create_booking(self):
        self.booking_status = 'PENDING' # pending: logic side, We have the record, but don't let the user play yet because they haven't paid
        self.save()
        return f'Booking for {self.user.username} is created'
    
    
    def confirm_booking(self):
        if self.booking_status != 'CANCELLED':
            self.booking_status = 'CONFIRMED'
            self.save()
            return True
        return False
    
    
    def cancel_booking(self):
        self.booking_status = 'cancelled'
        self.save()

        for slot in self.booking_slots.all():
            slot.timeslot.release_slot()


    def update_total_price(self):
        total = self.booking_slots.aggregate(Sum('unit_price'))['unit_price__sum'] or 0
        self.total_booking_price = total
        self.save()

    
    
    def view_bookings(self):
        return {
            'ID' : self.id,
            'USER': self.user.username,
            'DATE': self.booking_date.strftime('%Y-%m-%d %H-%M'),
            # strftime: "String Format Time." It is a Python function that takes a complex "Date Object" (which the computer understands) and turns it into a "String" (which humans and React understand).
            'TOTAL':self.total_booking_price,
            'STATUS': self.booking_status
        }



class BookingSlot(models.Model):
    timeslot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE, related_name='booking_times')
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='booking_slots')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
      

    # overlap prevention
    def validate_slots(self):
        if not self.timeslot.is_available:
            raise ValidationError(f'Slots {self.timeslot} is already booked')
        return True
    
    # rule-based heuristic for determing pricing 
    def calculate_slot_price(self):
        base = self.timeslot.court.base_price
        hour = self.timeslot.start_time.hour

        if hour >= 18:
            return base + 500
        
        elif 13 <= hour < 18:
            return base + 200
        
        return base
    

    def save(self, *args, **kwargs):
        if not self.id:
            self.validate_slots()

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
            slots_created = []
            for ts_id in timeslots_id:
                new_slot = cls.objects.create(
                    booking = booking_instance,
                    timeslot_id = ts_id
                )
                slots_created.append(new_slot)
        
            return slots_created




class Payment(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)

    PAYMENT_METHODS = [
        ('esewa', 'ESEWA'),
        ('khalti', 'KHALTI'),
        ('bank', 'BANK'),
        ('cash', 'CASH')
    ]

    payment_methods = models.CharField(max_length=50, choices=PAYMENT_METHODS)

    PAYMENT_STATUS = [
        ('pending', 'PENDING'),
        ('completed', 'COMPLETED'),
        ('failed', 'FAILED')
    ]

    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')

    # hashing logic, unique=True, from same esewa id cannot used twice
    TransactionHash = models.CharField(max_length=100, unique=True, null=True, blank=True)


    def __str__(self):
        return f'Pay {self.id} for booking {self.booking.id}'
    

    def initial_payment(self):
        self.payment_status = 'pending'
        self.save()
        return f'Payment of {self.amount} pays via {self.payment_methods}'
    
    # hashing logic 
    def confirm_payment(self, txn_hash):
        self.payment_status = 'completed'
        self.TransactionHash = txn_hash
        self.save()

        self.booking.booking_status = 'confirmed'
        self.booking.save()

        return 'Payment confirm and booking booked'


    def handle_failuer(self):
        if self.payment_status != 'completed':
            self.payment_status = 'failed'
            self.save()

            self.booking.cancel_booking()

            return 'Payment Failed'



    def generate_receipt(self):
        if self.payment_status == 'completed':
            return {
                'Player name': self.booking.user.username,
                'Receipt number': f'Recp-{self.id}',
                'Amount': self.amount,
                'Method': self.payment_methods,
                'Txn id': self.TransactionHash,
                'Date': self.payment_date.strftime('%Y-%m-%d')
            }

        return 'Receipt not available for unpaid transactions.'

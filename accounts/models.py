from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta
from django.db.models import Sum, Count



ADMIN_PERMISSIONS = [
    'assign_roles', 'manage_users', 'manage_futsal_courts', 'manage_time_slots', 'search_futsals',
    'monitor_payments','generate_reports', 'view_futsal_courts', 'check_time_available', 'book_slots'
]

PLAYER_PERMISSIONS = [
    'view_futsal_courts', 'search_futsals', 'check_time_available', 'select_time_slot',
    'create_booking','book_slots' 'view_bookings', 'make_payment', 'cancel_booking'
]



class Role(models.Model):
    role_name = models.CharField(max_length=50)
    permission = models.TextField(help_text='According to the role you will get permissions.')

    def __str__(self):
        return self.role_name
    
    def get_permissions(self):
        if self.role_name == 'Admin':
            return ADMIN_PERMISSIONS
        
        elif self.role_name == 'Player':
            return PLAYER_PERMISSIONS
        
        return[]




class User(AbstractUser):
    phone_number = models.CharField(max_length=10, unique=True, null=False, blank=False)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, blank=True, null=True, related_name='users')

    def __str__(self):
        if self.role:
           return f'{self.username}  ({self.role.role_name})'
        return f'{self.username}  -  Role is not assigned yet'    

    
    def has_permission(self, perm_name):

        if not self.role:
            return False
        
        return perm_name in self.role.get_permissions()
    



    def save(self, *args, **kwargs):
        if not self.role:
            try:
                self.role = Role.objects.get(role_name='Player')
            except Role.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)



    def assign_roles(self, get_user_id, new_role_id):

        if self.has_permission('assign_roles'):
            
            from .models import Role
            try:
                get_user = User.objects.get(id=get_user_id)
                get_role = Role.objects.get(id=new_role_id)

                get_user.role = get_role
                get_user.save()
                return f'{get_user.username} player is {get_role.role_name} now..'
            
            except (User.DoesNotExist, Role.DoesNotExist):
                return 'User or Role not found'
        
        return 'Permission denied'
    


    def manage_users(self, get_user_id, action):

        if self.has_permission('manage_users'):
            try:
                get_user = User.objects.get(id=get_user_id)

                if action == 'ban':
                    get_user.is_active = False
                    get_user.save()
                    return f'{get_user.username} has been banned.'
                
                elif action == 'activated':
                    get_user.is_active = True
                    get_user.save()
                    return f'{get_user.username} has been activated.'
                
                elif action == 'deleted':
                    username = get_user.username
                    get_user.delete()
                    return f'{username} player has been permanently deleted'
                
                return 'Invalid action provided'
            
            except User.DoesNotExist:
                return 'User not found'
        
        return 'Permission denied'
            


    def manage_futsal_courts(self, action, court_id=None, **kwargs):

        if self.has_permission('manage_futsal_courts'):

            from bookings.models import FutsalCourt

            if action == 'create':
                return FutsalCourt.objects.create(**kwargs)
            
            if action == 'update' and court_id:
                court = FutsalCourt.objects.get(id=court_id)
                return court.updated_details(**kwargs)
        
        return 'Permission denied'
    


    def manage_time_slots(self, court_instance, start_time, end_time, date=None):
        if self.has_permission('manage_time_slots'):

            from bookings.models import TimeSlot
            return TimeSlot.generate_slots(court_instance, start_time, end_time, date)
        
        return 'Permission denied'



    def search_futsals(self, location, city_area):
        if self.has_permission('search_futsal'):

            from bookings.models import FutsalCourt
            return FutsalCourt.search_location(location, city_area)
        
        return 'Permission denied'
    


    def monitor_payments(self):
        if self.has_permission('monitor_payments'):

            from bookings.models import Payment
            return Payment.objects.all().order_by('-payment_date')

        return 'Permission denied'     

    

    # def generate_annual_daily_reports(self):
    #     if self.has_permission('generate_reports'):

    #         from bookings.models import Payment

    #         now = timezone.now()
    #         one_year_ago = now - timedelta(days=365)

    #         payments = Payment.objects.filter(
    #             payment_date__gte=one_year_ago,
    #             payment_date__hour__gte=6,
    #             payment_date__hour__gte=22,
    #             payment_status = 'completed'
    #         )
            





    def book_slots(self, timeslots_id):
        if self.has_permission('create_bookings'):

            from bookings.models import TimeSlot, Booking, BookingSlot
            valid_slot_number = TimeSlot.objects.filter(id__in=timeslots_id).count()

            if valid_slot_number != len(timeslots_id):
                return 'This slots is not available'
            
            new_booking = Booking.objects.create(user=self)
            return BookingSlot.multiple_booking(new_booking, timeslots_id)
        
        return 'Permissions denied'

        

    def make_payment(self, booking_instance, amount, method):

        if self.has_permission('make_payment'):

            from bookings.models import Payment 
            payment = Payment.objects.create(
                booking=booking_instance,
                amount=amount,
                PaymentMethod=method
            )
            return payment.initial_payment()
        
        return 'Permission denied'



    

    
    


    
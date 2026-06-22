from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import PermissionDenied
from django.http import Http404



ADMIN_PERMISSIONS = [
    'assign_roles', 'manage_users', 'manage_futsal_courts', 'manage_time_slots', 'monitor_payments', 'search_futsals',
    'generate_reports', 'view_futsal_courts', 'check_time_available', 'create_booking', 'view_bookings', 'select_time_slot',
    'cancel_booking'
]

PLAYER_PERMISSIONS = [
    'view_futsal_courts', 'search_futsals', 'check_time_available', 'select_time_slot',
    'create_booking', 'view_bookings', 'make_payment', 'cancel_booking'
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
                self.role = Role.objects.get(role_name__iexact='Player')
            except Role.DoesNotExist:
                self.role = Role.objects.create(
                    role_name = 'Player',
                    permission = 'Default player permission'
                )
        
        super().save(*args, **kwargs)



    def assign_roles(self, get_user_id, get_role_id):

        if self.has_permission('assign_roles'):
            
            from .models import Role
            try:
                get_user = User.objects.get(id=get_user_id)
                get_role = Role.objects.get(id=get_role_id)

                get_user.role = get_role
                get_user.save()
                return f'{get_user.username} player is {get_role.role_name} now..'
            
            except (User.DoesNotExist, Role.DoesNotExist):
                return 'User and Role not found'
        
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
            
                return 'Invalid action provided'
            
            except User.DoesNotExist:
                return 'User not found'
        
        return 'Permission denied'
            


    def manage_futsal_courts(self, action, court_id=None, **kwargs):

        if not self.has_permission('manage_futsal_courts'):
            raise PermissionDenied("You don't have permission to manage futsal courts.")

        from bookings.models import FutsalCourt

        if action == 'create':
            return FutsalCourt.objects.create(**kwargs)
        
            
        if action == 'update' and court_id:
            try:
                court = FutsalCourt.objects.get(id=court_id)
                court.update_details(**kwargs)
                return court
            
            except FutsalCourt.DoesNotExist:
                raise Http404("court not found")
            
        if action == 'delete' and court_id:
            try:
                court = FutsalCourt.objects.get(id=court_id)
                court_name = court.court_name
                court.delete()
                return f"Court '{court_name}' (id: {court_id}) deleted successfully"
                    
            except FutsalCourt.DoesNotExist:
                raise Http404("court not found")
            
        raise ValueError("Invalid action")
        
        
    


    def manage_time_slots(self, court_instance, start_time, end_time, start_date=None, end_date=None, duration_hours=1):
        
        from django.core.exceptions import PermissionDenied

        if not self.has_permission('manage_time_slots'):
            raise PermissionDenied("You do not have access to manage time slots.")

        from bookings.models import TimeSlot        
        return TimeSlot.generate_slots(
            court_instance=court_instance,
            start_time=start_time,
            end_time=end_time,
            start_date=start_date,
            end_date=end_date,
            duration_hours=duration_hours
        )
    

    def monitor_payments(self):
        if self.has_permission('monitor_payments'):

            from bookings.models import Payment
            return Payment.objects.all().order_by('-payment_date')

        return 'Permission denied'     

    

    def generate_reports(self):
        if self.has_permission('generate_reports'):

            from bookings.models import Payment

            now = timezone.now()
            one_year_ago = now - timedelta(days=365)

            payments = Payment.objects.filter(
                payment_date__gte=one_year_ago,
                payment_date__hour__gte=6,
                payment_date__hour__lte=22,
                payment_status = 'completed'
             )
            pass

    
    def search_futsals(self, location, city_area):
        from django.core.exceptions import PermissionDenied

        if not self.has_permission('search_futsals'):
            raise PermissionDenied("Permission denied: You do not have access to search futsals.")

        from bookings.models import FutsalCourt
        return FutsalCourt.search_location(location, city_area)
        



    def view_bookings(self):
        if self.has_permission('view_bookings'):
            
            return [booking.view_bookings() for booking in self.bookings.all()]
        
        return 'Permission denied'
        
        

    def check_time_available(self, slots):
        if self.has_permission('check_time_available'):
            
            return slots.check_available_time()
        
        return 'Permission denied'


    def view_futsal_courts(self):
        if self.has_permission('view_futsal_courts'):

            from bookings.models import FutsalCourt
            return FutsalCourt.objects.all()
        
        return 'Permission denied'
    

    def select_time_slot(self, booking_instance, timeslots_id):
        if self.has_permission('select_time_slot'):

            from bookings.models import BookingSlot
            return BookingSlot.multiple_booking(booking_instance, timeslots_id)
        
        return 'Permission denied'


    def create_booking(self):
        if self.has_permission('create_booking'):
            
            from bookings.models import Booking
            new_booking = Booking(user=self)
            return new_booking.create_booking()
        
        return 'Permission denied'


    def make_payment(self, booking_instance, amount, methods):

        if self.has_permission('make_payment'):

            from bookings.models import Payment 
            payment = Payment.objects.create(
                booking=booking_instance,
                amount=amount,
                payment_methods=methods
            )
            return payment.initial_payment()
        
        return 'Permission denied'

    
    def cancel_booking(self, booking_instance):
        if self.has_permission('cancel_booking'):

            return booking_instance.cancel_booking()
        
        return 'Permission denied'

    

    
    


    
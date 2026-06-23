from django.contrib import admin
from .models import FutsalCourt, TimeSlot, Booking, BookingSlot, Payment, BookingCancellation


# Register your other models as usual
admin.site.register(FutsalCourt)
admin.site.register(TimeSlot)
admin.site.register(Booking)
admin.site.register(BookingSlot)
admin.site.register(Payment)
admin.site.register(BookingCancellation)
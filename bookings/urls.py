from django.urls import path
from .views import CourtView, CourtDetailView, TimeSlotListView, CourtSlotGetView, GenerateSlotView
from .views import BookingListCreateView, CancelIndividualSlotView, CancelFullBookingView, CancellationView
from .views import PaymentVerifyView, DeleteSlotView




urlpatterns = [

    path('courts/', CourtView.as_view(), name='court-list-create'),

    path('courts/<int:pk>/', CourtDetailView.as_view(), name='court-update-delete'),

    path('slots/', TimeSlotListView.as_view(), name='timeslot-list'),

    path('booking/slots/<int:slot_id>/delete/', DeleteSlotView.as_view(), name='delete-timeslot'),

    path('booking/slots/bulk-delete/', DeleteSlotView.as_view(), name='bulk-delete-timeslot'),
    
    path('courts/<int:court_id>/slots/', CourtSlotGetView.as_view(), name='court-specific-slots'),

    path('courts/<int:court_id>/slots/generate/', GenerateSlotView.as_view(), name='timeslot-generate'),

    path('booking/', BookingListCreateView.as_view(), name='booking-list-create'),

    path('booking/slots/<int:slot_id>/cancel/', CancelIndividualSlotView.as_view(), name='cancel-individual-slot'),

    path('booking/<int:booking_id>/cancel/', CancelFullBookingView.as_view(), name='cancel-booking'),

    path('cancellation/', CancellationView.as_view(), name='admin-today-cancellations'),

    path('booking/<int:booking_id>/verify-payment/', PaymentVerifyView.as_view(), name='verify-payment'),
]


from .serializers import CourtSerializer, TimeSlotSerializer, GenerateSlotSerializer, PaymentVerifySerializer, BookingPaymentSerializer
from .serializers import BookingSlotSerializer, BookingSerializer, CreateBookingSerializer, BookingCancellationSerializer
from .models import FutsalCourt, TimeSlot, Booking, BookingSlot, BookingCancellation, Payment
from rest_framework.views import APIView
from rest_framework import status, generics
from rest_framework.response import Response
from django.db import transaction
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly, IsAuthenticated
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
import nepali_datetime
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError

User = get_user_model()


class CourtView(APIView):

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated()]
        
        return [AllowAny()]

    def get(self, request):
                
        location = request.query_params.get('location', '').strip()
        city_area = request.query_params.get('city_area', '').strip()

        if location or city_area:
            courts = FutsalCourt.search_location(location=location, city_area=city_area)
        
        else:
            courts = FutsalCourt.objects.all()

        serializer = CourtSerializer(courts, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    

    def post(self, request):
    
        serializer = CourtSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            new_court = request.user.manage_futsal_courts(action='create', **serializer.validated_data)
            return Response(CourtSerializer(new_court).data, status=status.HTTP_201_CREATED)

        except PermissionDenied as e:
            return Response({"error" : str(e)}, status=status.HTTP_403_FORBIDDEN)



class CourtDetailView(APIView):

    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        
        return [IsAuthenticated()]
        
    def get(self, request, pk):

        court = get_object_or_404(FutsalCourt, pk=pk)

        return Response(court.view_details(), status=status.HTTP_200_OK)
    

    def put(self, request, pk):

        court = get_object_or_404(FutsalCourt, pk=pk)

        serializer = CourtSerializer(court, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            update_court = request.user.manage_futsal_courts(action='update', court_id=court.id, **serializer.validated_data)
            return Response(CourtSerializer(update_court).data, status=status.HTTP_200_OK)
        
        except PermissionDenied as e:
            return Response({"error" : str(e)}, status=status.HTTP_403_FORBIDDEN)


    def delete(self, request, pk):

        court = get_object_or_404(FutsalCourt, pk=pk)
        
        try:
            del_court = request.user.manage_futsal_courts(action='delete', court_id=court.id)
            return Response({'message': del_court}, status=status.HTTP_200_OK)
        
        except PermissionDenied as e:
            return Response({"error" : str(e)}, status=status.HTTP_403_FORBIDDEN)



class TimeSlotListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        
        Booking.expired_booking()

        queryset = TimeSlot.objects.all()

        court_id = request.query_params.get('court_id')
        date_str = request.query_params.get('date')
        date_type = request.query_params.get('date_type', 'AD') # default AD
        available = request.query_params.get('available')

        if court_id:
            queryset = queryset.filter(court_id=court_id)

        if date_str:
            try:
                if date_type.upper() == 'BS':
                    np_date = nepali_datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    query_date = np_date.to_datetime_date() # to_datetime_date takes an existing Nepali date object and converts it back into AD
                
                else:
                    query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                queryset = queryset.filter(date=query_date)
            
            except ValueError:
                return Response(
                    {"error": "Invalid date format. Please use 'YYYY-MM-DD'."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )


        if available is not None:
            if available.lower() == 'true':
                queryset = queryset.filter(is_available=True)
            
            elif available.lower() == 'false':
                queryset = queryset.filter(is_available=False)
        
        if not queryset.exists():
            return Response([], status=status.HTTP_200_OK)
        
        serializer = TimeSlotSerializer(queryset, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    


class DeleteSlotView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self,request, slot_id=None):
      
        del_date_eng = request.query_params.get('date')
        del_date_nep = request.query_params.get('date_bs')

        lookup_date = None
        display_date = ""

        try:
            if not request.user.has_permission('manage_time_slots'):
                raise PermissionDenied("You do not have access to manage time slots.")
            
            if del_date_eng:
                lookup_date = datetime.strptime(del_date_eng, '%Y-%m-%d').date()
                display_date = del_date_eng

            elif del_date_nep:
                try:
                    np_date = nepali_datetime.datetime.strptime(del_date_nep, '%Y-%m-%d').date()
                    lookup_date = np_date.to_datetime_date()
                    display_date = f'{del_date_nep}'
                
                except ValueError:
                    return Response({
                        "error": "Invalid Nepali date format. Please use 'YYYY-MM-DD' (e.g., 2083-03-11)."
                    }, status=status.HTTP_400_BAD_REQUEST)

        
            with transaction.atomic():
                if lookup_date:
                    all_slots = TimeSlot.objects.filter(date=lookup_date)
                 
                    if not all_slots.exists():
                        return Response({"message": f"No slots found on {display_date}."}, status=status.HTTP_404_NOT_FOUND)       

                    delete_count = 0
                    skip_count = 0

                    for slot in all_slots:
                            if slot.booking_times.filter(booking__booking_status__in=['pending', 'confirmed']).exists():
                                skip_count += 1
                            
                            else:
                                slot.delete()
                                delete_count += 1

                    return Response({
                            "message": f"deletion completed for {display_date}.",
                            "slots deleted": delete_count,
                            "slots skipped due to active bookings": skip_count
                        }, status=status.HTTP_200_OK)        
                
                else:
                    if not slot_id:
                            return Response({"error": "Slot ID or Date parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

                    timeslot = get_object_or_404(TimeSlot, id=slot_id)
                    timeslot.delete()
                    return Response({"message": f"Time slot {slot_id} deleted successfully."}, status=status.HTTP_200_OK)
        
        except PermissionDenied as e:
            return Response({"error" : str(e)}, status=status.HTTP_403_FORBIDDEN)

        except ValueError:
            return Response({"error": "Invalid English date format. Please use 'YYYY-MM-DD'."}, status=status.HTTP_400_BAD_REQUEST)
        
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)




class CourtSlotGetView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, court_id):
        
        if not FutsalCourt.objects.filter(id=court_id).exists():
            return Response(f'court with id {court_id} does not exist', status=status.HTTP_404_NOT_FOUND)

        queryset = TimeSlot.get_court_time(court_id=court_id)

        date_str = request.query_params.get('date')
        date_type = request.query_params.get('date_type', 'AD')

        if date_str:
            try:
                if date_type.upper() == 'BS':
                    np_date = nepali_datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    query_date = np_date.to_datetime_date()

                else:
                    query_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                queryset = queryset.filter(date=query_date)
            
            except ValueError:
                return Response({"error": f"Invalid date format {date_type}. Please use 'YYYY-MM-DD'."}, 
                status=status.HTTP_400_BAD_REQUEST)
        
        if not queryset.exists():
            return Response({"error": "Related date not found."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = TimeSlotSerializer(queryset, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    
    

class GenerateSlotView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, court_id):

        data = request.data.copy() # .copy() creates a mutable (editable) clone of that request data so can safely inject fields before passing them to the serializer.
        data['court_id'] = court_id

        serializer = GenerateSlotSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        court_instance = get_object_or_404(FutsalCourt, id=court_id)

        try:
            slots_created = request.user.manage_time_slots(
                court_instance=court_instance,
                start_date=data.get('start_date'),
                end_date=data.get('end_date'),
                start_time=data['start_time'],
                end_time=data['end_time'],
                duration_hours=data['duration_hours']
            )
            
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        
        except Exception as e:
            return Response({"error": f"Failed to build timelines: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
       
        if slots_created == 0:
            return Response({"message": "Slot times already exist for this court."}, status=status.HTTP_200_OK)
        
        generated_slots = TimeSlot.objects.filter(
            court = court_instance,
            date__gte = data.get('start_date'),
            date__lte = data.get('end_date')
        ).order_by('date', 'start_time')

        response_serializer = TimeSlotSerializer(generated_slots, many=True)
        
        return Response({
            "message": f"Generated {slots_created} new time slots",
            "data": response_serializer.data
        }, status=status.HTTP_201_CREATED)
    


class BookingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        Booking.expired_booking()
        
        queryset = Booking.objects.filter(user=request.user).prefetch_related('booking_slots__timeslot__court')
        court_id = request.query_params.get('court_id')

        if court_id:
            queryset = queryset.filter(booking_slots__timeslot__court=court_id).distinct() 
            
        serializer = BookingSerializer(queryset, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    

    def post(self, request):

        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        timeslot_ids = serializer.validated_data['timeslot_ids']

        try:
            with transaction.atomic():
                booking = Booking(user=request.user)
                result = booking.create_booking()

                if result == 'Permission denied':
                    return Response({"error": "Permission denied: You do not have access to create bookings."}, status=status.HTTP_403_FORBIDDEN)

                BookingSlot.multiple_booking(booking_instance=booking, timeslots_id=timeslot_ids)

        except DjangoValidationError as e:
            return Response({'error' : str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            return Response({'error': 'An unexpected error occurred during booking.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        booking.refresh_from_db()
        result = BookingSerializer(booking)

        return Response({
            "message": "Booking generated ",
            "booking": result.data }, status=status.HTTP_201_CREATED)
    


class CancelIndividualSlotView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, slot_id):

        if not request.user.has_permission('cancel_booking'):
            return Response({"error" : "You do not have permission to cancel the booking"}, status=status.HTTP_403_FORBIDDEN)
        
        booking_slot = get_object_or_404(BookingSlot, id=slot_id)
        parent_booking = booking_slot.booking

        if parent_booking.user != request.user:
            return Response({"error": "Unauthorized access"}, status=status.HTTP_403_FORBIDDEN)
        
        if parent_booking.booking_status == 'cancelled':
            return Response({"error": "This slot is already cancelled"}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            BookingCancellation.objects.create(
                user = request.user,
                booking_id = parent_booking.id,
                court_name = booking_slot.timeslot.court.court_name,
                slot_date = booking_slot.timeslot.date,
                slot_range = f"{booking_slot.timeslot.start_time} - {booking_slot.timeslot.end_time}",
                cancellation_type = 'single'
            )

            booking_slot.delete()

            if parent_booking.booking_slots.count() == 0:
                parent_booking.booking_status = 'cancelled'
                parent_booking.total_booking_price = 0.00
                parent_booking.advance_deposit = 0.00
                parent_booking.due_later = 0.00
                parent_booking.save()

        parent_booking.refresh_from_db()
        return Response({
            "message" : f"{slot_id} slots cancelled",
            "booking" : BookingSerializer(parent_booking).data}, status=status.HTTP_200_OK
        )


class CancelFullBookingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):

        if not request.user.has_permission('cancel_booking'):
            return Response({"error" : "You do not have permission to cancel the booking"}, status=status.HTTP_403_FORBIDDEN)
        
        booking = get_object_or_404(Booking, id=booking_id)

        if booking.user != request.user:
            return Response({"error": "Unauthorized action."}, status=status.HTTP_403_FORBIDDEN)
        
        if booking.booking_status == 'cancelled':
            return Response({"error": "This booking is already cancelled."}, status=status.HTTP_400_BAD_REQUEST)
        
        active_slots = list(booking.booking_slots.all())

        with transaction.atomic():
            for slot in active_slots:
                log_entry = BookingCancellation.objects.create(
                    user = request.user,
                    booking_id = booking.id,
                    court_name = slot.timeslot.court.court_name,
                    slot_date = slot.timeslot.date,
                    slot_range = f"{slot.timeslot.start_time} - {slot.timeslot.end_time}",
                    cancellation_type = 'entire'
                )

                slot.delete()
            
            booking.booking_status = 'cancelled'
            booking.total_booking_price = 0.00
            booking.advance_deposit = 0.00
            booking.due_later = 0.00
            booking.save()

        booking.refresh_from_db()

        booking_data = BookingSerializer(booking).data

        return Response({
            "message" : f'booking id {booking_id} has been cancelled', 
            "booking": booking_data}, status=status.HTTP_200_OK ) 


class CancellationView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):

        if not request.user.has_permission('generate_reports'):
            return Response({"error" : "Only admin can see the cencellation view"}, status=status.HTTP_403_FORBIDDEN)
        
        today = timezone.localtime(timezone.now()).date()
        one_week_ago = today - timedelta(days=7)

        week_cancellations = BookingCancellation.objects.filter(
            cancelled_at__date__range=[one_week_ago, today]
            ).order_by('-cancelled_at')

        total_cancel_slot = week_cancellations.count()
        entire_bookings_count = week_cancellations.filter(cancellation_type='entire').count()
        single_slots_count = week_cancellations.filter(cancellation_type='single').count()

        serializer = BookingCancellationSerializer(week_cancellations, many=True)

        return Response({
            "date":f"{one_week_ago.strftime('%Y-%m-%d')} to {today.strftime('%Y-%m-%d')}",
            "summary": {
                "total_cancellations": total_cancel_slot,
                "full_bookings_cancelled": entire_bookings_count,
                "individual_slots_cancelled": single_slots_count
            },
            "records": serializer.data}, status=status.HTTP_200_OK)
    


class PaymentVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, booking_id):

        if not request.user.has_permission('make_payment'):
            return Response({"error" : "You do not have permission to make payment"}, status=status.HTTP_403_FORBIDDEN)
               
        booking = get_object_or_404(Booking, id=booking_id)

        if booking.user != request.user:
            return Response({"error": "Unauthorized action."}, status=status.HTTP_403_FORBIDDEN)

        if booking.booking_status != 'pending':
            return Response({"error" : f"Cannot process payment, this booking is {booking.booking_status}."}, status=status.HTTP_400_BAD_REQUEST)
        
        exp_time = timezone.now() - booking.booking_date
        if exp_time > timedelta(minutes=3):
            with transaction.atomic():

                for slot in booking.booking_slots.all():
                    slot.timeslot.release_slot()
                
                booking.booking_status = 'failed'
                booking.save()

                return Response({"error" : "Payment failed, pays with in 3 minute after booking"}, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = PaymentVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        txn_hash = serializer.validated_data['transaction_hash']
        method = serializer.validated_data['payment_methods']

        if Payment.objects.filter(transaction_hash=txn_hash).exists():
            return Response({"error": "Duplicate transaction hash."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                payment, created = Payment.objects.get_or_create(
                    booking=booking, defaults={'amount': booking.advance_deposit, 'payment_methods': method})
                
                message = payment.confirm_payment(txn_hash)

        except Exception as e:
            return Response({"error": f"Transaction failed: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        booking.refresh_from_db()

        return Response({
            "message": message,
            "booking": BookingPaymentSerializer(booking).data
        }, status=status.HTTP_200_OK)


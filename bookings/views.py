from .serializers import CourtSerializer, TimeSlotSerializer, GenerateSlotSerializer, BookingSlotSerializer, BookingSerializer, CreateBookingSerializer
from .models import FutsalCourt, TimeSlot, Booking, BookingSlot, BookingCancellation
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.response import Response
from django.db import transaction
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
import nepali_datetime
from datetime import datetime

User = get_user_model()


class CourtView(APIView):
    # permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        courts = FutsalCourt.objects.all()
        
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

        admin = User.objects.filter(role__role_name__iexact='Admin').first()

        if not admin:
            return Response('admin not found', status=status.HTTP_400_BAD_REQUEST)

        new_court = admin.manage_futsal_courts(action='create', **serializer.validated_data)
         
        return Response(CourtSerializer(new_court).data, status=status.HTTP_201_CREATED)


class CourtDetailView(APIView):
        
    def get(self, request, pk):

        court = get_object_or_404(FutsalCourt, pk=pk)

        return Response(court.view_details(), status=status.HTTP_200_OK)
    

    def put(self, request, pk):
        court = get_object_or_404(FutsalCourt, pk=pk)

        serializer = CourtSerializer(court, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        admin = User.objects.filter(role__role_name__iexact='Admin').first()

        if not admin:
            return Response('admin not found', status=status.HTTP_400_BAD_REQUEST)

        update_court = admin.manage_futsal_courts(action='update', court_id=court.id, **serializer.validated_data)

        return Response(CourtSerializer(update_court).data, status=status.HTTP_200_OK)
    

    def delete(self, request, pk):
        court = get_object_or_404(FutsalCourt, pk=pk)

        admin = User.objects.filter(role__role_name__iexact='Admin').first()
        
        if not admin:
            return Response('admin not found', status=status.HTTP_400_BAD_REQUEST)


        del_court = admin.manage_futsal_courts(action='delete', court_id=court.id)

        return Response({'message': del_court}, status=status.HTTP_200_OK)
    


class TimeSlotListView(APIView):

    def get(self, request):

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
                return Response('Invalid date, Use YYYY-MM-DD format', status=status.HTTP_400_BAD_REQUEST)


        if available is not None:
            if available.lower() == 'true':
                queryset = queryset.filter(is_available=True)
            
            elif available.lower() == 'false':
                queryset = queryset.filter(is_available=False)
        

        if not queryset.exists():
            return Response('no record match', status=status.HTTP_200_OK)
        
        serializer = TimeSlotSerializer(queryset, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    


class CourtSlotGetView(APIView):

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
            return Response('related date not found', status=status.HTTP_404_NOT_FOUND)
            
        serializer = TimeSlotSerializer(queryset, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    
    

class GenerateSlotView(APIView):

    def post(self, request, court_id):

        data = request.data.copy() # .copy() creates a mutable (editable) clone of that request data so can safely inject fields before passing them to the serializer.
        data['court_id'] = court_id

        serializer = GenerateSlotSerializer(data=data)
        serializer.is_valid(raise_exception=True)

        admin = User.objects.filter(role__role_name__iexact='Admin').first()

        if not admin:
            return Response('admin not found', status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data

        court_instance = get_object_or_404(FutsalCourt, id=court_id)

        try:
            slots_created = admin.manage_time_slots(
                court_instance=court_instance,
                start_date=data.get('start_date'),
                end_date=data.get('end_date'),
                start_time=data['start_time'],
                end_time=data['end_time'],
                duration_hours=data['duration_hours']
            )
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        
        if slots_created == 0:
            return Response('slot times already exist for this court', status=status.HTTP_200_OK)
        
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

    def get(self, request):
        player = User.objects.filter(role__role_name__iexact='Player').first()
        if not player:
            return Response('Player not found', status=status.HTTP_404_NOT_FOUND)
        
        booking = Booking.objects.filter(user=player).prefetch_related('booking_slots__timeslot__court')
        serializer = BookingSerializer(booking, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
    

    def post(self, request):
        serializer = CreateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        timeslot_ids = serializer.validated_data['timeslot_ids']

        player = User.objects.filter(role__role_name__iexact='Player').first()

        if not player:
            return Response('player not found', status=status.HTTP_404_NOT_FOUND)
        
        try:
            with transaction.atomic():
                booking = Booking(user=player)
                booking.create_booking()

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

    def post(self, request, slot_id):
        booking_slot = get_object_or_404(BookingSlot, id=slot_id)
        parent_booking = booking_slot.booking

        player = User.objects.filter(role__role_name__iexact='Player').first()

        if parent_booking.user != player:
            return Response("Unauthorized access", status=status.HTTP_403_FORBIDDEN)
        
        if parent_booking.booking_status == 'cancelled':
            return Response("this slots is already cancelled", status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            BookingCancellation.objects.create(
                user = player,
                booking_id = parent_booking.id,
                court_name = booking_slot.timeslot.court.court_name,
                slot_date = booking_slot.timeslot.date,
                slot_range = f"{booking_slot.timeslot.start_time} - {booking_slot.timeslot.end_time}",
                cancellation_type = 'single'
            )

            booking_slot.delete()

            if parent_booking.booking_slots.count == 0:
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

    def post(self, request, booking_id):
        booking = get_object_or_404(Booking, id=booking_id)

        player = User.objects.filter(role__role_name__iexact='Player').first()
        if booking.user != player:
            return Response('Unauthorized action', status=status.HTTP_403_FORBIDDEN)
        
        if booking.booking_status == 'cancelled':
            return Response("this booking is already cancelled", status=status.HTTP_400_BAD_REQUEST)
        
        active_slots = booking.booking_slots.all()

        with transaction.atomic():
            for slot in active_slots:
                BookingCancellation.objects.create(
                    user = player,
                    booking_id = booking.id,
                    court_name = slot.timeslot.court.court_name,
                    slot_date = slot.timeslot.date,
                    slot_time_range = f"{slot.timeslot.start_time} - {slot.timeslot.end_time}",
                    cancellation_type = 'full'
                )

                slot.delete()
            
            booking.booking_status = 'cancelled'
            booking.total_booking_price = 0.00
            booking.advance_deposit = 0.00
            booking.due_later = 0.00
            booking.save()

        booking.refresh_from_db()

        return Response({
            "message" : f'booking id {booking_id} has been cancelled', "booking" : BookingSerializer(booking).data},
            status=status.HTTP_200_OK
        ) 
from rest_framework import generics, permissions

from reservations.serializers import ReservationSerializer


class CreateReservationsAPI(generics.CreateAPIView):
  serializer_class = ReservationSerializer
  permission_classes = (permissions.IsAuthenticated,)

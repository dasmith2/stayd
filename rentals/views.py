from rest_framework import generics, permissions

from rentals.models import Airvatar
from rentals.serializers import AirvatarSerializer


class ListAirvatarsAPI(generics.ListAPIView):
  queryset = Airvatar.objects.all()
  serializer_class = AirvatarSerializer
  permission_classes = (permissions.IsAuthenticated,)


class RetrieveAirvatarAPI(generics.RetrieveAPIView):
  queryset = Airvatar.objects.all()
  serializer_class = AirvatarSerializer
  lookup_field = 'name_slug'

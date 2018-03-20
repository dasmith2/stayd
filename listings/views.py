from rest_framework import generics, permissions
from rest_framework.response import Response

from listings.models import Airvatar
from listings.serializers import ListingSerializer, AirvatarSerializer


class CreateListingsAPI(generics.CreateAPIView):
  serializer_class = ListingSerializer
  permission_classes = (permissions.IsAuthenticated,)


class ListAirvatarsAPI(generics.ListAPIView):
  queryset = Airvatar.objects.all()
  serializer_class = AirvatarSerializer
  permission_classes = (permissions.IsAuthenticated,)


class RetrieveAirvatarAPI(generics.RetrieveAPIView):
  queryset = Airvatar.objects.all()
  serializer_class = AirvatarSerializer
  lookup_field = 'name_slug'

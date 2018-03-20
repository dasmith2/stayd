from rest_framework import generics, permissions

from listings.models import Airvatar
from listings.serializers import ListingSerializer, AirvatarSerializer


class ListingsAPI(generics.CreateAPIView):
  serializer_class = ListingSerializer
  permission_classes = (permissions.IsAuthenticated,)


class AirvatarsAPI(generics.ListAPIView):
  queryset = Airvatar.objects.all()
  serializer_class = AirvatarSerializer
  permission_classes = (permissions.IsAuthenticated,)

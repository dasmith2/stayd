from rest_framework import generics, permissions

from listings.serializers import ListingSerializer


class ListingsAPI(generics.CreateAPIView):
  serializer_class = ListingSerializer
  permission_classes = (permissions.IsAuthenticated,)

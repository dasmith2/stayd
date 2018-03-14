from rest_framework import generics, permissions

from pays.serializers import PaypalPayinSerializer


class PaypalPayinsAPI(generics.CreateAPIView):
  serializer_class = PaypalPayinSerializer
  permission_classes = (permissions.IsAuthenticated,)

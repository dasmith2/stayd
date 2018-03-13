from rest_framework import serializers
from reservations.models import Guest


class GuestSerializer(serializers.ModelSerializer):
  class Meta:
    model = Guest
    exclude = ('id',)

from rest_framework import serializers
from rentals.models import Airvatar


class AirvatarSerializer(serializers.ModelSerializer):
  class Meta:
    model = Airvatar
    exclude = ('id',)

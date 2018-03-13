from rest_framework import serializers
from rentals.models import Rental


class RentalSerializer(serializers.ModelSerializer):
  class Meta:
    model = Rental
    fields = ('__all__')

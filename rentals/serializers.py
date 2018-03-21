from rest_framework import serializers
from rentals.models import Rental


class RentalSerializer(serializers.ModelSerializer):
  def load_from_db_and_update(self, validated_data):
    rentals = Rental.objects.filter(
        airbnb_address_scrape=validated_data['airbnb_address_scrape'])
    if len(rentals):
      rental = Rental(
          pk=rentals[0].pk, time_zone=rentals[0].time_zone,
          currency=rentals[0].currency, **validated_data)
    else:
      rental = Rental(**validated_data)
    rental.save()
    return rental

  class Meta:
    model = Rental
    exclude = ('id', 'time_zone', 'currency')

from rest_framework import serializers
from listings.models import Listing, Airvatar
from rentals.models import Rental
from rentals.serializers import RentalSerializer


class ListingSerializer(serializers.ModelSerializer):
  rental = RentalSerializer()
  airvatar_name = serializers.CharField(required=True)

  def create(self, validated_data):
    validated_data['rental'] = self._get_rental(validated_data['rental'])
    validated_data['airvatar'] = Airvatar.objects.get(
        name=validated_data['airvatar_name'])
    del validated_data['airvatar_name']
    listings = Listing.objects.filter(
        channel_listing_id=validated_data['channel_listing_id'])
    if len(listings):
      listing = Listing(pk=listings[0].pk, **validated_data)
    else:
      listing = Listing(**validated_data)
    listing.save()
    return listing

  def _get_rental(self, validated_data):
    rentals = Rental.objects.filter(
        airbnb_address_scrape=validated_data['airbnb_address_scrape'])
    if len(rentals):
      rental = Rental(pk=rentals[0].pk, **validated_data)
    else:
      rental = Rental(**validated_data)
    rental.save()
    return rental

  class Meta:
    model = Listing
    exclude = ('id',)

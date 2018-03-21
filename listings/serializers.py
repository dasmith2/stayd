from rest_framework import serializers
from listings.models import Listing, Airvatar
from rentals.serializers import RentalSerializer


class AirvatarSerializer(serializers.ModelSerializer):
  class Meta:
    model = Airvatar
    exclude = ('id',)


class ListingSerializer(serializers.ModelSerializer):
  rental = RentalSerializer()
  airvatar_name = serializers.CharField(required=True)

  def load_from_db_and_update(self, validated_data):
    validated_data['rental'] = RentalSerializer().load_from_db_and_update(
        validated_data['rental'])
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

  def create(self, validated_data):
    """ This is for the benefit of the ModelSerializer realizing the API
    should allow creation. """
    return self.load_from_db_and_update(validated_data)

  class Meta:
    model = Listing
    exclude = ('id',)

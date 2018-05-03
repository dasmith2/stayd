from rest_framework import serializers

from guests.serializers import GuestSerializer
from listings.models import Listing
from reservations.models import Reservation, ReservationLineItem
from util.datetime import DatetimeFieldWithoutTZ


class ReservationLineItemSerializer(serializers.ModelSerializer):
  class Meta:
    model = ReservationLineItem
    fields = ('name', 'value')


class ListingNotFoundException(Exception):
  pass


class ReservationSerializer(serializers.ModelSerializer):
  """ We gotta scrape data off Airbnb, serialize it, and send it to our API.
  The server, not the scraper, is responsible for figuring out if we've seen
  that data before. Hence, the serializers purposefully exclude our database
  ids. The scraper has no idea about our internal ids. """
  channel_listing_id = serializers.CharField(required=True)
  guest = GuestSerializer()
  line_items = ReservationLineItemSerializer(many=True)

  # The scraper has no idea about timezones, so let's not serialize with
  # any assumptions about it.
  check_in = DatetimeFieldWithoutTZ()
  check_out = DatetimeFieldWithoutTZ()

  def load_from_db_and_update(self, validated_data):
    reservations = Reservation.objects.filter(
        channel_reservation_id=validated_data['channel_reservation_id'])
    if len(reservations):
      reservation = Reservation(pk=reservations[0].pk, **validated_data)
    else:
      reservation = Reservation(**validated_data)
    reservation.save()
    return reservation

  def create(self, validated_data):
    listing = self._get_listing(validated_data['channel_listing_id'])
    validated_data['listing'] = listing
    del(validated_data['channel_listing_id'])

    validated_data['guest'] = GuestSerializer().load_from_db_and_update(
        validated_data)

    dict_items = validated_data['line_items']
    del(validated_data['line_items'])

    reservation = self.load_from_db_and_update(validated_data)

    self._reconcile_line_items(
        dict_items, reservation.line_items(), reservation)

    return reservation

  def _get_listing(self, channel_listing_id):
    listings = Listing.objects.filter(
        channel_listing_id=channel_listing_id)
    if not len(listings):
      raise ListingNotFoundException()
    return listings[0]

  def _reconcile_line_items(self, new_dict_items, old_line_items, reservation):
    new_item_keys = set(
        (li['name'], li['value']) for li in new_dict_items)
    old_items = dict([
        ((li.name, li.value), li) for li in old_line_items])
    rental = reservation.listing.rental
    for key in new_item_keys:
      if key not in old_items:
        ReservationLineItem.objects.create(
            name=key[0], value=rental.set_currency(key[1]),
            reservation=reservation)
    for key, old_item in old_items.items():
      if key not in new_item_keys:
        old_item.delete()

  class Meta:
    model = Reservation
    exclude = (
        'id', 'listing', 'price_per_night_currency', 'total_payin_currency')

from rest_framework import serializers
from guests.models import Guest, GuestPhoneNumber


class GuestSerializer(serializers.ModelSerializer):
  def load_from_db_and_update(self, validated_data):
    existing = Guest.objects.get_if_exists(**validated_data['guest'])
    if existing:
      guest = Guest(pk=existing.pk, **validated_data['guest'])
    else:
      guest = Guest(**validated_data['guest'])
    guest.save()
    GuestPhoneNumber.objects.create_for_guest(guest)
    return guest

  class Meta:
    model = Guest
    exclude = ('id',)

from rest_framework import serializers
from django.utils.dateparse import parse_datetime


class DatetimeFieldWithoutTZ(serializers.Field):
  def to_representation(self, obj):
    return obj.isoformat()

  def to_internal_value(self, data):
    return parse_datetime(data)

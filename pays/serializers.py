from rest_framework import serializers

from pays.models import PaypalPayin


class PaypalPayinSerializer(serializers.ModelSerializer):
  def create(self, validated_data):
    # Here the scraper IS aware of currency. It's listed on the site.
    # Just go ahead and let Django assign the default time zone to `when`.
    payins = PaypalPayin.objects.filter(
        transaction_id=validated_data['transaction_id'])
    if len(payins):
      payin = PaypalPayin(pk=payins[0].pk, **validated_data)
    else:
      payin = PaypalPayin(**validated_data)
    payin.save()
    return payin

  class Meta:
    model = PaypalPayin
    exclude = ('id',)

from django.dispatch import Signal


post_sync = Signal(providing_args=['instance'])

from django.db.models.signals import ModelSignal
from django.dispatch import Signal


post_sync = Signal(providing_args=['instance'])


# I want to pass kwargs from save to post_save so I can mock dependencies for
# tests. This is an exact copy of post_save.
keys_post_save = ModelSignal(providing_args=[
    'instance', 'raw', 'created', 'using', 'update_fields'], use_caching=True)

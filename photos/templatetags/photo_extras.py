from django import template
from django.conf import settings

from photos.file_types import VALID_IMAGE_TYPES


register = template.Library()


@register.simple_tag
def valid_image_types():
  # Hack: this spits out valid Javascript.
  return str(VALID_IMAGE_TYPES)


@register.simple_tag
def public_images_dir():
  return settings.PUBLIC_IMAGE_HOST


""" There's no need to create def sensitive_images_dir because the sensitive S3
bucket doesn't allow browser requests. The only way to access bytes of a
sensitive image is through the API. """

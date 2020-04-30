import re


JPEG = 'jpeg'
JPG = 'jpg'
JPEG_SUFFIXES = [JPEG, JPG]
JPEG_CONTENT_TYPE = 'image/jpeg'
PNG = 'png'
PNG_CONTENT_TYPE = 'image/png'
VALID_IMAGE_TYPES = [JPEG_CONTENT_TYPE, PNG_CONTENT_TYPE]


def content_type_from_file_name(file_name):
  suffix = _suffix(file_name)
  if suffix:
    if suffix in JPEG_SUFFIXES:
      return JPEG_CONTENT_TYPE
    if suffix == PNG:
      return PNG_CONTENT_TYPE


def suffix_from_file_type(file_type):
  if file_type == JPEG_CONTENT_TYPE:
    return JPG
  if file_type == PNG_CONTENT_TYPE:
    return PNG


def _suffix(file_name):
  found = re.compile(r'\w+$').findall(file_name)
  if found:
    return found[0].lower()

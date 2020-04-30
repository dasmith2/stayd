"""
Given a photo of a credit card, use the Google Cloud API's document text
detection funtion to attempt to locate the credit card number. Draw a red
rectangle over all but the last 4 digits and resave the image.

The idea is to make it impossible for our virtual assistants to steal credit
card numbers by never showing them a full credit card number.

key.json is the Google Cloud API key. It has to be in the directory scripts
run out of.
"""

import argparse
from collections import namedtuple
import io
import re

from django.conf import settings

from google.cloud.vision import types, ImageAnnotatorClient
from PIL import Image, ImageDraw


class CCBlanker(object):
  """ So you have something to Mock in tests. """
  def blank_cc(
      self, input_image_file_name, output_image_file_name,
      image_annotator_client=None):
    return blank_cc(
        input_image_file_name, output_image_file_name,
        image_annotator_client=image_annotator_client)


def blank_cc(
    input_image_file_name, output_image_file_name,
    image_annotator_client=None):
  bounds = get_leading_cc_number_bounds(
      input_image_file_name, image_annotator_client=image_annotator_client)
  image = Image.open(input_image_file_name)
  draw_rectangles(image, bounds)
  image.save(output_image_file_name)


def get_leading_cc_number_bounds(image_file, image_annotator_client=None):
  image_annotator_client = (
      image_annotator_client or ImageAnnotatorClient.from_service_account_json(
          settings.GOOGLE_ACCOUNT_JSON))

  with io.open(image_file, 'rb') as image_file:
    content = image_file.read()
  image = types.Image(content=content)

  response = image_annotator_client.document_text_detection(image=image)
  document = response.full_text_annotation

  bounds = []
  for page in document.pages:
    for block in page.blocks:
      for paragraph in block.paragraphs:
        words = []
        for google_word in paragraph.words:
          word_str = ''.join(symbol.text for symbol in google_word.symbols)
          words.append(Word(word_str, google_word.bounding_box))
        last_was_4_digit_number = False
        for word in reversed(words):
          if is_gt4_digit_number(word):
            if last_was_4_digit_number:
              bounds.append(word.bounding_box)
            last_was_4_digit_number = True
          else:
            last_was_4_digit_number = False
  return bounds


def is_gt4_digit_number(word):
  return len(word.word_str) >= 4 and bool(
      re.compile(r'^\d+$').match(word.word_str))


Word = namedtuple('Word', 'word_str bounding_box')


def draw_rectangles(image, bounds):
  draw = ImageDraw.Draw(image)
  x_size, y_size = image.size
  for bound in bounds:
    draw_rectangle(draw, bound, x_size, y_size)


def draw_rectangle(draw, bound, x_size, y_size):
  """ I expand the box a litte bit just because the bounding box tends to let a
  little bit of the number leak around the outside. """
  min_x, max_x, min_y, max_y = expand_rectangle(bound, x_size, y_size)
  draw.polygon([
      min_x, min_y,
      min_x, max_y,
      max_x, max_y,
      max_x, min_y], 'red', 'red')


def expand_rectangle(bound, x_size, y_size, factor=.08):
  min_x, max_x, min_y, max_y = None, None, None, None
  for vertex in bound.vertices:
    if not min_x or vertex.x < min_x:
      min_x = vertex.x
    if not max_x or vertex.x > max_x:
      max_x = vertex.x
    if not min_y or vertex.y < min_y:
      min_y = vertex.y
    if not max_y or vertex.y > max_y:
      max_y = vertex.y
  x_delta = int(factor * (max_x - min_x))
  y_delta = int(factor * (max_y - min_y))
  min_x -= x_delta
  max_x += x_delta
  min_y -= y_delta
  max_y += y_delta
  if min_x < 0:
    min_x = 0
  if min_y < 0:
    min_y = 0
  if max_x >= x_size:
    max_x = x_size - 1
  if max_y >= y_size:
    max_y = y_size - 1
  return min_x, max_x, min_y, max_y


if __name__ == '__main__':
  """ python cc_blanker.py input_file.jpg output_file.jpg """
  parser = argparse.ArgumentParser()
  parser.add_argument('input_image', help='The image for text detection.')
  parser.add_argument('output_image', help='The output image')
  args = parser.parse_args()

  blank_cc(args.input_image, args.output_image)

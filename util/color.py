"""
This is handy for a table where every cell has a value between 2 extremes and
you want to color code the cells to make it easy to visualize the data.

Let's say all your data falls between the values 0 and 20. You want 0 to look
red (bad!), you want 20 to look green (good!) and you want 10 to look yellow
(caution!). You could do something like
"""


def value_to_color(min_color, min_value, max_color, max_value, value):
  # First normalize the values so min is at 0. This makes the math easy.
  delta = 0 - min_value
  min_value += delta
  max_value += delta
  value += delta

  middle = (min_value + max_value) / 2
  min_weight = 1
  max_weight = 1
  if value < middle:
    max_weight = 1 - (middle - value) / middle
  elif value > middle:
    min_weight = (max_value - value) / middle
  return combine_colors(min_color, min_weight, max_color, max_weight)


def combine_colors(color_a, color_a_weight, color_b, color_b_weight):
  """
  'f00' == combine_colors('f00', 1, '00f', 0)
  'f07' == combine_colors('f00', 1, '00f', .5)
  'f0f' == combine_colors('f00', 1, '00f', 1)
  '70f' == combine_colors('f00', .5, '00f', 1)
  '00f' == combine_colors('f00', 0, '00f', 1)
  """
  if color_a_weight < 0 or 1 < color_a_weight or (
      color_b_weight < 0 or 1 < color_b_weight):
    raise Exception((
        'color_a_weight {} and color_b_weight {} should both be '
        '>= 0 and <= 1.').format(color_a_weight, color_b_weight))
  ac = color_2_channels(color_a)
  bc = color_2_channels(color_b)
  baseline = min(ac + bc)
  acb = list(channel - baseline for channel in ac)
  bcb = list(channel - baseline for channel in bc)
  acbw = list(round(channel * color_a_weight) for channel in acb)
  bcbw = list(round(channel * color_b_weight) for channel in bcb)
  new_channels = list(baseline + acbw[i] + bcbw[i] for i in range(3))
  return channels_2_color(new_channels)


def channels_2_color(channels):
  return ''.join(str(hex(channel))[-1] for channel in channels)


def color_2_channels(color):
  return list(int(channel, 16) for channel in list(color))

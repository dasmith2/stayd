from collections import namedtuple
from decimal import Decimal
import types

from djmoney.money import Money

from rentals.models import Rental
from stats.models.getter import StatsGetter


class PointList(namedtuple('PointList', 'title points')):
  pass


COMBINE = 'combine'
SEPARATE = 'separate'


def _get_point_lists(
    from_date, to_date, interval, combine_or_separate, rental_ids):
  point_lists = []
  for rental_id in rental_ids:
    rental = Rental.objects.get(pk=rental_id)
    points = StatsGetter().get_stats(
        from_date, to_date, interval, rental_id=rental_id)
    point_lists.append(PointList(rental.nickname, points))
  if combine_or_separate == SEPARATE:
    return point_lists
  elif combine_or_separate == COMBINE:
    aggregate_list = PointList('Combined units', point_lists[0].points)
    point_list_len = len(aggregate_list.points)
    for point_list in point_lists[1:]:
      if point_list_len != len(point_list.points):
        raise Exception((
            'Point lists have different lengths! {} != {} '
            'with parameters {} {} {} {}').format(
                point_list_len, len(point_list.points),
                from_date, to_date, interval, rental_ids))
      for i in range(len(point_list.points)):
        aggregate_list.points[i].add(point_list.points[i])
    return [aggregate_list]
  else:
    raise Exception(combine_or_separate)


def write_csv(
    writer, from_date, to_date, interval, combine_or_separate,
    rental_ids, seriesies):
  point_lists = _get_point_lists(
      from_date, to_date, interval, combine_or_separate, rental_ids)

  headers = ['Date']
  for series in seriesies:
    for points in point_lists:
      headers.append('{} {}'.format(points.title, series))
  writer.writerow(headers)

  for i in range(len(point_lists[0].points)):
    next_row = [point_lists[0].points[i].from_date.isoformat()]
    for series in seriesies:
      for point_list in point_lists:
        point = point_list.points[i]
        value = getattr(point, series)
        if isinstance(value, types.MethodType):
          value = value()
        if isinstance(value, Money):
          value = round(value.amount, 2)
        if isinstance(value, Decimal):
          value = round(float(value), 2)
        if series == 'occupancy_rate':
          # I'm told Excel acts smarter when you put a literal percent sign
          # after percentages.
          value = '{}%'.format(value)
        next_row.append(value)
    writer.writerow(next_row)

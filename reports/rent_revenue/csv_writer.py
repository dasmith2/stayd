from collections import namedtuple
import types

from djmoney.money import Money

from rentals.models import Rental
from reports.rent_revenue.time_series import get_points


class PointList(namedtuple('PointList', 'title points')):
  pass


def _get_point_lists(
    from_date, to_date, interval, all_units_aggregate, cities, rental_ids):
  point_lists = []
  if all_units_aggregate:
    point_lists.append(
        PointList('All units', get_points(from_date, to_date, interval)))
  if cities:
    for city in cities:
      point_lists.append(PointList(
          city, get_points(from_date, to_date, interval, city=city)))
  if rental_ids:
    for rental_id in rental_ids:
      rental = Rental.objects.get(pk=rental_id)
      points = get_points(from_date, to_date, interval, rental_id=rental_id)
      point_lists.append(PointList(rental.nickname, points))
  return point_lists


def write_csv(
    writer, from_date, to_date, interval, all_units_aggregate, cities,
    rental_ids, seriesies):
  point_lists = _get_point_lists(
      from_date, to_date, interval, all_units_aggregate, cities, rental_ids)

  headers = ['Date']
  for points in point_lists:
    for series in seriesies:
      headers.append('{} {}'.format(points.title, series))
  writer.writerow(headers)

  for i in range(len(point_lists[0].points)):
    next_row = [point_lists[0].points[i].from_date.isoformat()]
    for point_list in point_lists:
      for series in seriesies:
        point = point_list.points[i]
        value = getattr(point, series)
        if isinstance(value, types.MethodType):
          value = value()
        if isinstance(value, Money):
          next_row.append(value.amount)
        else:
          next_row.append(str(value))
    writer.writerow(next_row)

from django.db import connection


def get_pairs(query, klass1, klass2):
  """
  Things like
  Reservation.objects.filter(rental__is_active=True).select_related('rental')
  make total sense for the ORM.

  But sometimes you want to ask a much more complicated question that can't be
  answered with simple joins. Like, which payments don't have a transaction yet
  but COULD have a transaction because they happen to match the date and amount
  of existing transactions. The Django ORM tends to turn those sorts of tasks
  into N database lookups and/or a bunch of rather incomprehensible ORM code.

  This function allows you to compute long lists of complex object pairs in 3
  queries.

  Query should select just 2 columns, one of ids for the first class and one of
  ids for the second class.
    SELECT pay.id AS pay_id, transact.id AS transact_id
    FROM pay
    LEFT OUTER JOIN transact ON <complicated join situation>
    WHERE <complicated where situation>

  Then you can
  for my_pay, my_transact in get_pairs(query, Pay, Transact):
    my_pay.transact = my_transact
    my_pay.save()
  """
  with connection.cursor() as cursor:
    cursor.execute(query)
    klass1_ids = set()
    klass2_ids = set()
    id_pairs = cursor.fetchall()
    for (klass1_id, klass2_id) in id_pairs:
      klass1_ids.add(klass1_id)
      klass2_ids.add(klass2_id)
    klass1_lookup = get_object_lookup(klass1, klass1_ids)
    klass2_lookup = get_object_lookup(klass2, klass2_ids)
    to_return = []
    for (klass1_id, klass2_id) in id_pairs:
      to_return.append((
          klass1_lookup[klass1_id],
          klass2_lookup[klass2_id]))
    return to_return


def get_related_object_list_lookup(query, klass1, klass2):
  """ Calling this with, like, (SELECT user.id, book.id FROM ..., User, Book)
  will return {Bob -> [Dune, Ender's Game], Fatima -> [Game of Thrones]} """
  lookup = {}
  for key_obj, list_obj in get_pairs(query, klass1, klass2):
    if key_obj not in lookup:
      lookup[key_obj] = []
    lookup[key_obj].append(list_obj)
  return lookup


def get_object_lookup(klass, keys, key_column_name='pk'):
  """
  This helps cut down on a little boilerplate when doing things like
  some_primary_keys = []
  for row in SELECT some_id FROM <complicated query>
    some_primary_keys.append(some_id)
  some_lookup = get_object_lookup(Some, some_primary_keys)
  my_something = some_lookup[a_primary_key]
  """
  lookup = {}
  # Most of the time this is {'pk__in': keys}
  kwargs = {'{}__in'.format(key_column_name): keys}
  for obj in klass.objects.filter(**kwargs):
    # Most of the time this is lookup[obj.pk] = obj
    lookup[getattr(obj, key_column_name)] = obj
  return lookup

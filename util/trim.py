def trim(self, thing):
  """ {'a': None, 'b': [None, {'c': None, 'd': 'e'}], 'd': []} ->
  {'b': [{'d': 'e'}]}
  This is useful for inspecting APIs which return a slew of empty fields. """
  if isinstance(thing, dict):
    remove_keys = []
    for key, value in thing.items():
      if value is None:
        remove_keys.append(key)
      elif isinstance(value, dict):
        new_value = self._trim_none(value)
        if new_value:
          thing[key] = new_value
        else:
          remove_keys.append(key)
      elif isinstance(value, list):
        new_value = list(
            filter(None, [self._trim_none(item) for item in value]))
        if new_value:
          thing[key] = new_value
        else:
          remove_keys.append(key)
    for key in remove_keys:
      del thing[key]
  elif isinstance(thing, list):
    return [self._trim_none(item) for item in thing]
  return thing

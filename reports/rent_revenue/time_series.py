import json

from reports.rent_revenue.util import DAY, WEEK, MONTH, ResStats


class Point(ResStats):
  """ This is ALMOST exactly the same object as stats.models.stats.Stats. I
  am this close to removing this object entirely. """
  def __init__(self, from_date, interval, **kwargs):
    self.from_date = from_date
    self.interval = interval
    super().__init__(**kwargs)

  def get_from_date_str(self):
    return self.from_date.strftime('%Y-%m-%d')

  def get_label(self):
    if self.interval == DAY:
      return self.from_date.strftime('%a %b %d')
    elif self.interval == WEEK:
      return self.from_date.strftime('%b %d')
    elif self.interval == MONTH:
      return self.from_date.strftime('%b %Y')

  def to_dict(self):
    return_me = super().to_dict()
    return_me['label'] = self.get_label()
    return return_me

  def to_json(self):
    return json.dumps(self.to_dict())

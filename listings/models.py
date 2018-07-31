from django.db import models


class Listing(models.Model):
  """ This class is now totally defunct and should go away,
  but removing it altogether causes incomprehensible errors when
  you run tests, so we'll have to wait for the next time we do
  a migration compression. """
  pass

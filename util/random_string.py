import secrets
import string


def random_string(length=7):
  choices = string.ascii_uppercase + string.digits
  return ''.join(secrets.choice(choices) for _ in range(length))


def get_new_random_string():
  """
  Use this like
  webhook_tag = models.CharField(
      max_length=20, default=get_new_random_string, help_text=(
          'Helpful for giving source_whatever_ids to things.'))
  """
  return random_string(7)

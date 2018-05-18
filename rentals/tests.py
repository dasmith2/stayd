from rentals.models import Rental, Owner, Airvatar


def get_test_owner(create, **kwargs):
  owner = Owner(
      name=kwargs.get('name', 'The queen of England'),
      email=kwargs.get('email', 'thequeenofengland@gmail.com'))
  if create:
    owner.save()
  return owner


def get_test_rental(create, **kwargs):
  owner = get_test_owner(create, **kwargs)
  airvatar = get_test_airvatar(create, **kwargs)
  rental = Rental(
      airbnb_address_scrape=kwargs.get(
          'airbnb_address_scrape', '254 Penwipper Dr., Bismund, Montana'),
      city=kwargs.get('city', 'Bismund'),
      time_zone=kwargs.get('time_zone', 'US/Central'),
      currency=kwargs.get('currency', 'USD'),
      accommodates=kwargs.get('accommodates', 2),
      bathrooms=kwargs.get('bathrooms', 1),
      bedrooms=kwargs.get('bedrooms', 1),
      property_type=kwargs.get('property_type', 'Apartment'),
      room_type=kwargs.get('room_type', 'Entire home/apt'),
      owner=kwargs.get('owner', owner),
      airvatar=kwargs.get('airvatar', airvatar))
  if create:
    rental.save()
  return rental


def get_test_airvatar(create, **kwargs):
  # Airvatars should definitely be in place already, so by default let's
  # return saved ones.
  name = kwargs.get('airvatar_name', 'Ron Burgundy')
  airvatars = Airvatar.objects.filter(name=name)
  if len(airvatars):
    return airvatars[0]
  airvatar = Airvatar(
      name=name,
      ip=kwargs.get('ip', '127.0.0.1'),
      port=kwargs.get('port', '123456'),
      gmail_address=kwargs.get('gmail_address', 'ron_burgundy@gmail.com'),
      gmail_password=kwargs.get('gmail_password', 'thatescalatedquickly'),
      airbnb_password=kwargs.get('airbnb_password', 'imnotevenmad'),
      front_channel=kwargs.get('front_channel', 'cha_637r'))
  if create:
    airvatar.save()
  return airvatar

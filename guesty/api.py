from datetime import time
import json
import re

from django.conf import settings
from django.db import IntegrityError
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, now
from djmoney.money import Money

from errors.models import ErrorLogger
from guest_messages.models import Message, ReservationSyncer
from guests.models import Guest
from guesty.api_getter import GuestyAPIGetter
from guesty.custom_fields import CustomFields
from guesty.front_contact_updater import FrontContactUpdater
from guesty.models import GuestyRental, GuestyReservation, GuestyGuest
from listings.models import Listing
from rentals.models import Rental
from reservations.models import Reservation, ReservationLineItem
from util.channels import AIRBNB, GUESTY, BOOKINGCOM, SHORT_CHANNEL_NAMES


"""
This SHOULD be guesty/guesty.py#class Guesty, and guesty/api.py SHOULD
contain what's in api_getter.py

Guesty is our Channel Manager, meaning it helps us interface with all the
channels such as Airbnb and Booking.com. We can't get access to the Airbnb
API, not in a straightforward sane above board way anyway. Guesty is also our
property management system (PMS).

This file has all our logic for talking with Guesty. For instance, it knows
how to sync reservations.

The following section is just for helper functions that make working in the
shell easier.
"""


def delete_me():
  r_long = get_one(Reservation, '5b168599fedfdd001ff0c03e')
  gs = GuestySync()
  return gs.sync_reservation(r_long)


def gget(url):
  """ gget('reservations') """
  return GuestyAPIGetter().get(url)


def gpost(url, data):
  return GuestyAPIGetter().post(url, data)


def gput(url, data):
  return GuestyAPIGetter().put(url, data)


def get_one(type_of_thing, guesty_id):
  """ get_one(Reservation, '5adf4893a67833002fae7393') """
  return GuestyAPIGetter().get_one(type_of_thing, guesty_id)


def get_all(type_of_thing):
  return GuestyAPIGetter().get_all(type_of_thing)


def get_json_for_reservation(reservation):
  guesty_id = GuestyReservation.objects.get(reservation=reservation).guesty_id
  return get_one(Reservation, guesty_id)


def sync_reservation(guesty_id):
  api_getter = GuestyAPIGetter()
  r = api_getter.get_one(Reservation, guesty_id)
  return GuestySync(api_getter).sync_reservation(r, True)


def sync_all_reservations(skip=0):
  GuestySync().sync_all_reservations(skip=skip, verbose=True)


"""
These are classes which are good for unit testing, wiring into the server,
and so on.
"""


GUESTY_EVENTS = [
    'guest.created',
    'guest.deleted',
    'guest.updated',
    'listing.new',
    'listing.updated',
    'listing.removed',
    'payments.failed',
    'reservation.messageReceived',
    'reservation.new',
    'reservation.updated',
    'reservation.messageSent',
    'reservation.reviewed',
    'task.created',
    'task.deleted',
    'task.updated']


class GuestySync(ReservationSyncer):
  def __init__(self, api_getter=GuestyAPIGetter()):
    self.api_getter = api_getter

  def handle_raw_event(self, raw_event):
    data = json.loads(raw_event.json)
    handled = False
    event_name = raw_event.event_name
    if event_name.find('reservation') >= 0 and 'reservation' in data:
      reservation = self.sync_reservation(data['reservation'])
      # I used to try to update front only when
      # event_name == 'reservation.new' but then it turned out all new
      # reservations are status='inquiry' so there was no point.
      if reservation:
        raw_event.reservation = reservation
        FrontContactUpdater().update_for_guest(reservation.guest)
        handled = 'I synced this reservation.'
      else:
        handled = (
            'I didn\'t bother to sync this reservation, probably because '
            'the status is inquiry or something.')
    elif event_name.find('listing') >= 0 and 'listing' in data:
      # This used to be self.sync_listing(data['listing']) but
      # sometimes the listing.updated event is just, like, {"listing": {"_id":
      # "5af600adf78694001ba03984", "accountId": "5af3858b36385d001f17fea0",
      # "customFields": []}, "event": "listing.updated"}
      self.sync_listing(data['listing']['_id'])
      handled = 'I synced this listing.'
    if handled:
      raw_event.handled = True
      raw_event.handled_at = now()
      raw_event.save()
    return handled

  def sync_listings(self, skip=0, verbose=False):
    self._sync_things(Listing, skip, verbose)

  def sync_all_reservations(self, skip=0, verbose=False):
    self._sync_things(Reservation, skip, verbose)

  def sync_upcoming_reservations(self, verbose=False):
    for guesty_reservation in GuestyReservation.objects.filter(
        reservation__check_out__gte=now()).select_related(
            'reservation').order_by('reservation__check_out'):
      if verbose:
        print('Syncing {}, checking out on {}'.format(
            guesty_reservation.guesty_id,
            guesty_reservation.reservation.check_out))
      self.sync_reservation(self.api_getter.get_one(
          Reservation, guesty_reservation.guesty_id))

  def _handle_custom_fields(self, reservation, custom_fields):
    if reservation.id_verified != custom_fields.id_verified():
      reservation.id_verified = custom_fields.id_verified()
      reservation.save()
    if reservation.guest.email != custom_fields.email_provided():
      reservation.guest.email = custom_fields.email_provided()
      reservation.guest.save()
    provided_phone = custom_fields.phone_provided()
    if provided_phone and reservation.guest.phone != provided_phone:
      reservation.guest.set_primary_phone(provided_phone)
    if custom_fields.paid_in_full() != reservation.is_paid_in:
      custom_fields.set_paid_in_full(reservation.is_paid_in)
    if custom_fields.credit_card_authorization_valid() != bool(
        reservation.security_deposit):
      custom_fields.set_credit_card_authorization_valid(bool(
          reservation.security_deposit))
    custom_fields.send_changes(self.api_getter)

    self._handle_message_custom_fields(reservation, custom_fields)

  def _handle_message_custom_fields(self, reservation, custom_fields):
    sms_enabled = custom_fields.sms_enabled()
    for message in Message.objects.get_for_reservation(reservation):
      specific_enabled = sms_enabled and custom_fields.get(
          message.guesty_custom_field_id, True)
      if message.green_light != specific_enabled:
        message.green_light = specific_enabled
        message.save()

  def sync_stayd_reservation(self, reservation):
    # There are sometimes two of these. What the heck!
    guestvation = GuestyReservation.objects.filter(
        reservation=reservation).first()
    guesty_id = guestvation.guesty_id
    guesty_r = self.api_getter.get_one(Reservation, guesty_id)
    return self.sync_reservation(guesty_r)

  def alert_send_sms_failed(self, reservation):
    custom_fields = self._get_custom_fields_for_reservation(reservation)
    custom_fields.set_send_sms_failed()
    custom_fields.send_changes(self.api_getter)

  def _get_custom_fields_for_reservation(self, reservation):
    guestvation = GuestyReservation.objects.get(reservation=reservation)
    guesty_id = guestvation.guesty_id
    guesty_r = self.api_getter.get_one(Reservation, guesty_id)
    return CustomFields(
        Reservation, guesty_id, guesty_r['customFields'])

  def sync_reservation(self, r_short, verbose=False):
    guesty_id = r_short['_id']
    if 'money' in r_short:
      r_long = r_short
    else:
      r_long = self.api_getter.get_one(Reservation, guesty_id)

    status = r_long['status']
    if status in (
        'inquiry', 'declined', 'closed', 'reserved', 'awaiting_payment'):
      # These cases have no confirmation code. I discovered each of them
      # by catching the errors that happened when I got webhooks with these
      # statuses. You can also see a list of statuses at
      # https://docs.guesty.com/#reservations but that list isn't super helpful
      # because it doesn't describe the circumstances.
      return

    channel_id = r_short['confirmationCode']
    reservation = Reservation.objects.filter(
        channel_reservation_id=channel_id).first()

    if status == 'canceled':
      if reservation:
        reservation.status = status
        reservation.save()
        if verbose:
          print('  Setting status to {}, but that\'t it.'.format(status))
      elif verbose:
        print('  Not syncing. The status is {}'.format(status))
      return

    if not reservation:
      reservation = Reservation(channel_reservation_id=channel_id)

    custom_fields = CustomFields(
        Reservation, r_long['_id'], r_long['customFields'])
    guesty_guest = self.api_getter.get_one(Guest, r_long['guestId'])
    # The email situation is a bit confusing. Guesty's guest object has an
    # anonymized channel email, not the guests's actual email. We can get the
    # guest's actual email, but that's custom, so it's in a custom field.
    # So I set the anonymized_email of the reservation with the guesty guest
    # object, and set the actual email on our guest object from the
    # custom_fields.
    reservation.guest = self._sync_guest(guesty_guest, custom_fields)
    guesty_email = guesty_guest.get('email', '')
    reservation.anonymized_email = guesty_email

    reservation.check_in = parse_datetime(r_short['checkIn'])
    reservation.check_out = parse_datetime(r_short['checkOut'])
    reservation.booked_at = parse_datetime(r_long['confirmedAt'])

    reservation.planned_arrival = self._get_time(r_long, 'plannedArrival')
    reservation.planned_departure = self._get_time(r_long, 'plannedDeparture')

    reservation.night_count = (
        reservation.check_out.date() - reservation.check_in.date()).days
    reservation.reservation_created = parse_datetime(r_long['createdAt'])
    our_cut = r_long['money']['hostPayout']
    reservation.total_payin = Money(our_cut, r_long['money']['currency'])

    security_deposit = self._get_security_deposit(reservation, r_long)
    reservation.security_deposit = security_deposit
    reservation.cc_last_4, reservation.cc_brand = self._get_last_4_and_cc_type(
        r_long)

    reservation.is_paid_in = r_long['money']['balanceDue'] == 0
    reservation.valid_payments_exist = bool(self._get_payment_with_status(
        r_long, 'SUCCEEDED'))
    reservation.status = status
    if r_long['source'] == 'Airbnb':
      reservation.display_channel = AIRBNB
    elif r_long['source'] == 'BookingCom':
      reservation.display_channel = BOOKINGCOM
    reservation.listing = self._get_listing_from_reservation(r_long)

    try:
      reservation.save()
    except IntegrityError as ex:
      # One time, I saw 26 webhooks for the same reservation in a 4 minute
      # time span. So this is a race. This exception comes from the unique
      # constraint on reservation.channel_reservation_id
      # Just re-run it and this time it'll know to load the existing one.
      if ex.args[0].find('channel_reservation_id'):
        return self.sync_reservation(r_short, verbose=verbose)
      # Otherwise I'm not sure what's up, so use the regular ol' error
      # reporting mechanism.
      raise ex

    Message.objects.create_for_reservation(reservation)

    self._handle_custom_fields(reservation, custom_fields)
    self._sync_reservation_line_items(reservation, r_long)
    # OK, apparently Guesty will destroy and create new objects for the
    # same reservation. I used to just have this here:
    # GuestyReservation.objects.get_or_create(
    #     reservation=reservation, guesty_id=guesty_id)
    # But that was no good because they'd send a totally new guesty_id for
    # the same channel_reservation_id, so I'd end up with two
    # GuestyReservations, the first being invalid.
    existing_gr = GuestyReservation.objects.filter(reservation=reservation)
    if existing_gr:
      existing_gr.update(guesty_id=guesty_id)
    else:
      GuestyReservation.objects.create(
          reservation=reservation, guesty_id=guesty_id)

    # This has to come after the GuestyReservation object is created because
    # the error message includes guesty links.
    self.alert_if_overlap(reservation)
    return reservation

  def alert_if_overlap(self, reservation, error_logger=ErrorLogger()):
    # We have some old imported reservations that are just for reports and
    # have data integrity issues, a.k.a. unit numbers were swapped in one
    # case, causing overlap alerts. Anyway if it's all in the past, who cares.
    for overlap in reservation.get_overlapping().filter(check_out__gte=now()):
      # alert_if_overlap gets called on 'reservation' after its
      # GuestyReservation gets created, so I know this one exists.
      this_guesty = GuestyReservation.objects.get(reservation=reservation)
      # But what it overlaps with, no guarantees there.
      overlap_guesty = GuestyReservation.objects.filter(
          reservation=overlap).first()
      overlap_str = (
          'The overlapping reservation appears not to exist in Guesty. '
          'It\'s reveration {} in Stayd-Web').format(overlap.pk)
      if overlap_guesty:
        overlap_str = overlap_guesty.guesty_url()
      error_logger.log_error(
          'Warning: overlapping reservations detected!!!',
          '{}\n{}'.format(
              this_guesty.guesty_url(), overlap_str),
          extra_to=settings.ALERT_OVERLAPPING_MESSAGES,
          always_new_error=True)

  def _get_security_deposit(self, reservation, r_long):
    messaging_goes_live = make_aware(
        parse_datetime(settings.MESSAGING_GOES_LIVE))
    before_policy = reservation.reservation_created < messaging_goes_live
    if before_policy:
      # If it was before we went live, then this security payment policy
      # wasn't in effect yet.
      return Money(1, 'USD')
    # I assume that any successful hold placed on a card is a security
    # payment.
    return self._get_payment_with_status(
        r_long, 'AUTHORIZATION_HOLD_SUCCEEDED')

  def _get_payment_with_status(self, r_long, status):
    payment = None

    for payment_j in r_long.get('money', {}).get('payments', []):
      pay_status = payment_j.get('status', '')
      if pay_status == status:
        payment = Money(payment_j['amount'], payment_j['currency'])

    return payment

  def _get_last_4_and_cc_type(self, r_long):
    """ This only shows up when a payment was successfully taken by Guesty
    via Stripe. So you don't see this on Airbnb reservations, and you don't
    see it on any reservation where the payment was taken directly on Stripe.
    If a payment fails, the correct thing it do is go click some button I
    heard about on Stripe to white list the payment, then go back to Guesty
    and retry from there. """
    if 'money' in r_long:
      money = r_long['money']
      if 'payments' in money:
        for payment in money['payments']:
          if 'attempts' in payment:
            for attempt in payment['attempts']:
              if 'payload' in attempt:
                payload = attempt['payload']
                if 'source' in payload:
                  source = payload['source']
                  if 'last4' in source and 'brand' in source:
                    return (source['last4'], source['brand'])
    return (None, None)

  def _successful_payment_exists(self, r_long):
    if 'money' in r_long:
      money = r_long['money']
      if 'payments' in money:
        for payment in money['payments']:
          if payment['status'] == 'SUCCEEDED':
            return True
    return False

  def _appears_to_be_anonymized_email(self, email):
    # So, like, @.*(airbnb|booking|homeaway)
    pattern = '@.*(' + '|'.join(SHORT_CHANNEL_NAMES) + ')'
    finder = re.compile(pattern, flags=re.IGNORECASE)
    return bool(finder.findall(email))

  def _get_time(self, r_long, key):
    time_str = r_long.get(key, None)
    if time_str:  # '17:00'
      parts = list(int(p) for p in time_str.split(':'))  # (17, 0)
      return time(*parts)
    return None

  def sync_webhooks(self, server_url, verbose=False, events=GUESTY_EVENTS):
    """ Only production should always have the webhooks turned on now that
    reservation webhooks trigger Front contact information updates, and the
    Front API is rate limited. See front.models.py#Front.set_contact_infos for
    more information. """
    if server_url[-1] == '/':
      server_url = server_url[:-1]

    existing = self.api_getter.get_all('Webhook')
    expected = self._create_missing_webhooks_and_return_expected(
        server_url, existing, events, verbose)
    self._delete_extra_webhooks(server_url, existing, expected, verbose)

  def delete_webhooks(self, server_url, verbose=False):
    for webhook in self.api_getter.get_all('Webhook'):
      if webhook['url'].find(server_url) >= 0:
        if verbose:
          print('Deleting {}'.format(webhook))
        self.api_getter.delete('webhooks/{}'.format(webhook['_id']))

  def _create_missing_webhooks_and_return_expected(
      self, server_url, existing, events, verbose):
    expected = []
    account_ids = self._all_account_ids()
    for event_name in events:
      for account_id in account_ids:
        events = [event_name]
        expected.append({'accountId': account_id, 'events': events})

        found = False
        for exist in existing:
          found = found or all([
              exist['accountId'] == account_id,
              exist['events'] == events,
              exist['url'].find(server_url) >= 0])
        if not found:
          url = server_url + reverse(
              'guesty_webhook', kwargs={'event_name': event_name})
          new_hook = {
              'url': url, 'accountId': account_id, 'events': [event_name]}
          if verbose:
            print('Creating {}'.format(new_hook))
          self.api_getter.post('webhooks', new_hook)
    return expected

  def _delete_extra_webhooks(self, server_url, existing, expected, verbose):
    for exist in existing:
      if exist['url'].find(server_url) >= 0:
        found = False
        for expect in expected:
          accountId_match = exist['accountId'] == expect['accountId']
          events_match = exist['events'] == expect['events']
          if all([accountId_match, events_match]):
            found = True
            break
        if not found:
          if verbose:
            print('Deleting {}'.format(exist))
          self.api_getter.delete('webhooks/{}'.format(exist['_id']))

  def _sync_things(self, type_of_thing, skip, verbose):
    limit = 25
    results = self.api_getter.get_many(type_of_thing, skip, limit)
    while len(results):
      for index, thing in enumerate(results):
        if verbose:
          print('{}. Syncing {} {}'.format(
              index + skip, type_of_thing.__name__, thing['_id']))
        if type_of_thing is Listing or type_of_thing is Rental:
          self.sync_listing(thing)
        elif type_of_thing is Reservation:
          self.sync_reservation(thing, verbose)
        else:
          raise Exception(
              'Not sure what to do with a {}'.format(type_of_thing))
      skip += len(results)
      results = self.api_getter.get_many(type_of_thing, skip, limit)

  def sync_listing(self, listing_data):
    """ Ok, I guess that here "listing" means a Guesty listing, which in our
    terms is a rentals.Rental plus all the listings.Listings. So in this def
    we not only make sure the rental exists, we make sure all the possible
    listings exist. That includes a GUESTY listing which is what's used for
    reservations that get entered manually such as this one:
    https://app.guesty.com/reservations/5b1c4dfe5e1665001f6c7d61/guests

    listing_data can be either a listing dict, or a listing id string. """
    if listing_data.__class__ is str:
      listing_data = self.api_getter.get_one(Listing, listing_data)
    custom_fields = CustomFields(
        Listing, listing_data['_id'], listing_data['customFields'])
    address = listing_data['address']['full']
    rental = Rental.objects.filter(
        airbnb_address_scrape=address).first()
    if not rental:
      rental = Rental(airbnb_address_scrape=address)
    rental.city = listing_data['address']['city']
    rental.time_zone = listing_data['timezone']
    rental.currency = listing_data['prices']['currency']
    rental.accommodates = listing_data['accommodates']
    rental.bathrooms = listing_data['bathrooms']
    rental.bedrooms = listing_data['bedrooms']
    rental.property_type = listing_data['propertyType']
    rental.room_type = listing_data['roomType']
    rental.nickname = listing_data['nickname']
    rental.market_rent = custom_fields.market_rent()
    # isListed is an optional field, but active is always there. You need
    # both to actually actually be active tho haha
    is_listed = listing_data.get('isListed', False)
    rental.is_active = listing_data['active'] and is_listed
    rental.save()
    GuestyRental.objects.get_or_create(
        rental=rental, guesty_id=listing_data['_id'])
    # Always create the GUESTY listing in case anybody ever enters a manual
    # reservation.
    channel_listing_id = listing_data['_id']
    self._create_listing(channel_listing_id, GUESTY, rental, listing_data)
    # Then create a listing for every platform this rental is integrated with.
    for channel in listing_data['integrations']:
      if channel['platform'] == 'airbnb':
        channel_listing_id = channel['airbnb']['id']
        self._create_listing(channel_listing_id, AIRBNB, rental, listing_data)
      elif channel['platform'] == 'bookingCom':
        channel_listing_id = channel['bookingCom']['id']
        self._create_listing(
            channel_listing_id, BOOKINGCOM, rental, listing_data)
      elif channel['platform'] == 'rentalsUnited':
        pass
      else:
        raise Exception((
            'I\'m not sure how to handle {} in the '
            'platform field yet.').format(channel['platform']))

  def _create_listing(self, channel_listing_id, channel, rental, listing_data):
    listing = Listing.objects.filter(rental=rental, channel=channel).first()
    if listing:
      if listing.channel_listing_id != channel_listing_id:
        listing.channel_listing_id = channel_listing_id
        listing.save()
    else:
      listing = Listing(
          channel_listing_id=channel_listing_id, channel=channel,
          rental=rental)
    listing.title = listing_data['title']
    listing.save()
    return listing

  def _get_listing_from_reservation(self, r_long):
    channel = r_long['integration']['platform']
    if channel.title() == AIRBNB:
      channel_listing_id = r_long['integration']['airbnb']['listingId']
    elif channel == 'manual':
      # This is probably just the test listing, so use guesty's id as the
      # channel id.
      channel_listing_id = r_long['listingId']
    elif channel == 'bookingCom':
      channel_listing_id = r_long['integration']['bookingCom']['listingId']
    else:
      raise Exception(
          'I\'m not sure how to handle channel {} yet.'.format(channel))
    listings = Listing.objects.filter(channel_listing_id=channel_listing_id)
    if listings:
      return listings[0]
    self.sync_listing(self.api_getter.get_one(Listing, r_long['listingId']))
    listings = Listing.objects.filter(channel_listing_id=channel_listing_id)
    if listings:
      return listings[0]
    raise Exception((
        'I tried to sync the listing for reservation {} '
        'but no dice.').format(r_long['_id']))

  def _sync_guest(self, guesty_guest, custom_fields):
    if 'airbnb' not in guesty_guest:
      raise Exception('Im not sure how to handle non-airbnb guests yet.')
    channel_id = guesty_guest['airbnb']['id']
    guest = Guest.objects.filter(channel_id=channel_id).first()
    # Reservation 5af79a5b4c226b0061027476 has no phone number.
    phone = guesty_guest.get('phone', '')
    if not guest:
      guest = Guest.objects.filter(
          full_name=guesty_guest['fullName'], phone=phone).first()
    if not guest:
      guest = Guest()
    guest.channel_id = channel_id
    # Yep, encountered one without a first_name.
    guest.first_name = guesty_guest.get('firstName', '')
    guest.last_name = guesty_guest.get('lastName', '')
    guest.full_name = guesty_guest['fullName']
    guest.phone = phone
    guest.airbnb_says_theyre_from = guesty_guest.get('hometown', '')
    guest.email = custom_fields.email_provided()
    guest.save()

    # Apparently Guesty will destroy and create new objects for the
    # same guest, just like reservation. I used to just have this here:
    # GuestyGuest.objects.get_or_create(
    #     guest=guest, guesty_id=guesty_guest['_id'])
    # But that was no good because they'd send a totally new guesty_id for
    # the same guest, the first being invalid.
    guesty_id = guesty_guest['_id']
    existing_gg = GuestyGuest.objects.filter(guest=guest)
    if existing_gg:
      existing_gg.update(guesty_id=guesty_id)
    else:
      GuestyGuest.objects.create(guest=guest, guesty_id=guesty_id)

    return guest

  def _sync_reservation_line_items(self, reservation, r_long):
    ReservationLineItem.objects.filter(reservation=reservation).delete()
    for item in r_long.get('money', {}).get('invoiceItems', []):
      value = Money(item['amount'], item['currency'])
      ReservationLineItem.objects.create(
          name=item['title'],
          value=value,
          reservation=reservation)
      if item['title'] == 'Accommodation fare':
        reservation.price_per_night = value / reservation.night_count
        reservation.save()

  def _all_account_ids(self):
    account_ids = set()

    for listing in self.api_getter.get_all(Listing):
      account_ids.add(listing['accountId'])

    return account_ids

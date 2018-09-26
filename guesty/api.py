from datetime import time
import json
import re

from django.conf import settings
from django.db import IntegrityError
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, now
from djmoney.money import Money

from errors.models import ErrorLogger, Notifier
from guest_messages.models.models import Email, SMS
from guests.models import Guest, GuestPhoneNumber
from guesty.api_getter import GuestyAPIGetter
from guesty.custom_fields import CustomFields
from guesty.models import GuestyRental, GuestyReservation, GuestyGuest
from rentals.models import Rental
from reservations.models import Reservation, ReservationLineItem
from util.channels import (
    BOOKINGCOM, HOMEAWAY, SHORT_CHANNEL_NAMES, CHANNELS, STAYD,
    ONLY_APARTMENTS)
from util.signals import post_sync


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


def gget(url, print_curl=False):
  """ gget('reservations') """
  return GuestyAPIGetter().get(url, print_curl=print_curl)


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


def sync_all_reservations(skip=0, from_date=None, to_date=None):
  GuestySync().sync_all_reservations(
      skip=skip, verbose=True, from_date=from_date, to_date=to_date)


def get_money(guesty_id):
  helpful = [
      'hostPayout', 'balanceDue', 'payments', 'isAuthorizationHold', 'status',
      'currency', 'amount', 'attempts', 'status', 'payload', 'status',
      'source', 'last4', 'exp_year', 'exp_month', 'brand', 'refunds']

  def del_helper(lookup):
    if lookup.__class__ is dict:
      keys = list(lookup.keys())
      for key in keys:
        if key not in helpful:
          del lookup[key]
        elif lookup[key].__class__ is list:
          lookup[key] = [del_helper(item) for item in lookup[key]]
        elif lookup[key].__class__ is dict:
          lookup[key] = del_helper(lookup[key])
    return lookup
  return del_helper(get_one(Reservation, guesty_id)['money'])


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


class GuestySync(object):
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
        handled = 'I synced this reservation.'
      else:
        handled = (
            'I didn\'t bother to sync this reservation, probably because '
            'the status is inquiry or something.')
    elif event_name.find('listing') >= 0 and 'listing' in data:
      # This used to be self.sync_rental(data['listing']) but
      # sometimes the listing.updated event is just, like, {"listing": {"_id":
      # "5af600adf78694001ba03984", "accountId": "5af3858b36385d001f17fea0",
      # "customFields": []}, "event": "listing.updated"}
      # Remember that by "listing" guesty means Rental.
      self.sync_rental(self.api_getter.get_one(Rental, data['listing']['_id']))
      handled = 'I synced this rental.'
    if handled:
      raw_event.handled = True
      raw_event.handled_at = now()
      raw_event.save()
    return handled

  def sync_rentals(self, skip=0, verbose=False):
    self._sync_things(Rental, skip, verbose)

  def sync_all_reservations(
      self, skip=0, verbose=False, from_date=None, to_date=None):
    self._sync_things(Reservation, skip, verbose, from_date, to_date)

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
    messages_enabled = custom_fields.messages_enabled()
    smss = SMS.objects.get_for_reservation(reservation)
    emails = Email.objects.get_for_reservation(reservation)
    messages = list(smss) + list(emails)

    for message in messages:
      guesty_custom_field_id = message.guesty_custom_field_id()
      if guesty_custom_field_id:
        specific_enabled = messages_enabled and custom_fields.get(
            message.guesty_custom_field_id(), True)
        if message.green_light != specific_enabled:
          message.green_light = specific_enabled
          message.save()

  def sync_stayd_reservation(self, reservation):
    guestvation = GuestyReservation.objects.filter(
        reservation=reservation).first()
    guesty_id = guestvation.guesty_id
    guesty_r = self.api_getter.get_one(Reservation, guesty_id)
    return self.sync_reservation(guesty_r)

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

    reservation.check_in = parse_datetime(r_long['checkIn'])
    reservation.check_out = parse_datetime(r_long['checkOut'])
    reservation.booked_at = parse_datetime(r_long['confirmedAt'])

    reservation.planned_arrival = self._get_time(r_long, 'plannedArrival')
    reservation.planned_departure = self._get_time(r_long, 'plannedDeparture')

    reservation.night_count = (
        reservation.check_out.date() - reservation.check_in.date()).days
    reservation.reservation_created = parse_datetime(r_long['createdAt'])
    # Guesty picked a bad variable name here.
    total_payin = r_long['money']['hostPayout']
    currency = r_long['money']['currency']
    reservation.total_payin = Money(total_payin, currency)

    security_deposit = self._get_security_deposit(reservation, r_long)
    reservation.security_deposit = security_deposit
    reservation.cc_last_4, reservation.cc_brand = self._get_last_4_and_cc_type(
        r_long)

    reservation.balance_due = self.get_balance_due(r_long['money'])
    # Sometimes things go wrong and guests overpay.
    reservation.is_paid_in = reservation.balance_due <= Money(0, currency)

    reservation.valid_payments_exist = bool(self._get_payment_with_status(
        r_long, 'SUCCEEDED'))
    reservation.status = status
    reservation.channel = self.get_channel_from_source(r_long['source'])
    reservation.rental = self._get_rental_from_reservation(r_long)

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

    # SMSs and Emails are created via a post save hook.

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

    # These have to come after the GuestyReservation object is created because
    # the error message includes guesty links.
    self.alert_if_overlap(reservation)
    self.alert_if_overpaid(reservation)

    post_sync.send(sender=Reservation, instance=reservation)

    return reservation

  def get_balance_due(self, money):
    """ It'd be great if we could just use the balanceDue attribute, but
    for this reservation, the Guesty UI correctly says a "Balance due" of 0
    while the API incorrectly says a balanceDue of -300.
    https://app.guesty.com/reservations/5b75b2f3f99c1e003a94d55e/guests
    """
    total_due = money['hostPayout']
    currency = money['currency']
    paid = 0
    for payment in money['payments']:
      # I've seen isAuthorizationHold=True and status SUCCEEDED,
      # isAuthorizationHold=True and status AUTHORIZATION_HOLD_SUCCEEDED,
      # and isAuthorizationHold=False and status SUCCEEDED
      if not payment['isAuthorizationHold']:
        if payment['status'] == 'SUCCEEDED':
          paid += payment['amount']
          # For the record, 'refunds' is only optional in api_examples.py.
          # The actual API always includes it.
          for refund in payment.get('refunds', []):
            if refund['status'] == 'SUCCEEDED':
              paid -= refund['amount']
    return Money(total_due - paid, currency)

  def get_channel_from_source(self, source):
    """ OK, webhooks come in one at a time. So if unexpected data shows up,
    it's best to fail now so this reservation doesn't cause unexpected
    failures later. For instance, if this causes a problem during message
    sending, the messages for other valid reservations could get blocked. """
    if source in CHANNELS:
      return source
    if source.lower().find('homeway') >= 0:
      # Yeeeesss this homeway is not a typo. That's what somebody put in the
      # source field. Homeway old booking.
      return HOMEAWAY
    if source == 'BookingCom':
      return BOOKINGCOM
    if source.lower() == 'website':
      return STAYD
    if source == 'oa@oa.oa':
      return ONLY_APARTMENTS
    raise Exception('Unknown channel: \'{}\''.format(source))

  def alert_if_overpaid(self, reservation, notifier=Notifier()):
    if reservation.balance_due < Money(0, reservation.balance_due.currency):
      subject = 'Warning: overpaid reservation for {}'.format(
          reservation.guest.get_name())
      message = '{}\nBalance due: {}'.format(
          reservation.admin_url(), reservation.balance_due)
      notifier.notify(
          settings.ALERT_OVERPAYMENT, subject, message)

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
        overlap_str = overlap_guesty.admin_url()
      error_logger.log_error(
          'Warning: overlapping reservations detected!!!',
          '{}\n{}'.format(
              this_guesty.admin_url(), overlap_str),
          extra_to=settings.ALERT_OVERLAPPING_RESERVATIONS,
          always_new_error=True)

  def _get_security_deposit(self, reservation, r_long):
    messaging_goes_live = make_aware(
        parse_datetime(settings.MESSAGING_GOES_LIVE))
    before_policy = reservation.reservation_created < messaging_goes_live
    if before_policy:
      # If it was before we went live, then this security payment policy
      # wasn't in effect yet.
      return Money(1, 'USD')
    # This came up a surprising amount of times. Tom or McKay would need a way
    # to force the system to recognize the cc as authorized. Sometimes it's for
    # old reservations authorized a long time ago, sometimes it's for test
    # reservations.
    if CustomFields(
        Reservation, None, r_long['customFields']).trust_me_cc_authorized():
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
    Front API is rate limited. """
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

  def _sync_things(
      self, type_of_thing, skip, verbose, from_date=None, to_date=None):
    limit = 25
    results = self.api_getter.get_many(
        type_of_thing, skip, limit, from_date, to_date)
    while len(results):
      for index, thing in enumerate(results):
        if verbose:
          print('{}. Syncing {} {}'.format(
              index + skip, type_of_thing.__name__, thing['_id']))
        if type_of_thing is Rental:
          self.sync_rental(thing)
        elif type_of_thing is Reservation:
          self.sync_reservation(thing, verbose)
        else:
          raise Exception(
              'Not sure what to do with a {}'.format(type_of_thing))
      skip += len(results)
      results = self.api_getter.get_many(
          type_of_thing, skip, limit, from_date, to_date)

  def sync_rental(self, rental_data):
    guesty_rental_id = rental_data['_id']
    guesty_rental = GuestyRental.objects.filter(
        guesty_id=guesty_rental_id).first()
    rental = self._get_rental_object_from_data(
        rental_data, guesty_rental_id, guesty_rental)
    rental.save()
    if not guesty_rental:
      guesty_rental = GuestyRental.objects.create(
          rental=rental, guesty_id=guesty_rental_id)

  def _get_rental_object_from_data(
      self, rental_data, guesty_rental_id, guesty_rental):
    """ rental_data can be either a rental dict, or a guesty id string
    for a rental ("listing" in Guesty vernacular). """
    if rental_data.__class__ is str:
      rental_data = self.api_getter.get_one(Rental, rental_data)
    custom_fields = CustomFields(
        Rental, guesty_rental_id, rental_data['customFields'])
    address = rental_data['address']['full']
    if guesty_rental:
      rental = guesty_rental.rental
    else:
      rental = Rental()
    rental.airbnb_address_scrape = address
    rental.city = rental_data['address']['city']
    rental.time_zone = rental_data['timezone']
    rental.currency = rental_data['prices']['currency']
    rental.accommodates = rental_data['accommodates']
    rental.bathrooms = rental_data['bathrooms']
    rental.bedrooms = rental_data['bedrooms']
    rental.property_type = rental_data['propertyType']
    rental.room_type = rental_data['roomType']
    rental.nickname = rental_data['nickname']

    rental.main_checkin_instructions_link = \
        custom_fields.main_checkin_instructions_link()
    rental.main_property_access_codes_in_order_of_use = \
        custom_fields.main_property_access_codes_in_order_of_use()
    rental.master_access_code_building_door_electronic_lock = \
        custom_fields.master_access_code_building_door_electronic_lock()
    rental.master_access_code_apartment_door_electronic_lock = \
        custom_fields.master_access_code_apartment_door_electronic_lock()
    rental.wifi_network_name = \
        custom_fields.wifi_network_name()
    rental.wifi_password = \
        custom_fields.wifi_password()
    rental.building_trash_instructions = \
        custom_fields.building_trash_instructions()
    rental.link_to_property_page_in_helpdocs = \
        custom_fields.link_to_property_page_in_helpdocs()
    rental.google_maps_link = \
        custom_fields.google_maps_link()
    rental.departure_check_list = \
        custom_fields.departure_check_list()
    rental.local_bag_storage_info = \
        custom_fields.local_bag_storage_info()
    rental.local_bag_storage_link = \
        custom_fields.local_bag_storage_link()
    rental.parking_link = \
        custom_fields.parking_link()
    rental.public_transportation_link = \
        custom_fields.public_transportation_link()
    rental.local_recommendations_link = \
        custom_fields.local_recommendations_link()
    rental.walking_to_nearest_path_stations = \
        custom_fields.walking_to_nearest_path_stations()
    rental.parking_suggestions_no_links = \
        custom_fields.parking_suggestions_no_links()
    rental.public_transport_no_link = \
        custom_fields.public_transport_no_link()
    rental.walk_time_to_nearest_train = \
        custom_fields.walk_time_to_nearest_train()
    rental.laundry_info = \
        custom_fields.laundry_info()
    rental.online_store_available = \
        custom_fields.online_store_available()

    # isListed is an optional field, but active is always there. You need
    # both to actually actually be active tho haha
    is_listed = rental_data.get('isListed', False)
    rental.is_active = rental_data['active'] and is_listed
    return rental

  def _get_rental_from_reservation(self, r_long):
    guesty_rental_id = r_long['listingId']
    # One time during the reservation.reviewed webhook listingId was
    # {'_id': '5af600acf78694001ba03953', 'id': '5af600acf78694001ba03953'}
    if guesty_rental_id.__class__ is dict:
      guesty_rental_id = guesty_rental_id['_id']
    if not GuestyRental.objects.filter(guesty_id=guesty_rental_id):
      self.sync_rental(self.api_getter.get_one(Rental, guesty_rental_id))
    return GuestyRental.objects.filter(
        guesty_id=guesty_rental_id).first().rental

  def _sync_guest(self, guesty_guest, custom_fields):
    if 'airbnb' not in guesty_guest:
      raise Exception('Im not sure how to handle non-airbnb guests yet.')
    channel_id = guesty_guest['airbnb']['id']
    guest = Guest.objects.filter(channel_id=channel_id).first()
    # Reservation 5af79a5b4c226b0061027476 has no phone number.
    phone = guesty_guest.get('phone', '')
    # All numbers seem to come in from Guesty with a country code, but no
    # plus sign. Twilio and Front need that + sign to work properly.
    if phone and phone[0] != '+':
      phone = '+' + phone
    if not guest:
      guest = GuestPhoneNumber.objects.find_guest(
          phone, guesty_guest['fullName'])
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

    for rental in self.api_getter.get_all(Rental):
      account_ids.add(rental['accountId'])

    return account_ids

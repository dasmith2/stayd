from datetime import timedelta
from decimal import Decimal
import json
import re

from django.conf import settings
from django.db import IntegrityError
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware, now
from djmoney.money import Money

from commands.models import background_command
from errors.models import ErrorLogger, log_error, notify, Notifier
from guests.models import Guest, GuestPhoneNumber
from guesty.api import GuestyAPI
from guesty.custom_fields import CustomFields
from guesty.models import (
    GuestyRental, GuestyReservation, GuestyGuest, RawEvent,
    ReservedReservation)
from guesty.sync_payments import sync_payments
from rentals.models import City, Building, Rental, RentalPhoto, Amenity
from reservations.models import Reservation, ReservationLineItem
from util.channels import (
    AIRBNB, BOOKINGCOM, HOMEAWAY, SHORT_CHANNEL_NAMES, CHANNELS, HOWARD,
    ONLY_APARTMENTS, MISTER_B_AND_B, THEY_ASSUME_CC_RISK_CHANNELS,
    CANADA_STAYS)
from util.html_status_codes import ServerError
from util.signals import post_sync
from util.timezone import time_str_to_time
from util.urls import keys_reverse


""" Guesty is our Channel Manager, meaning it helps us interface with all the
channels such as Airbnb and Booking.com. We can't get access to the Airbnb API,
not in a straightforward sane above board way anyway. Guesty is also our
property management system (PMS).

This file has all our logic for talking with Guesty. For instance, it knows how
to sync reservations.

The following section is just for helper functions that make working in the
shell easier. """


@background_command
def reinstall_webhooks_background():
  """ One time, for no good reason and with no warning, Guesty dropped all our
  webhook configuration and we didn't notice for 3 days. So we missed a lot of
  webhooks. So now, just reinstall the webhooks regularly in case that ever
  happens again. """
  try:
    Guesty().sync_webhooks(settings.KEYS_SERVER)
  except ServerError:
    # Ugh, fine. Hopefully it'll just work tomorrow or they won't drop our
    # webhook configuration in the first place.
    pass


def sync_canceled_reservations(skip=0):
  """ Go ahead and delete this ASAP. I'm just using it right now to get all the
  canceled reservations in the prod database that I missed back when I thought
  we could ignore them. """
  api = GuestyAPI()
  api.reservation_status = 'canceled'
  guesty = Guesty(api)
  guesty.sync_all_reservations(skip=skip, verbose=True)


def gget(url, print_curl=False):
  """ gget('reservations') """
  return GuestyAPI().get(url, print_curl=print_curl)


def gpost(url, data):
  return GuestyAPI().post(url, data)


def gput(url, data):
  return GuestyAPI().put(url, data)


def get_one(type_of_thing, guesty_id):
  """ get_one(Reservation, '5adf4893a67833002fae7393') """
  return GuestyAPI().get_one(type_of_thing, guesty_id)


def get_all(type_of_thing):
  return GuestyAPI().get_all(type_of_thing)


def get_json_for_reservation(reservation):
  guesty_id = GuestyReservation.objects.get(reservation=reservation).guesty_id
  return get_one(Reservation, guesty_id)


def sync_reservation(guesty_id, allowed_in_runserver=False):
  api = GuestyAPI()
  r = api.get_one(
      Reservation, guesty_id, allowed_in_runserver=allowed_in_runserver)
  return Guesty(api).sync_reservation(
      r, True, allowed_in_runserver=allowed_in_runserver)


def sync_all_reservations(skip=0, from_date=None, to_date=None):
  Guesty().sync_all_reservations(
      skip=skip, verbose=True, from_date=from_date, to_date=to_date)


def get_reservation(guesty_id):
  return get_one(Reservation, guesty_id)


def get_money(guesty_id):
  return get_one(Reservation, guesty_id)['money']


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


def sync_cc_reservations(start_at_index=0):
  for index, gr in enumerate(GuestyReservation.objects.filter(
      reservation__cc_last_4__isnull=False)):
    if index >= start_at_index:
      print('{}. {}'.format(index, gr.guesty_id))
      sync_reservation(gr.guesty_id)


class Guesty(object):
  def __init__(self, api=GuestyAPI()):
    self.api = api

  def handle_raw_event(self, raw_event):
    data = raw_event.data()
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
      self.sync_rental(self.api.get_one(Rental, data['listing']['_id']))
      handled = 'I synced this rental.'
    if handled:
      raw_event.handled = True
      raw_event.handled_at = now()
      raw_event.save()
    return handled

  def handle_raw_events(self, verbose=False):
    for event in RawEvent.objects.filter(
        created_at__gte=now() - timedelta(days=1), handled_at__isnull=True):
      handled = self.handle_raw_event(event)
      if handled and verbose:
        print(handled)

  def sync_rentals(self, skip=0, verbose=False):
    self._sync_things(Rental, skip, verbose)

  def sync_all_reservations(
      self, skip=0, verbose=False, from_date=None, to_date=None):
    self._sync_things(Reservation, skip, verbose, from_date, to_date)

  def sync_stayd_reservation(self, reservation):
    guestvation = GuestyReservation.objects.filter(
        reservation=reservation).first()
    guesty_id = guestvation.guesty_id
    guesty_r = self.api.get_one(Reservation, guesty_id)
    return self.sync_reservation(guesty_r)

  def _find_custom_fields(self, r_long):
    """ There's a guesty bug where, in reservation.new webhooks, the custom
    fields are lurking in the listing object for some reason. But in
    reservation.updated webhooks, it's in the correct place. """
    fields = r_long['customFields']
    if len(fields) == 0:
      fields = r_long.get('listing', {}).get('customFields', [])
    return CustomFields(Reservation, r_long['_id'], fields, api=self.api)

  def get_existing_reservation(self, guesty_id, channel_id):
    # One time, a reservation switched its channel id after it was booked,
    # causing duplicates! Come to think of it I feel like I remember guesty
    # changing a guesty_id once too. So now as long as one of them doesn't
    # change it'll pick up the correct existing reservation.
    easy = Reservation.objects.filter(
        channel_id=channel_id, guestyreservation__guesty_id=guesty_id).first()
    if easy:
      return easy
    by_guesty_id = Reservation.objects.filter(
        guestyreservation__guesty_id=guesty_id).first()
    by_channel_id = Reservation.objects.filter(channel_id=channel_id).first()
    either = by_guesty_id or by_channel_id
    if either:
      either.channel_id = channel_id
      either.save()
      either.guestyreservation.guesty_id = guesty_id
      either.guestyreservation.save()
    return either

  def sync_reservation(
      self, r_short, verbose=False, allowed_in_runserver=False, nnow=None):

    guesty_id = r_short['_id']
    channel_id = r_short.get('confirmationCode', None)
    reservation = None
    if channel_id:
      reservation = self.get_existing_reservation(guesty_id, channel_id)

    # Guesty is apparently messing with the contents of webhooks. Now they
    # don't necessarily contain listing.
    if 'money' in r_short and 'listing' in r_short:
      r_long = r_short
    else:
      r_long = self.api.get_one(
          Reservation, guesty_id, allowed_in_runserver=allowed_in_runserver)
      if 'listing' not in r_long:
        # But if, when you get the long version of the reservation data and it
        # doesn't include a listing, THAT means it's for a listing that's no
        # longer integrated with our account, a.k.a. not our responsibility.
        # So in that case we can safely ignore it.
        if verbose:
          print((
              'Ignoring {} because we no longer manage whatever property this '
              'is for apprently').format(guesty_id))
        return

    status = r_long['status']

    # A "reserved" reservation can transition to "closed", "declined", or
    # "confirmed". Now, there's some confusion here due to a guesty bug. At the
    # moment, they're failing to send a webhook when "reserved" transitions to
    # "confirmed". So now I'm keeping track of all "reserved" guesty_ids and
    # polling them on the hour for a status change. When THOSE turn confirmed I
    # actually import them. But in the past, before I understood the difference
    # between reserved and confirmed, I tried a shortcut of just treating
    # reserved as confirmed. So some data in the database is inconsistent that
    # way. You can get a "declined" webhook on a reservation keys thinks is
    # "confirmed" for instance.
    if status == 'reserved':
      ReservedReservation.objects.get_or_create(guesty_id=guesty_id)
      return
    if reservation:
      if status in ['closed', 'declined']:
        # Looks like a reserved reservation got treated as confirmed, so now we
        # should treat it as canceled.
        if not reservation.canceled_at:
          reservation.status = 'canceled'
          reservation.canceled_at = now()
          reservation.save()
        status = 'canceled'
      elif status == 'reserved':
        return

    ignore_statuses = [
        'inquiry', 'declined', 'closed', 'awaiting_payment', 'expired']
    if status in ignore_statuses:
      # I saw an inquiry reservation from TripAdvisor that already had a
      # confirmation code. awaiting_payment happened about half an hour before
      # confirmed for an airbnb reservation.
      if channel_id and status not in [
          'declined', 'closed', 'inquiry', 'awaiting_payment']:
        subject = (
            'Reservation with status {} does have a '
            'confirmation code').format(status)
        log_error(subject, '{} {} {}'.format(guesty_id, status, channel_id))
      return
    elif status not in ('canceled', 'confirmed', 'reserved'):
      log_error(
          'Unexpected reservation status', '{} from {}'.format(
              status, json.dumps(r_long, indent=2)))

    if not channel_id:
      if status == 'confirmed':
        # 5dabe0174f96d100477a1030 had this, but Guesty immediately sent a
        # confirmed webhook with a confirmation code.
        return
      subject = (
          'Reservation with status {} does not have a '
          'confirmation code').format(status)
      log_error(subject, '{} {} {}'.format(guesty_id, status, channel_id))
    money = r_long['money']
    source = r_long['source']
    if source.lower() == 'block':
      # If you're curious, see
      # https://app.guesty.com/reservations/5bc36b2ad98137003bbf26a9/guests for
      # an example of a block. It's just a way to make sure no reservations
      # happen during that time so we can, for instance, do a thorough
      # cleaning. But also, see
      # https://app.guesty.com/reservations/5c50b93bf4969c001f54bfd5/financials
      # for an example of a reservation that was accidentally marked block!
      # Hence the check for any payments.
      if len(money['payments']):
        source = 'manual'
      else:
        return
    channel = self.get_channel_from_source(source)

    notified_already = [AIRBNB, CANADA_STAYS, MISTER_B_AND_B, ONLY_APARTMENTS]
    if status == 'confirmed' and channel in THEY_ASSUME_CC_RISK_CHANNELS and (
        channel not in notified_already):
      notify(
          settings.ALERT_THEY_COLLECT_PAYMENT_CHANNEL,
          'Seb, we got a reservation from {}'.format(channel), (
              '{} takes payments, so we don\'t have a way to verify that we '
              'got paid yet. I (Dave) programmed up this message so you\'d '
              'be aware of the situation.').format(channel))
      subject = 'Add {} to sync_reservation in guesty.guesty'.format(channel)
      message = (
          'This isnt actually an error. Its just the first time weve seen '
          'this channel. We notified the accountants of the situation and '
          'just want to avoid re-notifying them.')
      log_error(subject, message)

    if not reservation:
      reservation = Reservation(channel_id=channel_id)

    custom_fields = self._find_custom_fields(r_long)
    guesty_guest = self.api.get_one(
        Guest, r_long['guestId'], allowed_in_runserver=allowed_in_runserver)
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
    reservation.set_check_out(parse_datetime(r_long['checkOut']), nnow=nnow)
    # reservation.new webhooks don't include this information for some reason.
    if 'confirmedAt' in r_long:
      reservation.booked_at = parse_datetime(r_long['confirmedAt'])
    else:
      reservation.booked_at = now()
    reservation.canceled_at = None
    canceled_at_str = r_long.get('canceledAt', None)
    if canceled_at_str:
      reservation.canceled_at = parse_datetime(canceled_at_str)
    reservation.imported_at = r_long.get('importedAt', None)
    if reservation.imported_at:
      reservation.imported_at = parse_datetime(reservation.imported_at)

    reservation.planned_arrival = self._get_time(r_long, 'plannedArrival')
    reservation.planned_departure = self._get_time(r_long, 'plannedDeparture')

    reservation.guest_count = r_long['guestsCount']
    reservation.reservation_created = parse_datetime(r_long['createdAt'])

    # Guesty picked a bad variable name here.
    ideal_payin = money['hostPayout']
    currency = money['currency']
    reservation.ideal_payin = Money(ideal_payin, currency)

    maximum_authorization_hold = self._get_maximum_authorization_hold(
        reservation, r_long)
    reservation.maximum_authorization_hold = maximum_authorization_hold
    first_payment_scheduled_on = self.first_payment_scheduled_on(money)
    reservation.first_payment_scheduled_on = first_payment_scheduled_on
    reservation.cc_last_4, reservation.cc_brand = self._get_last_4_and_cc_type(
        r_long)

    reservation.valid_payments_exist = bool(
        self._get_maximum_payment_with_status(r_long, 'SUCCEEDED'))
    reservation.status = status
    if status == 'canceled' and not reservation.canceled_at:
      reservation.canceled_at = now()
    reservation.channel = channel
    reservation.issues = r_long.get('notes', {}).get('other', None)
    reservation.rental = self._get_rental_from_reservation(
        r_long, allowed_in_runserver=allowed_in_runserver)

    try:
      reservation.save()
    except IntegrityError as ex:
      # One time, I saw 26 webhooks for the same reservation in a 4 minute
      # time span. So this is a race. This exception comes from the unique
      # constraint on reservation.channel_id. Hopefully all the copies are more
      # or less the same and we can just ignore this loser of the race.
      if ex.args[0].find('channel_id'):
        return
      # Otherwise I'm not sure what's up, so use the regular ol' error
      # reporting mechanism.
      raise ex
    sync_payments(reservation, money)

    # SMSs and Emails are created via a post_sync hook.

    custom_fields.pull_custom_fields(reservation)
    self._sync_reservation_line_items(reservation, r_long)

    # OK, apparently Guesty will destroy and create new objects for the same
    # reservation. I used to just have this here:
    # GuestyReservation.objects.get_or_create( reservation=reservation,
    # guesty_id=guesty_id) But that was no good because they'd send a totally
    # new guesty_id for the same channel_id, so I'd end up with two
    # GuestyReservations, the first being invalid.
    existing_gr = GuestyReservation.objects.filter(reservation=reservation)
    if existing_gr:
      existing_gr.update(guesty_id=guesty_id)
    else:
      GuestyReservation.objects.create(
          reservation=reservation, guesty_id=guesty_id)

    # These have to come after the GuestyReservation object is created because
    # the error messages includes guesty links and the feedback form url
    # contains a guesty link.
    if settings.PROD or settings.TEST:
      # We want to sync reservations in all environments, but it only makes
      # sense to push custom fields in production, which is allowed to, and in
      # tests, where the api is mocked.
      custom_fields.push_custom_fields(reservation)
    self.alert_if_overlap(reservation)

    post_sync.send(sender=Reservation, instance=reservation)

    return reservation

  def get_balance_due(self, money):
    """
    This should be in the reservation object and be based off the new Payment
    and Refund objects.

    It'd be great if we could just use the balanceDue attribute, but
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
    if source.lower() in ('website', 'manual'):
      return HOWARD
    if source == 'oa@oa.oa':
      return ONLY_APARTMENTS
    if source in ['hello@misterbnb.com', 'misterb&b']:
      return MISTER_B_AND_B
    raise Exception((
        'Unknown channel: \'{}\'. Please update get_channel_from_source in '
        'guesty.guesty.Guesty or possibly util/channels.py').format(source))

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
          extra_to=settings.ALERT_OVERLAPPING_RESERVATIONS)

  def first_payment_scheduled_on(self, money):
    first = None
    for payment in money.get('payments', []):
      should = payment.get('shouldBePaidAt', None)
      if should:
        should = parse_datetime(should)
        if not first or should < first:
          first = should
    return first

  def _get_maximum_authorization_hold(self, reservation, r_long):
    messaging_goes_live = make_aware(
        parse_datetime(settings.MESSAGING_GOES_LIVE))
    before_policy = reservation.reservation_created < messaging_goes_live
    if before_policy:
      # If it was before we went live, then this security payment policy
      # wasn't in effect yet.
      return Money(300, 'USD')
    # This came up a surprising amount of times. Tom or McKay would need a way
    # to force the system to recognize the cc as authorized. Sometimes it's for
    # old reservations authorized a long time ago, sometimes it's for test
    # reservations.
    if CustomFields(
        Reservation, None, r_long['customFields'],
        api=self.api).trust_me_cc_authorized():
      return Money(300, 'USD')
    # I assume that any successful hold placed on a card is a security
    # payment.
    return self._get_maximum_payment_with_status(
        r_long, 'AUTHORIZATION_HOLD_SUCCEEDED')

  def _get_maximum_payment_with_status(self, r_long, status):
    payment = None

    for payment_j in r_long.get('money', {}).get('payments', []):
      pay_status = payment_j.get('status', '')
      if pay_status == status:
        next_payment = Money(payment_j['amount'], payment_j['currency'])
        if not payment or next_payment > payment:
          payment = next_payment

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
    return time_str_to_time(r_long.get(key, None))

  def sync_webhooks(self, server_url, verbose=False, events=GUESTY_EVENTS):
    """ This gets run daily on prod entirely because one time guesty dropped
    our webhook configuration and it took us 3 days to notice.

    You can run this from any server on behalf of any server, hence there's no
    exception for running this on non-PROD. But let's only have production
    receive guesty webhooks. Webhooks trigger all kinds of stuff and I can
    totally imagine some easy-to-miss thing eating up all the rate limiting of
    some API or another if these are installed on stage too.

    Guesty().api.get_all('Webhook') shows all existing configurations. """
    if server_url[-1] == '/':
      server_url = server_url[:-1]

    try:
      existing = self.api.get_all('Webhook')
    except ServerError:
      # Who cares. This function so rarely accomplishes anything.
      return
    expected = self._create_missing_webhooks_and_return_expected(
        server_url, existing, events, verbose)
    self._delete_extra_webhooks(server_url, existing, expected, verbose)

  def delete_webhooks(self, server_url, verbose=False):
    for webhook in self.api.get_all('Webhook'):
      if webhook['url'].find(server_url) >= 0:
        if verbose:
          print('Deleting {}'.format(webhook))
        self.api.delete('webhooks/{}'.format(webhook['_id']))

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
          self.api.post('webhooks', new_hook)
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
          self.api.delete('webhooks/{}'.format(exist['_id']))

  def _sync_things(
      self, type_of_thing, skip, verbose, from_date=None, to_date=None):
    limit = 25
    results = self.api.get_many(
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
      results = self.api.get_many(
          type_of_thing, skip, limit, from_date, to_date)

  def too_early_to_sync_rental(self, nickname):
    """ In the process of setting up units, all kinds of wacky webhooks come
    in. When the nicknames look like "6735 E Grnway #1103" then we're talking
    about a unit that's close to being set up at least. If the nickname looks
    like "Modern 2 BR/2 BA with Gym and Pool by Howard" then we're still early
    in the process and liable to create cruft. Sometimes the early units go
    away entirely, or the IDs AND the nicknames change. """
    return nickname.lower().find('by howard') >= 0

  def sync_rental(self, rental_data, notifier=None):
    notifier = notifier or Notifier()
    nickname = rental_data['nickname']
    guesty_rental_id = rental_data['_id']
    # This depends on a current weird step the VAs are doing, setting the
    # nickname to a long weird description like "3BA SUNNY WAH BLAH BLA! by
    # Howard"
    if self.too_early_to_sync_rental(nickname):
      return
    # This is the newer, more robust approach to keeping weird un-ready listing
    # data out of keys.
    custom_fields = CustomFields(
        Rental, guesty_rental_id, rental_data['customFields'], api=self.api)
    if custom_fields.enter_1_to_activate_listing_in_keys() != 1:
      return

    guesty_rental_by_id = GuestyRental.objects.filter(
        guesty_id=guesty_rental_id).first()
    guesty_rental_by_nickname = GuestyRental.objects.filter(
        rental__nickname=nickname).first()

    # This is why it's OK to have a GuestyRental with an old incorrect ID as
    # long as its the only one with the new correct nickname.
    if guesty_rental_by_nickname and not guesty_rental_by_id:
      # The ID changed.
      guesty_rental_by_nickname.guesty_id = guesty_rental_id
      guesty_rental_by_nickname.save()
    elif guesty_rental_by_nickname and guesty_rental_by_id and (
        guesty_rental_by_nickname.guesty_id != guesty_rental_by_id.guesty_id):
      url = keys_reverse('clean_up_dupe_rentals') + '?pks={},{}'.format(
          guesty_rental_by_nickname.rental.pk, guesty_rental_by_id.rental.pk)
      notifier.notify(
          ['tom@hihoward.com', 'dave@hihoward.com'],
          'One of these rentals probably needs to go away.',
          'You can pick which is the correct one here: {}'.format(url))

    guesty_rental = guesty_rental_by_nickname or guesty_rental_by_id
    rental = self._get_rental_object_from_data(
        rental_data, guesty_rental_id, guesty_rental)
    if not guesty_rental:
      guesty_rental = GuestyRental.objects.create(
          rental=rental, guesty_id=guesty_rental_id)
    post_sync.send(sender=Rental, instance=rental)
    return rental

  def _get_rental_object_from_data(
      self, rental_data, guesty_rental_id, guesty_rental):
    """ rental_data can be either a rental dict, or a guesty id string
    for a rental ("listing" in Guesty vernacular). """
    if rental_data.__class__ is str:
      rental_data = self.api.get_one(Rental, rental_data)
    rental = self._get_unsaved_rental_object_from_data(
        rental_data, guesty_rental_id, guesty_rental)
    rental.save()
    rental.building.is_active = rental.building.is_active or rental.is_active
    rental.building.save()

    rental.rentalphoto_set.all().delete()
    for picture in rental_data.get('pictures', []):
      RentalPhoto.objects.create(
          rental=rental,
          thumbnail_url=picture.get('thumbnail', ''),
          regular_url=picture.get('regular', ''),
          large_url=picture.get('large', ''),
          original_url=picture.get('original', ''))
    amenities = []
    for amenity in rental_data.get('amenities', []):
      amenities.append(Amenity.objects.get_or_create(name=amenity)[0])
    rental.amenities.set(amenities)
    return rental

  def _get_unsaved_rental_object_from_data(
      self, rental_data, guesty_rental_id, guesty_rental):
    custom_fields = CustomFields(
        Rental, guesty_rental_id, rental_data['customFields'], api=self.api)

    possible_existing_building = None
    nickname = rental_data['nickname']
    if guesty_rental:
      possible_existing_building = guesty_rental.rental.building
      rental = guesty_rental.rental
    else:
      rental = Rental.objects.filter(nickname=nickname).first()
      if not rental:
        rental = Rental()

    building = self._get_unsaved_building_object_from_data(
        possible_existing_building, rental_data)
    building.save()
    rental.building = building

    address = rental_data['address']
    rental.full_address = address['full']
    rental.street = address.get('street', '')
    rental.apartment = address.get('apt', rental.apartment) or ''
    rental.accommodates = rental_data['accommodates']
    rental.bathrooms = rental_data['bathrooms']
    rental.bedrooms = rental_data['bedrooms']
    rental.property_type = rental_data['propertyType']
    rental.room_type = rental_data['roomType']
    rental.nickname = nickname
    prices = rental_data.get('prices', {})
    if prices:
      currency = prices.get('currency', 'USD').upper()
      rental.cleaning_fee = Money(prices.get('cleaningFee', '0'), currency)
      rental.extra_guest_fee = Money(
          prices.get('extraPersonFee', '0'), currency)
      rental.guests_before_fee = prices.get('guestsIncludedInRegularFee', 1)
    bed_count = 0
    for room in rental_data.get('listingRooms', []):
      for bed in room.get('beds', []):
        bed_count += bed.get('quantity', 0)
    rental.bed_count = bed_count
    rental.brief_description = rental_data.get(
        'publicDescription', {}).get('summary', '')

    rental.main_checkin_instructions_link = \
        custom_fields.main_checkin_instructions_link()
    rental.main_property_access_codes_in_order_of_use = \
        custom_fields.main_property_access_codes_in_order_of_use()
    rental.master_access_code_building_door_electronic_lock = \
        custom_fields.master_access_code_building_door_electronic_lock()
    rental.master_access_code_apartment_door_electronic_lock = \
        custom_fields.master_access_code_apartment_door_electronic_lock()
    rental.backup_check_in_codes = \
        custom_fields.backup_check_in_codes()
    rental.backup_check_in_instructions_link = \
        custom_fields.backup_check_in_instructions_link()
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
    rental.is_test_rental = \
        custom_fields.is_test_rental()
    rental.extra_details = \
        custom_fields.extra_details()
    rental.leave_the_keys = \
        custom_fields.leave_the_keys()

    # isListed is an optional field, but active is always there. You need
    # both to actually actually be active tho haha
    is_listed = rental_data.get('isListed', False)
    rental.is_active = rental_data['active'] and is_listed
    return rental

  def _get_unsaved_building_object_from_data(
      self, possible_existing_building, rental_data):
    address = rental_data['address']
    country = address.get('country', 'Unknown')
    state = address.get('state', 'Unknown')
    city_name = address.get('city', 'Unknown')
    if city_name == 'Washington' and state == 'DC':
      city_name = 'Washington, DC'
    city = City.objects.get_or_create(
        name=city_name, state=state, country=country)[0]
    street = address.get('street', 'Unknown')
    default_nickname = '{}, {}'.format(street, state)

    # Thanks for being so simple to work with Decimal. I hate you.
    latitude = address.get('lat', None)
    if latitude:
      # latitude = models.DecimalField(decimal_places=6
      latitude = round(Decimal(latitude), 6)
    longitude = address.get('lng', None)
    if longitude:
      longitude = round(Decimal(longitude), 6)

    # The test rental doesn't have all these filled in.
    building_kwargs = {
        'city': city,
        'zipcode': address.get('zipcode', 'Unknown'),
        'street': street,
        'time_zone': rental_data.get('timezone', 'Unknown'),
        'latitude': latitude,
        'longitude': longitude}
    if possible_existing_building and possible_existing_building.pk:
      Building.objects.filter(
          pk=possible_existing_building.pk).update(**building_kwargs)
      return Building.objects.get(pk=possible_existing_building.pk)
    found_existing = Building.objects.filter(**building_kwargs).first()
    if found_existing:
      return found_existing
    # nickname is unique.
    nickname_existing = Building.objects.filter(nickname=default_nickname)
    if nickname_existing.exists():
      nickname_existing.update(**building_kwargs)
      return nickname_existing.first()
    building_kwargs['nickname'] = default_nickname
    new_building = Building(**building_kwargs)
    return new_building

  def _get_rental_from_reservation(self, r_long, allowed_in_runserver=False):
    guesty_rental_id = r_long['listingId']
    # One time during the reservation.reviewed webhook listingId was
    # {'_id': '5af600acf78694001ba03953', 'id': '5af600acf78694001ba03953'}
    if guesty_rental_id.__class__ is dict:
      guesty_rental_id = guesty_rental_id['_id']
    if not GuestyRental.objects.filter(guesty_id=guesty_rental_id):
      self.sync_rental(self.api.get_one(
          Rental, guesty_rental_id, allowed_in_runserver=allowed_in_runserver))
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
    guest.first_name = guesty_guest.get('firstName', None) or ''
    guest.last_name = guesty_guest.get('lastName', None) or ''
    guest.full_name = guesty_guest['fullName']
    guest.phone = phone
    guest.airbnb_says_theyre_from = guesty_guest.get('hometown', None) or ''
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

  def _all_account_ids(self):
    account_ids = set()

    for rental in self.api.get_all(Rental):
      account_ids.add(rental['accountId'])

    return account_ids

""" Refactoring idea. API should check for errors and raise exceptions if it
encounters them. If not, then return json. """
import json

from django.conf import settings
from django.shortcuts import reverse

from errors.models import ErrorLogger
from util.html_status_codes import NotOkError, raise_if_server_error
from util.network import can_write_net, CantUseTheNet
from util.random_string import random_string
from util import rrequests


# OK, each properly request has both a synchronous response, and an
# asynchronous webhook. Requests contain data typically including a bunch of
# IDs. To create a cleaning you reference a checklist by ID and a property by
# ID, for instance. Both the response and the webhook may notice that the
# request used an invalid ID. When the response has problems with an ID, it'll
# tell you it was unable to find the property by that ID, or whatever. But when
# a webhook has problems with an ID, this is what it tells you. I've also seen
# this error when we sent an API call to change the list of service providers,
# but a service provider simultaneously accepted the job, so it wasn't until
# the webhook came back that it hit the issue about updating service providers
# after a job has been accepted.
UNKNOWN_ID_ERROR = (
    'Invalid response from Parse. Expecting status 200 and received: '
    '400 - Body: ')
# One time we started getting this error in webhooks for jobRequest.create
# requests. The crazy thing was, the requests actually did go through. Now,
# when we try to create one offs, we often get errors because there's a race
# with creating the custom checklist. Our answer to that is simply to keep
# retrying to create the one off until it finally goes through. Now, the old
# version of the code didn't distinguish between UNKNOWN_ID_ERROR and
# SERVER_ERROR so when it encountered a SERVER_ERROR in a webhook, it retried
# to create the job, but each call was actually successful, so we got, like, 8
# copies of the same one off job.
SERVER_ERROR = (
    'Invalid response from Parse. Expecting status 200 and received: '
    '503 - Body: ')


class API(object):
  def cleaning_jobs(self, data, print_curl=False):
    return self._post_api_event(
        'listing.cleaningJobs', data, print_curl=print_curl).json()

  def checklist_create(self, data, print_curl=False):
    return self._post_api_event(
        'checklist.create', data, print_curl=print_curl).json()

  def checklist_disable(self, checklist_id, print_curl=False):
    return self._post_api_event(
        'checklist.disable', {'checklistId': checklist_id},
        print_curl=print_curl)

  def booking_create(self, data, print_curl=False):
    raise Exception('Taking Properly doooown')
    return self._post_api_event('booking.create', data, print_curl=print_curl)

  def booking_cancel(self, booking_id, print_curl=False):
    return self._post_api_event(
        'booking.canceled', {'bookingId': booking_id}, print_curl=print_curl)

  def booking_changed(self, data, print_curl=False):
    return self._post_api_event('booking.changed', data, print_curl=print_curl)

  def job_request_create(self, data, client_request_id, print_curl=False):
    raise Exception('We no longer create jobs on Properly')
    return self._post_api_event(
        'jobRequest.create', data, client_request_id, print_curl).json()

  def job_request_create_curl_command(
      self, data, client_request_id, print_curl=False):
    """ This doesn't actually run the command, just return a theoretical curl
    command which is handy for communicating with Properly when a
    create command fails. """
    return self._post_api_event_curl_command(
        'jobRequest.create', data, client_request_id)

  def job_request_update(self, data, print_curl=False):
    raise Exception('Slowly weaning ourselves off Properly')
    return self._post_api_event(
        'jobRequest.update', data, print_curl=print_curl)

  def job_request_cancel(self, job_request_id, print_curl=False):
    return self._post_api_event(
        'jobRequest.canceled', {'jobRequestId': job_request_id},
        print_curl=print_curl).json()

  def property_update(self, data, print_curl=False):
    return self._post_api_event('property.update', data, print_curl=print_curl)

  def _post_api_event(
      self, namespace_action, data, client_request_id=None, print_curl=False):
    return self._post(
        self._url('/apiEvent'), {namespace_action: [data]}, client_request_id,
        print_curl)

  def _post_api_event_curl_command(
      self, namespace_action, data, client_request_id=None):
    data = {namespace_action: [data]}
    data = self._json_wrapper(data, client_request_id)
    return rrequests.post_curl_command(
        self._url('/apiEvent'), headers=self._headers(), json=data)

  def setup_webhook(self, event_name='*'):
    """
    Hey! Don't spam this function because, you guessed it, Properly doesn't
    handle it good when this is called and it tends to skip a bunch of
    webhooks.

    'Evetytime (sic) you call /setupWebhook your webhook configurations are
    replaced.'
    Regarding the clientRequestId, the docs say "when not provided, we will
    generate one." But if you don't include one they return a 500 error with
    content
    [{"type":"required","field":"clientRequestId","message":
    "The 'clientRequestId' field is required!"}] """
    if can_write_net():
      call_my_webhook_url = '{}{}'.format(
          settings.THIS_SERVERS_BASE_URL, reverse('properly_webhook'))
      return self._post(self._url('/setupWebhook'), {
          'webhooks': [{
              'url': call_my_webhook_url,
              'eventName': event_name}]})

  def _post(self, url, data, client_request_id=None, print_curl=False):
    """ If we are able to identify any errors, raise them here. Then by default
    they'll get mailed out. """
    if settings.TEST:
      raise CantUseTheNet(
          'This is ugly, but I use this in tests because I cant, like, '
          'intercept post_save hooks and inject a mocked API')
    # I mean, can_write_net also raises a CantUseTheNet in tests. But I kept
    # commenting out this check so I could do local development. So I put that
    # settings.TEST check in there so I could still run the tests and develop
    # locally.
    if can_write_net():
      data = self._json_wrapper(data, client_request_id)
      got = rrequests.post(
          url, headers=self._headers(), json=data, print_curl=print_curl)
      if got.status_code == 403:
        raise Exception(
            'Properly turned off API access again.',
            '{} returned 403.'.format(url))
      raise_if_server_error(got)
      self.check_response_data_is_ok(data, got.json())
      # One by one, convert every function that uses _post to return json. Once
      # they all do, we can turn this into return got.json(). Right now this
      # API is confusing because functions return response objects, which
      # implies you have to check for valid responses, which you don't, because
      # I changed it so any problems that occur during the api calls throw
      # exceptions now. So if you get a response at all, you know it's good, so
      # the results from the API may as well just be data.
      return got

  def check_response_data_is_ok(
      self, sent_data, received_data, error_logger=ErrorLogger()):
    for key, value in received_data.items():
      if key.find('.') > 0:  # jobRequest.create, for instance
        for result in value:
          if 'errors' in result:
            message = 'Sent {}\nReceived{}'.format(
                json.dumps(sent_data, indent=2),
                json.dumps(received_data, indent=2))
            error_logger.log_error('Properly API error', message)
            raise NotOkError(
                status_code=None, content=message, url=None,
                sent_data=sent_data)
    return True

  def _json_wrapper(self, data, client_request_id=None):
    client_request_id = client_request_id or random_string(7)
    send_json = {
        'targetAccountId': settings.PROPERLY_TARGET_ACCOUNT_ID,
        'clientRequestId': client_request_id}
    send_json.update(data)
    return send_json

  def _headers(self):
    return {'x-api-key': settings.PROPERLY_API_KEY}

  def _url(self, endpoint):
    if endpoint[0] == '/':
      endpoint = endpoint[1:]
    return '{}/{}'.format(settings.PROPERLY_API_ROOT, endpoint)

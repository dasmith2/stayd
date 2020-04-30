from datetime import timedelta
from unittest.mock import Mock, call

from django.shortcuts import reverse

from photos.tests import set_photo_stuff
from rentals.tests import get_test_rental
from work.models.clean import (
    ConfirmationPhoto, DidSlide,
    handle_report_cleaning_ticket, handle_slide_did_stuff,
    handle_complete_cleaning, created_tickets_data)
from work.models.message import (
    Message, MessageSender, CLEANER_REPORTED_PROBLEM)
from work.models.ticket import CLEAN_HIHOWARD_COM
from work.tests.test_cleaning import (
    get_test_cleaning, get_test_cleaning_config)
from work.tests.test_cleaning_checklist import (
    get_test_slide, get_test_cleaning_checklist)
from work.tests.test_rental import get_test_properly_rental
from work.tests.test_work_co import get_test_work_co
from util.ajax import AjaxProblem
from util.tests import TestCase, get_test_user
from util.timezone import str_to_tz_dt


def get_test_confirmation_photo(**kwargs):
  return set_photo_stuff(ConfirmationPhoto(), **kwargs)


def get_test_did_slide(**kwargs):
  slide = kwargs.get('slide', None)
  if not slide:
    slide = get_test_slide(**kwargs)
  cleaning = kwargs.get('cleaning', None)
  if not cleaning:
    cleaning = get_test_cleaning(**kwargs)
  confirmation_photo = kwargs.get('confirmation_photo', None)
  if not confirmation_photo:
    confirmation_photo = get_test_confirmation_photo(**kwargs)

  return DidSlide.objects.create(
      cleaning=cleaning,
      slide=slide,
      confirmation_photo=confirmation_photo,
      done=kwargs.get('done', False))


class HandlePostsTests(TestCase):
  def setUp(self):
    super().setUp()
    self.rental = get_test_rental(nickname='Not a horse apt')
    owner = get_test_user(email='spectacular@hassle.com')
    clean_co = get_test_work_co(
        owner=owner, name='Spectacular Hassle Cleaners')
    properly_rental = get_test_properly_rental(
        clean_co=clean_co, rental=self.rental)
    cleaning_checklist = get_test_cleaning_checklist()
    get_test_cleaning_config(
        cleaning_checklist=cleaning_checklist, properly_rental=properly_rental)
    self.cleaning = get_test_cleaning(
        rental=self.rental, started_at=str_to_tz_dt('2018-12-25 11:26'))
    self.message_sender = Mock(spec=MessageSender)
    self.slide = get_test_slide(
        cleaning_checklist=cleaning_checklist, title='The horse loft')

  def test_handle_report_cleaning_ticket(self):
    post = {
        'description': 'There is a horse loose in the apartment',
        'photo_file_name': 'horse.jpg'}
    ticket = handle_report_cleaning_ticket(
        post, self.cleaning, message_sender=self.message_sender)
    self.assertEqual('There is a horse loose in the apartment', ticket.title)
    self.assertEqual('horse.jpg', ticket.ticketphoto.file_name)
    self.assertTrue(ticket.image_url.find('horse.jpg') > 0)
    self.assertEqual(self.rental, ticket.rental)
    self.assertEqual('New', ticket.status())
    self.assertEqual(CLEAN_HIHOWARD_COM, ticket.came_from)

    resolve_url = reverse('close_ticket', kwargs={'ticket_pk': ticket.pk})
    expected = [{
        'pk': ticket.pk,
        'title': 'There is a horse loose in the apartment',
        'image_url': 'https://dev-hihoward-public.s3.amazonaws.com/horse.jpg',
        'resolve_url': resolve_url,
        'fixed': False}]
    self.assertEqual(expected, created_tickets_data(self.cleaning))

    return ticket

  def test_report_ticket_to_clean_co(self):
    ticket = self.test_handle_report_cleaning_ticket()
    msg = Message.objects.get(
        to='spectacular@hassle.com', reason=CLEANER_REPORTED_PROBLEM,
        work=self.cleaning)
    subject = (
        'Troubleshoot at Not a horse apt: There is a horse loose in the '
        'apartment')
    self.assertEqual(subject, msg.subject)
    close_ticket_url = reverse('close_ticket', kwargs={'ticket_pk': ticket.pk})
    self.assertTrue(msg.content.find(close_ticket_url) > 0)
    self.assertEqual([call(msg)], self.message_sender.send.call_args_list)

  def test_handle_slide_did_stuff(self):
    # No photo, yes done.
    post = {'photo_file_name': None, 'done': 'true'}
    did_slide = handle_slide_did_stuff(post, self.cleaning, self.slide)
    self.assertIsNone(did_slide.confirmation_photo)
    self.assertTrue(did_slide.done)
    self.assertFalse(did_slide.is_complete())

    # Yes photo, not done.
    post = {'photo_file_name': 'done.jpg', 'done': 'false'}
    did_slide = handle_slide_did_stuff(post, self.cleaning, self.slide)
    self.assertEqual('done.jpg', did_slide.confirmation_photo.file_name)
    self.assertFalse(did_slide.done)
    self.assertFalse(did_slide.is_complete())

    # Yes photo, yes done.
    post = {'photo_file_name': 'done.jpg', 'done': 'true'}
    did_slide = handle_slide_did_stuff(post, self.cleaning, self.slide)
    self.assertEqual('done.jpg', did_slide.confirmation_photo.file_name)
    self.assertTrue(did_slide.done)
    self.assertTrue(did_slide.is_complete())

  def test_handle_complete_cleaning(self):
    try:
      handle_complete_cleaning(self.cleaning)
      self.fail()
    except AjaxProblem as ex:
      self.assertEqual(
          'You still need to complete these slides: The horse loft',
          ex.message)
    self.cleaning.refresh_from_db()
    self.assertIsNone(self.cleaning.completed_at)

    self.test_handle_slide_did_stuff()
    handle_complete_cleaning(
        self.cleaning, nnow=str_to_tz_dt('2018-12-25 13:12'))

    self.cleaning.refresh_from_db()
    self.assertEqual(
        str_to_tz_dt('2018-12-25 13:12'), self.cleaning.completed_at)


class ConfirmationPhotoTests(TestCase):
  def test_no_did_slide(self):
    photo = get_test_confirmation_photo()
    self.assertEqual(
        'This confirmation photo isnt associated with a cleaning',
        photo.explain_why_no_need_for_photo())
    photo.calc_and_set_keep(nnow=str_to_tz_dt('2018-12-25'))
    self.assertEqual(str_to_tz_dt('2018-12-25'), photo.keep_until)

  def test_no_ticket(self):
    photo = get_test_confirmation_photo()
    get_test_did_slide(
        confirmation_photo=photo,
        offered_start_time=str_to_tz_dt('2018-12-01 11:15'))
    self.assertEqual('', photo.explain_why_no_need_for_photo(
        nnow=str_to_tz_dt('2018-12-25')))
    self.assertEqual(
        'The cleaning was 30 or more days ago',
        photo.explain_why_no_need_for_photo(nnow=str_to_tz_dt('2019-01-01')))
    photo.calc_and_set_keep()
    self.assertEqual(
        str_to_tz_dt('2018-12-01 11:15') + timedelta(days=30),
        photo.keep_until)

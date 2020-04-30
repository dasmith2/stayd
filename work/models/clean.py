""" Clean is a verb in this case. This is the unit-testable stuff relating to
cleaners completing a cleaning on clean.hihoward.com """
from datetime import timedelta

from django.db import models
from django.shortcuts import reverse

from photos.models import Photo
from work.models.cleaning import Cleaning
from work.models.cleaning_checklist import Slide
from work.models.message import (
    CLEANER_REPORTED_PROBLEM, Message, MessageSender)
from work.models.ticket import Ticket, CLEAN_HIHOWARD_COM, TicketPhoto
from util.ajax import get_ajax_variable, AjaxProblem
from util.fields import OneToOneOrNoneField
from util.timezone import now
from util.urls import keys_reverse


def created_tickets_data(cleaning):
  to_return = []
  for ticket in cleaning.created_ticket_set.filter(
      completed_at__isnull=True).order_by('pk'):
    to_return.append(created_ticket_data(ticket))
  return to_return


def created_ticket_data(ticket):
  return {
      'pk': ticket.pk,
      'title': ticket.title,
      'image_url': ticket.image_url,
      'resolve_url': reverse('close_ticket', kwargs={'ticket_pk': ticket.pk}),
      'fixed': bool(ticket.completed_at)}


def slides_for_clean(cleaning):
  did_slides = list(cleaning.didslide_set.all())
  to_return = []
  for slide in cleaning.get_cleaning_checklist().slide_set.order_by('order'):
    did_slide = None
    for possible in did_slides:
      if possible.slide == slide:
        did_slide = possible
    to_return.append(slide_for_clean(cleaning, slide, did_slide))
  return {'slides': to_return}


def slide_for_clean(cleaning, slide, did_slide):
  steps = [step.text for step in slide.step_set.all()]
  example_photo = None
  if slide.example_photo:
    example_photo = {
        'url': slide.example_photo.url(),
        'file_name': slide.example_photo.file_name}
  confirmation_photo = None
  done = False
  if did_slide:
    if did_slide.confirmation_photo:
      confirmation_photo = {
          'url': did_slide.confirmation_photo.url(),
          'file_name': did_slide.confirmation_photo.file_name}
    done = did_slide.done
  url_kwargs = {'cleaning_pk': cleaning.pk, 'slide_pk': slide.pk}
  did_slide_stuff_url = reverse('slide_done', kwargs=url_kwargs)
  return {
      'title': slide.title,
      'pk': slide.pk,
      'steps': steps,
      'example_photo': example_photo,
      'confirmation_photo': confirmation_photo,
      'done': done,
      'did_slide_stuff_url': did_slide_stuff_url}


def handle_complete_cleaning(cleaning, nnow=None):
  nnow = nnow or now()
  unfinished = []
  checklist = cleaning.rental.properlyrental.cleaningconfig.cleaning_checklist
  for slide in checklist.slide_set.all():
    did_slide = slide.didslide_set.filter(cleaning=cleaning).first()
    if not did_slide or not did_slide.is_complete():
      unfinished.append(slide.title)
  if unfinished:
    raise AjaxProblem('You still need to complete these slides: {}'.format(
        ', '.join(unfinished)))
  cleaning.completed_at = nnow
  cleaning.save()
  return True


def handle_report_cleaning_ticket(post, cleaning, message_sender=None):
  description = get_ajax_variable(post, 'description')
  photo_file_name = get_ajax_variable(
      post, 'photo_file_name', required=False)
  ticket = Ticket.objects.create(
      title=description, rental=cleaning.rental, came_from_work=cleaning,
      came_from=CLEAN_HIHOWARD_COM)
  if photo_file_name:
    TicketPhoto.objects.create(
        file_name=photo_file_name, ticket=ticket, keep_until=now(),
        keep_forever=False)
  report_ticket_to_clean_co(cleaning, ticket, message_sender=message_sender)
  return ticket


def handle_slide_did_stuff(post, cleaning, slide):
  did_slide = DidSlide.objects.filter(cleaning=cleaning, slide=slide).first()
  if not did_slide:
    did_slide = DidSlide(cleaning=cleaning, slide=slide)

  photo_file_name = None
  if slide.example_photo:
    photo_file_name = get_ajax_variable(
        post, 'photo_file_name', required=False)
    # The way this is programmed, you can't clear out the confirmation photo.
    # That's totally consistent with the user interface which only lets you
    # replace an existing confirmation photo.
    if photo_file_name:
      confirmation_photo = ConfirmationPhoto.objects.filter(
          file_name=photo_file_name).first()
      if not confirmation_photo:
        confirmation_photo = ConfirmationPhoto.objects.create(
            file_name=photo_file_name, keep_until=now() + timedelta(days=1),
            keep_forever=False)
      did_slide.confirmation_photo = confirmation_photo

  # I'm being real defensive here. The requests are coming in with 'true' or
  # 'false' but just in case they ever come in as True or False, this will keep
  # working.
  did_slide.done = str(get_ajax_variable(post, 'done')).lower() == 'true'

  did_slide.save()

  return did_slide


def report_ticket_to_clean_co(cleaning, ticket, message_sender=None):
  """ Cleaners will be, like, "I can't complete the living room because the
  vacuum cleaner has no bag." So we want the cleaning company to hear about
  that and have the chance to a) just put a bag in the vacuum cleaner and b)
  mark the ticket resolved. """
  message_sender = message_sender or MessageSender()

  clean_co = cleaning.rental.properlyrental.clean_co
  owner_email = clean_co.owner.email
  subject = 'Troubleshoot at {}: {}'.format(
      cleaning.rental.nickname, ticket.title[:40])
  content = (
      'If possible, troubleshoot it yourself and <a href="{}">click '
      'this link so we know you handled it</a>:'
      '\n\nDescription: {}').format(
          keys_reverse('close_ticket', ticket_pk=ticket.pk), ticket.title)
  if ticket.image_url:
    content += '\n<img src="{}">'.format(ticket.image_url)

  Message.objects.create_and_send_email(
      to=owner_email, reason=CLEANER_REPORTED_PROBLEM, content=content,
      work=cleaning, subject=subject, message_sender=message_sender)


class ConfirmationPhoto(Photo):
  """ In a cleaning checklist, if a slide has an ExamplePhoto, then in every
  cleaning it's the cleaner's responsibility to snap a ConfirmationPhoto that
  tries to look exactly like the ExamplePhoto. So a ConfirmationPhoto is a
  per-slide thing. """
  def explain_why_no_need_for_photo(self, nnow=None):
    if self.didslide_or_none:
      if self.old_cleaning(nnow=nnow):
        return 'The cleaning was 30 or more days ago'
    else:
      return 'This confirmation photo isnt associated with a cleaning'
    return ''

  def calc_and_set_keep(self, nnow=None):
    nnow = nnow or now()
    self.keep_until = nnow
    if self.didslide_or_none:
      self.keep_until = self.didslide.cleaning.offered_start_time + (
          timedelta(days=30))
    self.keep_forever = False

  def old_cleaning(self, nnow=None):
    nnow = nnow or now()
    return self.didslide.cleaning.offered_start_time < (
        nnow - timedelta(days=30))

  def delete(self, s3=None):
    if self.didslide_or_none:
      did_slide = self.didslide
      did_slide.confirmation_photo = None
      did_slide.save()
    super().delete(s3=s3)

  def sensitive(self):
    return False


class DidSlide(models.Model):
  cleaning = models.ForeignKey(Cleaning, on_delete=models.CASCADE)
  slide = models.ForeignKey(Slide, on_delete=models.CASCADE)
  confirmation_photo = OneToOneOrNoneField(
      ConfirmationPhoto, null=True, blank=True, on_delete=models.PROTECT,
      help_text='A confirmation photo is always required now.')
  done = models.BooleanField(default=True, help_text='Is this actually done?')
  created_at = models.DateTimeField(auto_now_add=True)

  # I used to have a, like, blocking_ticket per DidSlide so if the cleaner
  # couldn't complete the slide for whatever reason they could explain why. But
  # that turned out to be terrifically confusing for the cleaners.

  def is_complete(self):
    if self.slide.example_photo and not self.confirmation_photo:
      return False
    if not self.done:
      return False
    return True

  class Meta:
    unique_together = [['cleaning', 'slide']]

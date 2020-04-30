""" A cleaning checklist is basically a list of photos of what the rooms are
supposed to look like along with a few lines of text. """
from datetime import timedelta
from django.db import models

from photos.models import Photo
from util.ajax import get_ajax_variable, AjaxProblem, OK
from util.fields import OneToOneOrNoneField
from util.timezone import now


def create_slide(data):
  cleaning_checklist_pk = get_ajax_variable(data, 'cleaning_checklist_pk')
  title = get_ajax_variable(data, 'title')
  insert_at = int(get_ajax_variable(data, 'insert_at'))

  cleaning_checklist = CleaningChecklist.objects.filter(
      pk=cleaning_checklist_pk).first()
  if not cleaning_checklist:
    raise AjaxProblem('This cleaning checklist doesn\'t exist', 404)

  slides = list(cleaning_checklist.slide_set.order_by('order'))
  new_slide = Slide(title=title, cleaning_checklist=cleaning_checklist)
  slides.insert(insert_at, new_slide)
  _set_slide_orders(slides)
  return new_slide.data()


def delete_slide(slide):
  """ This is outside the Slide object so I can hand it to
  do_simple_rest_request """
  cleaning_checklist = slide.cleaning_checklist
  slide.delete()
  slides = list(cleaning_checklist.slide_set.order_by('order'))
  _set_slide_orders(slides)
  return OK


def _set_slide_orders(slides):
  # I put a unique_together constraint on slide.cleaning_checklist and
  # slide.order. So you can't just change the order because you might step on
  # an existing slide.
  if len(slides) > 99999:
    raise Exception('Why is there a checklist with a hundred thousand slides?')
  for slide in slides:
    if slide.pk:
      slide.order += 100000
      slide.save()
  for index, slide in list(enumerate(slides)):
    slide.order = index
    slide.save()


def edit_slide(slide, data):
  for key in data.keys():
    if key.find('photo') >= 0 or key.find('file_name') >= 0:
      raise AjaxProblem(
          'Use the create_example_photo function to set the example photo on '
          'slides')
  slide.title = get_ajax_variable(data, 'title')
  slide.save()
  return OK


def create_step(data):
  slide_pk = get_ajax_variable(data, 'slide_pk')
  text = get_ajax_variable(data, 'text')
  return Step.objects.create(slide_id=slide_pk, text=text).data()


def edit_step(step, data):
  text = get_ajax_variable(data, 'text')
  step.text = text
  step.save()
  return OK


def delete_step(step):
  step.delete()
  return OK


def do_create_example_photo(slide, file_name, nnow=None):
  nnow = nnow or now()
  photo = ExamplePhoto.objects.filter(file_name=file_name).first()
  if not photo:
    photo = ExamplePhoto.objects.create(
        file_name=file_name, keep_forever=False, keep_until=nnow)
  slide.set_example_photo(photo, nnow=nnow)
  return {'pk': photo.pk, 'url': photo.url()}


class CleaningChecklist(models.Model):
  title = models.CharField(unique=True, max_length=200, help_text=(
      'Give this checklist a brief, helpful title that will make it easy to '
      'select from a drop down list, e.g., Slate 3 bedroom'))

  def slides_data(self):
    slides = []
    for slide in self.slide_set.order_by('order'):
      slides.append(slide.data())
    return {'slides': slides}

  def __repr__(self):
    return '<CleaningChecklist {}: {}>'.format(self.pk, self.title)

  def __str__(self):
    return self.title


class ExamplePhoto(Photo):
  def explain_why_no_need_for_photo(self):
    if self.slide_or_none:
      return ''
    return 'No slide is using this photo'

  def calc_and_set_keep(self, nnow=None):
    nnow = nnow or now()
    if self.slide_or_none:
      self.keep_forever = True
      self.keep_until = None
    else:
      self.keep_forever = False
      self.keep_until = nnow - timedelta(hours=1)

  def sensitive(self):
    return False


class Slide(models.Model):
  title = models.CharField(max_length=200, default='', blank=True)
  cleaning_checklist = models.ForeignKey(
      CleaningChecklist, on_delete=models.CASCADE)
  order = models.PositiveIntegerField(default=0)
  example_photo = OneToOneOrNoneField(
      ExamplePhoto, on_delete=models.PROTECT, blank=True, null=True,
      help_text=(
          'Where appropriate, you can include a photo showing how this should '
          'look'))

  def set_example_photo(self, new_example_photo, nnow=None):
    nnow = nnow or now()
    if self.example_photo:
      self.example_photo.keep_forever = False
      self.example_photo.keep_until = nnow
      self.example_photo.save()
    self.example_photo = new_example_photo
    self.save()

  def delete(self, nnow=None):
    nnow = nnow or now()
    if self.example_photo:
      self.example_photo.keep_forever = False
      self.example_photo.keep_until = nnow
      self.example_photo.save()
    super().delete()

  def data(self):
    data = {
        'title': self.title, 'order': self.order, 'pk': self.pk, 'steps': []}
    if self.example_photo:
      data['example_photo'] = {
          'pk': self.example_photo.pk, 'url': self.example_photo.url()}
    for step in self.step_set.order_by('pk'):
      data['steps'].append(step.data())
    return data

  def move_up(self):
    self._move_helper(-1)

  def move_down(self):
    self._move_helper(1)

  def _move_helper(self, move_direction):
    if move_direction not in [1, -1]:
      raise Exception('move_direction should be 1 or -1')
    slides = list(self.cleaning_checklist.slide_set.order_by('order'))
    at = slides.index(self)
    if move_direction == 1:
      if at == len(slides) - 1:
        return
      slides = slides[:at] + [slides[at + 1], slides[at]] + slides[at + 2:]
    elif move_direction == -1:
      if at == 0:
        return
      slides = slides[:at - 1] + [slides[at], slides[at - 1]] + slides[at + 1:]
    _set_slide_orders(slides)

  class Meta:
    unique_together = [['cleaning_checklist', 'order']]

  def __repr__(self):
    return '<Slide {}: {} {}>'.format(self.pk, self.title, self.order)


class Step(models.Model):
  slide = models.ForeignKey(Slide, on_delete=models.CASCADE)
  text = models.CharField(max_length=300)

  def data(self):
    return {'pk': self.pk, 'text': self.text}

  class Meta:
    ordering = ['pk']

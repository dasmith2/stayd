from photos.tests import set_photo_stuff
from work.models.cleaning_checklist import (
    CleaningChecklist, ExamplePhoto, Slide, Step, create_slide, edit_slide,
    delete_slide, create_step, edit_step, delete_step, do_create_example_photo)
from util.ajax import OK
from util.random_string import random_string
from util.tests import TestCase
from util.timezone import str_to_tz_dt


def get_test_cleaning_checklist(**kwargs):
  return CleaningChecklist.objects.create(
      title=kwargs.get('title', random_string()))


def get_test_example_photo(**kwargs):
  return set_photo_stuff(ExamplePhoto(), **kwargs)


def get_test_slide(**kwargs):
  cleaning_checklist = kwargs.get('cleaning_checklist', None)
  if not cleaning_checklist:
    cleaning_checklist = get_test_cleaning_checklist(**kwargs)
  example_photo = kwargs.get('example_photo', None)
  if not example_photo:
    example_photo = get_test_example_photo(**kwargs)
  return Slide.objects.create(
      title=kwargs.get('title', 'Living room'),
      cleaning_checklist=cleaning_checklist,
      order=kwargs.get('order', 0),
      example_photo=example_photo)


def get_test_step(**kwargs):
  slide = kwargs.get('slide', None)
  if not slide:
    slide = get_test_slide(**kwargs)
  return Step.objects.create(
      slide=slide,
      order=kwargs.get('order', 0),
      text=kwargs.get('text', 'I totally feel for these millionaires'))


class ExamplePhotoTests(TestCase):
  def test_example_photo(self):
    slide = get_test_slide()
    got = do_create_example_photo(
        slide, 'blarney.jpg', nnow=str_to_tz_dt('2018-12-25 12:00'))
    slide.refresh_from_db()
    original_photo = ExamplePhoto.objects.get(pk=got['pk'])
    self.assertEqual('blarney.jpg', original_photo.file_name)
    self.assertFalse(original_photo.keep_forever)
    self.assertEqual(
        str_to_tz_dt('2018-12-25 12:00'), original_photo.keep_until)
    self.assertTrue(original_photo.url().find('blarney.jpg') > 0)
    self.assertEqual(original_photo.url(), got['url'])

    self.assertEqual('', original_photo.explain_why_no_need_for_photo())
    self.assertFalse(original_photo.sensitive())
    original_photo.calc_and_set_keep(nnow=str_to_tz_dt('2018-12-25 13:00'))
    original_photo.save()
    self.assertTrue(original_photo.keep_forever)
    self.assertIsNone(original_photo.keep_until)

    got2 = do_create_example_photo(
        slide, 'stone.jpg', nnow=str_to_tz_dt('2018-12-25 14:00'))
    original_photo.refresh_from_db()
    self.assertFalse(original_photo.keep_forever)
    self.assertEqual(
        str_to_tz_dt('2018-12-25 14:00'), original_photo.keep_until)
    self.assertEqual(
        'No slide is using this photo',
        original_photo.explain_why_no_need_for_photo())

    new_photo = ExamplePhoto.objects.get(pk=got2['pk'])
    slide.refresh_from_db()
    self.assertEqual(new_photo, slide.example_photo)
    new_photo.calc_and_set_keep(nnow=str_to_tz_dt('2018-12-25 15:00'))
    new_photo.save()
    self.assertTrue(new_photo.keep_forever)

    slide.delete(nnow=str_to_tz_dt('2018-12-25 16:00'))
    new_photo.refresh_from_db()
    self.assertFalse(new_photo.keep_forever)
    self.assertEqual(
        str_to_tz_dt('2018-12-25 16:00'), new_photo.keep_until)


class SlideTests(TestCase):
  def test_create_slide(self):
    self.checklist = get_test_cleaning_checklist(
        title='36 hours a day, 5 days a week')

    def create_slide_in_test(title, insert_at):
      got_data = create_slide({
          'cleaning_checklist_pk': self.checklist.pk, 'title': title,
          'insert_at': insert_at})
      return Slide.objects.get(pk=got_data['pk'])

    self.living_room = create_slide_in_test('Living room', 0)
    self.bedroom = create_slide_in_test('Bedroom', 0)
    self.bathroom = create_slide_in_test('Bathroom', 1)
    self.porch = create_slide_in_test('Porch', 3)

    self.living_room.refresh_from_db()
    self.bedroom.refresh_from_db()
    self.bathroom.refresh_from_db()
    self.porch.refresh_from_db()

    self.assertEqual(0, self.bedroom.order)
    self.assertEqual(1, self.bathroom.order)
    self.assertEqual(2, self.living_room.order)
    self.assertEqual(3, self.porch.order)
    self.assertEqual(
        [self.bedroom, self.bathroom, self.living_room, self.porch],
        list(self.checklist.slide_set.order_by('order')))

  def test_edit_slide(self):
    self.test_create_slide()

    edit_slide(self.living_room, {'title': 'I SAID LIVING ROOM!!'})
    self.living_room.refresh_from_db()
    self.assertEqual('I SAID LIVING ROOM!!', self.living_room.title)

  def test_delete_slide(self):
    self.test_create_slide()

    delete_slide(self.bathroom)
    self.living_room.refresh_from_db()
    self.bedroom.refresh_from_db()
    self.porch.refresh_from_db()

    self.assertEqual(0, self.bedroom.order)
    self.assertEqual(1, self.living_room.order)
    self.assertEqual(2, self.porch.order)
    self.assertEqual(
        [self.bedroom, self.living_room, self.porch],
        list(self.checklist.slide_set.order_by('order')))

  def test_move_slide_up_and_down(self):
    self.test_create_slide()

    self.bedroom.move_down()
    self.bedroom.refresh_from_db()
    self.bathroom.refresh_from_db()
    self.living_room.refresh_from_db()
    self.porch.refresh_from_db()

    self.assertEqual(0, self.bathroom.order)
    self.assertEqual(1, self.bedroom.order)
    self.assertEqual(2, self.living_room.order)
    self.assertEqual(3, self.porch.order)

    self.assertEqual(
        [self.bathroom, self.bedroom, self.living_room, self.porch],
        list(self.checklist.slide_set.order_by('order')))
    self.bedroom.move_down()
    self.bedroom.refresh_from_db()
    self.assertEqual(2, self.bedroom.order)
    self.assertEqual(
        [self.bathroom, self.living_room, self.bedroom, self.porch],
        list(self.checklist.slide_set.order_by('order')))
    self.bedroom.move_down()
    self.bedroom.refresh_from_db()
    self.assertEqual(3, self.bedroom.order)
    self.assertEqual(
        [self.bathroom, self.living_room, self.porch, self.bedroom],
        list(self.checklist.slide_set.order_by('order')))
    self.bedroom.move_down()
    self.bedroom.refresh_from_db()
    self.assertEqual(3, self.bedroom.order)
    self.bedroom.move_up()
    self.bedroom.refresh_from_db()
    self.assertEqual(2, self.bedroom.order)
    self.assertEqual(
        [self.bathroom, self.living_room, self.bedroom, self.porch],
        list(self.checklist.slide_set.order_by('order')))
    self.bedroom.move_up()
    self.bedroom.refresh_from_db()
    self.assertEqual(1, self.bedroom.order)
    self.assertEqual(
        [self.bathroom, self.bedroom, self.living_room, self.porch],
        list(self.checklist.slide_set.order_by('order')))
    self.bedroom.move_up()
    self.bedroom.refresh_from_db()
    self.assertEqual(0, self.bedroom.order)
    self.assertEqual(
        [self.bedroom, self.bathroom, self.living_room, self.porch],
        list(self.checklist.slide_set.order_by('order')))
    self.bedroom.move_up()
    self.bedroom.refresh_from_db()
    self.assertEqual(0, self.bedroom.order)


class StepTests(TestCase):
  def test_step(self):
    checklist = get_test_cleaning_checklist()
    slide = get_test_slide(cleaning_checklist=checklist)
    got_data = create_step({
        'slide_pk': slide.pk, 'text': 'Polish the remote control'})
    self.assertEqual('Polish the remote control', got_data['text'])
    step = Step.objects.get(pk=got_data['pk'])
    edit_step(step, {'text': 'Oil up the sea lions'})
    step.refresh_from_db()
    self.assertEqual('Oil up the sea lions', step.text)
    self.assertEqual(OK, delete_step(step))
    self.assertFalse(Step.objects.filter(pk=step.pk).exists())

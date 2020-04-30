""" The cleaning checklist page has to create ExamplePhotos as it goes, but
otherwise it puts together an ajax object and sends it to save_checklist.  """
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse, Http404
from django.shortcuts import redirect, reverse, render

from work.models.cleaning_checklist import (
    CleaningChecklist, create_slide, edit_slide, delete_slide,
    create_step, edit_step, delete_step, Slide, Step, do_create_example_photo)
from util.admin import admin_context
from util.ajax import (
    get_ajax_variable, AjaxProblem, do_simple_rest_request, OK, ajax)
from util.permission import can_groups, CLEANING_ADMINISTRATOR_GROUP


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
@ajax
def slide(request, slide_pk=None):
  """ Create, update, or delete a slide depending on the request method and the
  slide_pk. """
  action = request.POST.get('action', None)
  if action:
    slide = Slide.objects.filter(pk=slide_pk).first()
    if not slide:
      return Http404('Slide doesnt exist')
    if action == 'move_up':
      slide.move_up()
      return OK
    elif action == 'move_down':
      slide.move_down()
      return OK
  return do_simple_rest_request(
      request, Slide, slide_pk, create_slide, edit_slide, delete_slide)


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
@ajax
def step(request, step_pk=None):
  """ Create, update, or delete a step depending on the request method and the
  step_pk. """
  return do_simple_rest_request(
      request, Step, step_pk, create_step, edit_step, delete_step)


class NewChecklistForm(forms.Form):
  title = forms.CharField(max_length=200)

  def clean(self):
    if CleaningChecklist.objects.filter(
        title=self.get_title()).exists():
      raise ValidationError('A checklist with this title already exists')
    return super().clean()

  def get_title(self):
    return self.cleaned_data['title']


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
def new_checklist(request):
  form = NewChecklistForm()
  if request.method == 'POST':
    form = NewChecklistForm(request.POST)
    if form.is_valid():
      checklist = CleaningChecklist.objects.create(title=form.get_title())
      return redirect(reverse(
          'edit_checklist', kwargs={'checklist_pk': checklist.pk}))
  context = admin_context('New cleaning checklist', form=form)
  return render(
      request, 'cleaning_checklist/new_checklist.html', context=context)


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
def edit_checklist(request, checklist_pk):
  checklist = CleaningChecklist.objects.filter(pk=checklist_pk).first()
  if not checklist:
    return Http404('This checklist doesn\'t exist')
  list_slides_url = reverse(
      'list_slides', kwargs={'checklist_pk': checklist.pk})
  cleaning_checklists_url = reverse('admin:work_cleaningchecklist_changelist')
  context = admin_context(
      'Edit cleaning checklist', checklist=checklist,
      change_checklist_title_url=reverse('change_checklist_title'),
      list_slides_url=list_slides_url, slide_url=reverse('slide'),
      step_url=reverse('step'),
      create_example_photo_url=reverse('create_example_photo'),
      cleaning_checklists_url=cleaning_checklists_url)
  return render(
      request, 'cleaning_checklist/edit_checklist.html', context=context)


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
def list_slides(request, checklist_pk):
  checklist = CleaningChecklist.objects.filter(pk=checklist_pk).first()
  if not checklist:
    return Http404('This cleaning checklist doesnt exist')
  return JsonResponse(checklist.slides_data())


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
@ajax
def change_checklist_title(request):
  checklist_pk = get_ajax_variable(request.POST, 'checklist_pk')
  title = get_ajax_variable(request.POST, 'title')
  if not title:
    raise AjaxProblem('The title cant be empty')
  checklist = CleaningChecklist.objects.filter(pk=checklist_pk).first()
  if not checklist:
    raise AjaxProblem('This checklist doesnt seem to exist')
  if CleaningChecklist.objects.filter(
      ~Q(pk=checklist_pk), title=title).exists():
    raise AjaxProblem('A different checklist already has this title')
  checklist.title = title
  checklist.save()
  return OK


@login_required
@can_groups(CLEANING_ADMINISTRATOR_GROUP)
def create_example_photo(request):
  try:
    slide_pk = get_ajax_variable(request, 'slide_pk')
    slide = Slide.objects.filter(pk=slide_pk).first()
    if not slide:
      raise AjaxProblem('This slide does not exist')
    file_name = get_ajax_variable(request, 'file_name')
  except AjaxProblem as ex:
    return ex.get_problem_response()

  return JsonResponse(do_create_example_photo(slide, file_name))

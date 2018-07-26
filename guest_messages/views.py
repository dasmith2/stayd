from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.shortcuts import render

from guest_messages.forms import SMSTemplateFormSet, EmailTemplateFormSet
from guest_messages.models import SMS, Email, SMSTemplate, EmailTemplate
from util.fake_admin import admin_context


@login_required
@permission_required('guest_messages.change_smstemplate')
def edit_sms_templates(request):
  if request.method == 'POST':
    formset = SMSTemplateFormSet(request.POST)
    if formset.is_valid():
      formset.save()
      formset = SMSTemplateFormSet(queryset=SMSTemplate.objects.all())
  else:
    formset = SMSTemplateFormSet(queryset=SMSTemplate.objects.all())
  context = admin_context(
      'Guest SMS templates',
      formset=formset)
  return render(request, 'sms_templates.html', context=context)


@login_required
@permission_required('guest_messages.change_emailtemplate')
def edit_email_templates(request):
  if request.method == 'POST':
    formset = EmailTemplateFormSet(request.POST)
    if formset.is_valid():
      formset.save()
      formset = EmailTemplateFormSet(queryset=EmailTemplate.objects.all())
  else:
    formset = EmailTemplateFormSet(queryset=EmailTemplate.objects.all())
  context = admin_context(
      'Guest Email templates',
      formset=formset)
  return render(request, 'email_templates.html', context=context)


@login_required
def send_test_email(request):
  message = Email.objects.send_test(request.POST)
  return JsonResponse({'message': message})


@login_required
def send_test_sms(request):
  message = SMS.objects.send_test(request.POST)
  return JsonResponse({'message': message})

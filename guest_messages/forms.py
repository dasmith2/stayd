from django import forms

from guest_messages.models import SMSTemplate, EmailTemplate


SMSTemplateFormSet = forms.modelformset_factory(
    SMSTemplate, fields='__all__', can_delete=True)


EmailTemplateFormSet = forms.modelformset_factory(
    EmailTemplate, fields='__all__', can_delete=True)

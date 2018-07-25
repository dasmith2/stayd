from django import forms

from guest_messages.models import SMSTemplate


TemplateFormSet = forms.modelformset_factory(
    SMSTemplate, fields='__all__', can_delete=True)

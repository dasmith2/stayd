"""
For the actual HTML for SMS templates, say, see
guest_messages/templates/sms_templates.html which extends
message_templates.html
"""
from django import forms

from guest_messages.models.sms import SMSTemplate
from guest_messages.models.email import EmailTemplate


SMSTemplateFormSet = forms.modelformset_factory(
    SMSTemplate, fields='__all__', can_delete=True)


EmailTemplateFormSet = forms.modelformset_factory(
    EmailTemplate, fields='__all__', can_delete=True)

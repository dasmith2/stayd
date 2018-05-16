from django import forms

from guest_messages.models import Template


TemplateFormSet = forms.modelformset_factory(
    Template, fields='__all__', can_delete=True)

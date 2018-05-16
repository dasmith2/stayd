from django.forms import modelformset_factory

from guest_messages.models import Template


TemplateFormSet = modelformset_factory(
    Template, fields='__all__', can_delete=True)

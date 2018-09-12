from django.contrib import admin

from guest_messages.models.models import SMSTemplate, EmailTemplate


admin.site.register(SMSTemplate)
admin.site.register(EmailTemplate)

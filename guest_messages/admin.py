from django.contrib import admin

from guest_messages.models.email import EmailTemplate
from guest_messages.models.sms import SMSTemplate


admin.site.register(SMSTemplate)
admin.site.register(EmailTemplate)

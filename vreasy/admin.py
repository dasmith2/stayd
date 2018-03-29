from django.contrib import admin

from vreasy.models import VreasyProperty


class VreasyPropertyAdmin(admin.ModelAdmin):
  list_display = ('title', 'rental')
  list_editable = ('rental',)

admin.site.register(VreasyProperty, VreasyPropertyAdmin)

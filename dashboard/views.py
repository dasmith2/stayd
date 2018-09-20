from django.contrib.auth.decorators import login_required
from django.shortcuts import render


DASHBOARD_LOGIN = '/dashboard/login/'


@login_required(login_url=DASHBOARD_LOGIN)
def dashboard(request):
  context = {'owner_id': request.GET.get('owner_id', request.user.pk)}
  return render(request, 'dashboard.html', context=context)

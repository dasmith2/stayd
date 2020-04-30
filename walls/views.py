from django.shortcuts import render


def walls(request):
  return render(request, 'walls.html', {})

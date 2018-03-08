from django.shortcuts import render

def log_tester(request):
  options = [
    ('programmatic', 'Cause a programmatic error'),
  ]
  if request.post['action']
  context = {'options': options}
  return render(request, 'util/log_tester.html')

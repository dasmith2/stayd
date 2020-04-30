import warnings

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


def get_page_number(request):
  return request.GET.get('p', 1)


def set_page_number(url, page_number):
  if url.find('?') >= 0:
    return '{}&p={}'.format(url, page_number)
  return '{}?p={}'.format(url, page_number)


def get_page(query_set, page_number):
  # I turn warnings into errors so we catch any UnorderedObjectListWarning:
  # Pagination may yield inconsistent results with an unordered object_list:
  # <class 'properly.models.payment.Payment'> QuerySet.
  warnings.filterwarnings('error')
  paginator = Paginator(query_set, 10)
  warnings.resetwarnings()

  try:
    page = paginator.page(page_number)
  except PageNotAnInteger:
    page = paginator.page(1)
  except EmptyPage:
    page = paginator.page(paginator.num_pages)
  return page

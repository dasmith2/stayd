def admin_context(title, **kwargs):
  kwargs = kwargs or {}
  # The page title is `title : site_title`
  kwargs.update({
      'title': title,
      'site_title': title,
      'site_header': 'Stayd administration'})
  return kwargs

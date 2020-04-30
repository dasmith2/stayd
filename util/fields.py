from django.db import models


class OneToOneOrNoneField(models.OneToOneField):
  """
  You start with something like
  class Book(models.Model):
    pass

  I got a little frustrated with this kind of thing:

  class QueensLibraryBook(models.Model):
    book = models.OneToOneField(Book)

  def get_queens_library_book(my_book):
    try:
      return my_book.queenslibrarybook
    except Book.queenslibrarybook.RelatedObjectDoesNotExist:
      return None

  Now, you can do, like,

  class QueensLibraryBook(models.Model):
    book = OneToOneOrNoneField(Book)

  def get_queens_library_book(my_book):
    return my_book.queenslibrarybook_or_none

  """
  def contribute_to_related_class(self, cls, related):
    super().contribute_to_related_class(cls, related)

    def accessor_or_none(model_instance):
      if hasattr(model_instance, related.get_accessor_name()):
        return getattr(model_instance, related.get_accessor_name())
    property_name = '{}_or_none'.format(related.get_accessor_name())
    setattr(cls, property_name, property(accessor_or_none))

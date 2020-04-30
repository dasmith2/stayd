import re

from django.db import models

from errors.models import log_error
from xxero.models.businesses import Business
from xxero.api import ContactExistsAlready


class ContactManager(models.Manager):
  def get_by_name(self, name, business, api=None):
    """ If you try to look up an existing contact by 'TARGET.COM  *' Xero will
    say that contact doesn't exist. But when you try to create a contact with
    that name, Xero will say 'TARGET.COM *' already exists (note: count the
    spaces before the *). That's Xero contact name trickery. """
    api = api or business.get_api()
    name = re.compile(r'\s+').subn(' ', name)[0]
    existing_local = self.filter(name=name, business=business).first()
    if existing_local:
      return existing_local
    existing_xero = api.contact(name)
    if existing_xero:
      return self.sync_contact(existing_xero, business)
    try:
      created_data = api.create_contact(name)
      return self.sync_contact(created_data, business)
    except ContactExistsAlready as ex:
      message = (
          'I tried to look up a contact with name "{}", Xero said there '
          'wasn\'t one. Then I tried to create that contact and Xero '
          'said {}').format(name, ex.args[0])
      log_error('Xero contact name trickery', message)

  def sync_contact(self, contact_dict, business):
    contact_id = contact_dict['ContactID']
    contact = self.filter(contact_id=contact_id).first()
    if not contact:
      contact = Contact(contact_id=contact_id, business=business)
    if contact.name != contact_dict['Name']:
      contact.name = contact_dict['Name']
      contact.save()
    return contact


class Contact(models.Model):
  contact_id = models.UUIDField(db_index=True, unique=True)
  name = models.CharField(max_length=200)
  business = models.ForeignKey(
      Business, on_delete=models.PROTECT, help_text=(
          'Contacts are per business. So we\'ll get a few with the same name '
          'but different businesses.'))

  objects = ContactManager()

  def __str__(self):
    return self.name

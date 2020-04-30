import copy
from datetime import date
from unittest.mock import Mock, call
from uuid import UUID

from django.conf import settings
from django.shortcuts import reverse
from djmoney.money import Money

from bento.models import CREDIT, LOAD
from bento.tests import (
    get_test_transaction as get_test_bento_transaction, get_test_card,
    get_test_merchant_category)
from rentals.tests import get_test_building
from util.permission import ACCOUNTANT
from util.tests import TestCase
from util.timezone import str_to_tz_dt
from xxero.api import API
from xxero.api_examples import (
    CONTACT, CREATE_TRACKING_CATEGORY, CREATE_TRANSACTION, MISSING_TRACKING)
from xxero.models.bento_2_transaction import (
    Bento2Transaction, MerchantCategory2Coconut,
    get_merchant_category_2_coconut, MC2CValue,
    handle_merchant_category_2_coconut)
from xxero.models.businesses import Business
from xxero.models.contacts import Contact
from xxero.models.transactions import DELETED, AUTHORISED
from xxero.tests.test_businesses import get_test_business
from xxero.tests.test_coconuts import get_test_coconut, get_test_bank_account
from xxero.tests.test_tracking import (
    get_test_tracking_category, get_test_tracking_option)
from xxero.tests.test_transactions import (
    get_test_transaction as get_test_xero_transaction, get_test_line_item)


def get_test_bento_2_transaction(**kwargs):
  bento_transaction = kwargs.get('bento_transaction', None)
  if not bento_transaction:
    bento_transaction = get_test_bento_transaction(**kwargs)
  xero_transaction = kwargs.get('xero_transaction', None)
  if not xero_transaction:
    xero_transaction = get_test_xero_transaction(**kwargs)
  return Bento2Transaction.objects.create(
      bento_transaction=bento_transaction,
      xero_transaction=xero_transaction)


class HandleMerchantCategory2CoconutTests(TestCase):
  def test_merchant_category_2_coconut(self):
    # Brand new
    telecom = get_test_merchant_category(
        bento_id=-3, name='Telecom, Internet & Utilities')
    telecom_nut = get_test_coconut(code='611', name='Telecom nut')
    # Remain unchanged
    retail = get_test_merchant_category(
        bento_id=1000, name='Retail and Miscellaneous Stores')
    retail_nut = get_test_coconut(code='blonkyty', name='Retail?!')
    MerchantCategory2Coconut.objects.create(
        merchant_category=retail, coconut=retail_nut)
    # Change
    mail = get_test_merchant_category(bento_id=5, name='Mail Phone Order')
    old_mail_nut = get_test_coconut(code='over 9000', name='Bushels of emails')
    MerchantCategory2Coconut.objects.create(
        merchant_category=mail, coconut=old_mail_nut)
    new_mail_nut = get_test_coconut(code='50', name='Metric tons of emails')
    # Remain unset
    travel = get_test_merchant_category(
        bento_id=7, name='Travel & Transportation')

    # Test getting the current situation
    mc2c_values = get_merchant_category_2_coconut()
    expected_mc2c_values = [
        MC2CValue(mail, old_mail_nut),
        MC2CValue(retail, retail_nut),
        MC2CValue(telecom, None),
        MC2CValue(travel, None)]
    self.assertEqual(expected_mc2c_values, mc2c_values)

    # Test updating the situation
    request_post = {
        'merchant_category-3': telecom_nut.pk,
        'merchant_category1000': retail_nut.pk,
        'merchant_category5': new_mail_nut.pk,
        'merchant_category7': ''}
    handle_merchant_category_2_coconut(request_post)

    self.assertEqual(3, MerchantCategory2Coconut.objects.count())

    MerchantCategory2Coconut.objects.get(
        merchant_category=telecom, coconut=telecom_nut)
    MerchantCategory2Coconut.objects.get(
        merchant_category=retail, coconut=retail_nut)
    MerchantCategory2Coconut.objects.get(
        merchant_category=mail, coconut=new_mail_nut)

    # And while we're in here, test the view.
    self.login(group=ACCOUNTANT)
    url = reverse('merchant_category_2_coconut')
    self.assert_get_contains(url, 'Mail Phone Order')


class Bento2TransactionTests(TestCase):
  def test_fix_missing_tracking_options(self):
    api = Mock(spec=API)
    api.bank_transaction.return_value = MISSING_TRACKING
    business = get_test_business(consumer_key='wrawr')
    api_lookup = {'wrawr': api}
    xero_transaction = get_test_xero_transaction(
        bank_transaction_id='b7754eca-41b9-4f2e-9577-7bcc9a6eccde',
        business=business, status=AUTHORISED)
    get_test_coconut(code='644', name='Comically large shoes')
    line_item = get_test_line_item(
        transaction=xero_transaction,
        line_item_id='a169757f-f9dc-4b13-af7c-3093e92f1293')

    # This is really a test of add_tracking_to_data. I expect that fixing the
    # problem will call api.save_bank_transaction with data with new tracking
    # information. I have the api return exactly what it sent and then I see
    # if, upon syncing that data, the line item gets the tracking I expect.
    building = get_test_building(nickname='The Taj Mahal')
    bento_transaction = get_test_bento_transaction(building=building)
    get_test_bento_2_transaction(
        xero_transaction=xero_transaction,
        bento_transaction=bento_transaction)
    # Syncing tracking stuff is beyond the scope of this test. Let's just put
    # tracking stuff in place.
    tracking_category = get_test_tracking_category(
        business=business, name='Bldg',
        tracking_category_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
    get_test_tracking_option(
        tracking_category=tracking_category, name='The Taj Mahal')

    self.assertEqual(0, line_item.tracking_options.count())
    Bento2Transaction.objects.fix_missing_tracking_options(api_lookup)
    self.assertEqual(1, line_item.tracking_options.count())
    line_item.tracking_options.get(
        tracking_category__name='Bldg', name='The Taj Mahal')

  def test_find_non_deleted_transaction(self):
    bank_account = get_test_bank_account()
    old_transaction_1 = get_test_xero_transaction(
        status=DELETED,
        bank_account=bank_account,
        ttype=CREDIT,
        amount=Money('10', 'USD'),
        when=date(2018, 12, 15))
    b2t1 = get_test_bento_2_transaction(xero_transaction=old_transaction_1)
    old_transaction_2 = get_test_xero_transaction(
        status=DELETED,
        bank_account=bank_account,
        ttype=CREDIT,
        amount=Money('10', 'USD'),
        when=date(2018, 12, 15))
    b2t2 = get_test_bento_2_transaction(xero_transaction=old_transaction_2)
    get_test_xero_transaction(  # Wrong amount
        status=AUTHORISED,
        bank_account=bank_account,
        ttype=CREDIT,
        amount=Money('9', 'USD'),
        when=date(2018, 12, 15))
    new_transaction_1 = get_test_xero_transaction(
        status=AUTHORISED,
        bank_account=bank_account,
        ttype=CREDIT,
        amount=Money('10', 'USD'),
        when=date(2018, 12, 15))
    new_transaction_2 = get_test_xero_transaction(
        status=AUTHORISED,
        bank_account=bank_account,
        ttype=CREDIT,
        amount=Money('10', 'USD'),
        when=date(2018, 12, 15))

    Bento2Transaction.objects.fix_deleted()
    b2t1.refresh_from_db()
    b2t2.refresh_from_db()
    self.assertEqual(
        set([new_transaction_1, new_transaction_2]),
        set([b2t1.xero_transaction, b2t2.xero_transaction]))

  def test_push_bento_2_xero_receive(self):
    get_test_bento_transaction(
        ttype=LOAD, payee='ExecResidence Chase',
        amount=Money('2000', 'USD'),
        transaction_date=str_to_tz_dt('2018-10-15 12:00'))
    api = Mock(spec=API)
    api.contact.return_value = None
    CONTACT['ContactID'] = '88888888-8888-8888-8888-888888888888'
    CONTACT['Name'] = 'ExecResidence Chase'
    api.create_contact.return_value = CONTACT
    get_test_coconut(code='NUNU', name='Uncategorized')
    api.save_bank_transaction.return_value = CREATE_TRANSACTION

    for i in range(2):
      Bento2Transaction.objects.push_bento_2_xero(api)

    self.assertEqual(1, len(api.save_bank_transaction.call_args_list))
    expected = {
        'Type': 'RECEIVE',
        'Contact': {'ContactID': '88888888-8888-8888-8888-888888888888'},
        'LineItems': [{
            'AccountCode': 'Bento1',
            'UnitAmount': '2000.0',
            'Tracking': []}],
        'BankAccount': {'AccountID': settings.XERO_BENTO_BANK_ACCOUNT},
        'Date': str_to_tz_dt('2018-10-15 12:00')}
    self.assertEqual(
        [call(expected)], api.save_bank_transaction.call_args_list)

  def test_push_bento_2_xero_spend(self):
    Business.objects.init_businesses()
    # The card tracking category and option don't exist, but the building ones
    # do.
    card = get_test_card(alias='Blargh card')
    bobs_building = get_test_building(nickname='Bobs building')
    tracking_category = get_test_tracking_category(
        name='Bldg',
        tracking_category_id='56565656-5656-5656-5656-999999999999')
    # Note I don't set the building attribute here...
    bobs_building_option = get_test_tracking_option(
        tracking_category=tracking_category, name='Bobs building',
        tracking_option_id='55555555-6666-7777-8888-999999999999')

    bento_transaction = get_test_bento_transaction(
        ttype=CREDIT, payee='AMZN     Mktp US*M80MQ43K2',
        amount=Money('-10', 'USD'), card=card, building=bobs_building,
        transaction_date=str_to_tz_dt('2018-10-15 12:00'))

    api = Mock(spec=API)
    api.contact.return_value = None
    CONTACT['ContactID'] = '0cd2c44f-eaa5-4ad5-bb7e-4476371de679'
    CONTACT['Name'] = 'AMZN Mktp US*M80MQ43K2'
    api.create_contact.return_value = CONTACT
    api.get_tracking_category_by_name.return_value = None
    CREATE_TRACKING_CATEGORY['Name'] = 'Bento Card'
    CREATE_TRACKING_CATEGORY['TrackingCategoryID'] = (
        '55555555-5555-5555-5555-555555555555')
    api.create_tracking_category.return_value = CREATE_TRACKING_CATEGORY
    # It tries to sync the tracking category one last time before it creates
    # any new options.
    api.tracking_category.return_value = CREATE_TRACKING_CATEGORY
    api.create_tracking_option.return_value = (
        '66666666-6666-6666-6666-666666666666')
    CREATE_TRANSACTION['BankTransactionID'] = (
        '33333333-3333-3333-3333-333333333333')
    get_test_coconut(code='NUNU', name='Uncategorized')
    api.save_bank_transaction.return_value = CREATE_TRANSACTION

    for i in range(2):
      Bento2Transaction.objects.push_bento_2_xero(api)

    self.assertEqual(
        [call('AMZN Mktp US*M80MQ43K2')], api.contact.call_args_list)
    self.assertEqual(
        [call('AMZN Mktp US*M80MQ43K2')], api.create_contact.call_args_list)
    self.assertEqual(1, Contact.objects.count())
    Contact.objects.get(
        contact_id='0cd2c44f-eaa5-4ad5-bb7e-4476371de679',
        name='AMZN Mktp US*M80MQ43K2')

    self.assertEqual(
        [call('55555555-5555-5555-5555-555555555555', 'Blargh card')],
        api.create_tracking_option.call_args_list)

    self.assertEqual(1, Bento2Transaction.objects.count())
    bento_2_transaction = Bento2Transaction.objects.first()
    self.assertEqual(bento_transaction, bento_2_transaction.bento_transaction)
    self.assertEqual(
        UUID('33333333-3333-3333-3333-333333333333'),
        bento_2_transaction.xero_transaction.bank_transaction_id)

    self.assertEqual(1, len(api.save_bank_transaction.call_args_list))
    card_tracking = {
        'Name': 'Bento Card', 'Option': 'Blargh card',
        'TrackingCategoryID': '55555555-5555-5555-5555-555555555555',
        'TrackingOptionID': '66666666-6666-6666-6666-666666666666'}
    bldg_tracking = {
        'Name': 'Bldg', 'Option': 'Bobs building',
        'TrackingCategoryID': '56565656-5656-5656-5656-999999999999',
        'TrackingOptionID': '55555555-6666-7777-8888-999999999999'}
    expected = {
        'Type': 'SPEND',
        'Contact': {'ContactID': '0cd2c44f-eaa5-4ad5-bb7e-4476371de679'},
        'LineItems': [{
            'AccountCode': 'Bento1',
            'UnitAmount': '10.0',
            'Tracking': [card_tracking, bldg_tracking]}],
        'BankAccount': {'AccountID': settings.XERO_BENTO_BANK_ACCOUNT},
        'Date': str_to_tz_dt('2018-10-15 12:00')}
    self.assertEqual(
        [call(expected)], api.save_bank_transaction.call_args_list)
    business = Business.objects.get_operator()
    self.assertEqual(
        expected, Bento2Transaction.objects._bento_transaction_2_data(
            bento_transaction, business))

    # Let's throw in a quick MerchantCategory2Coconut test
    merchant_category = get_test_merchant_category()
    bento_transaction.merchant_category = merchant_category
    bento_transaction.save()
    coconut = get_test_coconut(code='711')
    self.assertEqual(
        expected, Bento2Transaction.objects._bento_transaction_2_data(
            bento_transaction, business))
    MerchantCategory2Coconut.objects.create(
        merchant_category=merchant_category, coconut=coconut)
    new_expected = copy.deepcopy(expected)
    new_expected['LineItems'][0]['AccountCode'] = '711'
    self.assertEqual(
        new_expected, Bento2Transaction.objects._bento_transaction_2_data(
            bento_transaction, business))

    # Here I check that the building option got a building attribute set along
    # the way. That comes in handy for cash_basis
    bobs_building_option.refresh_from_db()
    self.assertEqual(bobs_building, bobs_building_option.building)

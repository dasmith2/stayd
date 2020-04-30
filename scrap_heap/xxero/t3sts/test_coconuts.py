import copy
from unittest.mock import Mock
from uuid import uuid4 as random_uuid

from django.conf import settings
from django.shortcuts import reverse

from errors.models import Notifier
from xxero.api_examples import SYSTEM_ACCOUNT
from xxero.models.coconuts import Coconut, CoconutConflict, BankAccount
from xxero.models.businesses import Business, OPERATOR, OWNER
from xxero.tests.test_businesses import get_test_business


def get_test_bank_account(**kwargs):
  business = kwargs.get('business', None)
  if not business:
    business = get_test_business(**kwargs)
  return BankAccount.objects.create(
      account_id=kwargs.get('account_id', random_uuid()),
      name=kwargs.get('name', 'Daves offshore haven'),
      business=business)


def get_test_coconut(**kwargs):
  owner_reporting_code_name = kwargs.get('owner_reporting_code_name', 'Assets')
  operator_reporting_code_name = kwargs.get(
      'operator_reporting_code_name', 'Cash')
  return Coconut.objects.create(
      code=kwargs.get('code', '655'),
      name=kwargs.get('name', 'Software'),
      owner_type=kwargs.get('owner_type', 'EXPENSE'),
      operator_type=kwargs.get('operator_type', 'EXPENSE'),
      tax_type=kwargs.get('tax_type', 'INPUT'),
      owner_class=kwargs.get('owner_class', 'EXPENSE'),
      operator_class=kwargs.get('operator_class', 'REVENUE'),
      reporting_code=kwargs.get('reporting_code', 'ASS.CUR.INY'),
      owner_reporting_code_name=owner_reporting_code_name,
      operator_reporting_code_name=operator_reporting_code_name,
      description=kwargs.get('description', ''))


def get_test_coconut_conflict(**kwargs):
  business = kwargs.get('business', None)
  if not business:
    business = get_test_business(**kwargs)
  coconut = kwargs.get('coconut', None)
  if not coconut:
    coconut = get_test_coconut(**kwargs)
  return CoconutConflict.objects.create(
      business=business,
      coconut=coconut,
      code=kwargs.get('code', '655'),
      name=kwargs.get('name', 'Software'))


class FakeAccountsAPI(object):
  def __init__(self, accounts):
    self.account_lookup = {}
    for account in accounts:
      self.account_lookup[account['AccountID']] = account
    self.no_id_list = []

  def accounts(self):
    return list(self.account_lookup.values()) + self.no_id_list

  def account_by_code(self, code):
    for account in self.accounts():
      if account['Code'] == code:
        return account

  def account_by_name(self, name):
    for account in self.accounts():
      if account['Name'] == name:
        return account

  def save_account(self, account):
    if 'AccountID' in account:
      self.account_lookup[account['AccountID']] = account
    else:
      self.no_id_list.append(account)


class CoconutTests(object):
  def test_clean_up_unnecessary_conflicts(self):
    business_1 = get_test_business()
    business_2 = get_test_business()
    business_3 = get_test_business()

    satanic_laughter = get_test_coconut(code='661', name='Satanic laughter')
    get_test_coconut_conflict(
        business=business_1, coconut=satanic_laughter, code='661',
        name='Nasal spray')
    self.assertFalse(satanic_laughter.conflict_actually_exists())
    self.assertTrue(satanic_laughter.clean_up_unnecessary_conflicts())
    satanic_laughter.refresh_from_db()
    self.assertEqual('Nasal spray', satanic_laughter.name)
    self.assertEqual(0, CoconutConflict.objects.count())

    the_hay_bailing_days = get_test_coconut(
        code='771', name='The hay bailing days')
    get_test_coconut_conflict(
        business=business_1, coconut=the_hay_bailing_days, code='771',
        name='The hay bailing days')
    get_test_coconut_conflict(
        business=business_2, coconut=the_hay_bailing_days, code='771',
        name='Shoe putting on contest')
    self.assertTrue(the_hay_bailing_days.conflict_actually_exists())
    self.assertFalse(the_hay_bailing_days.clean_up_unnecessary_conflicts())
    Coconut.objects.get(code='771', name='The hay bailing days')
    self.assertEqual(2, the_hay_bailing_days.coconutconflict_set.count())

    outsmarting_yourself = get_test_coconut(
        code='881', name='Outsmarting yourself')
    get_test_coconut_conflict(
        business=business_1, coconut=outsmarting_yourself, code='123',
        name='Manufactured contempt')
    get_test_coconut_conflict(
        business=business_2, coconut=outsmarting_yourself, code='321',
        name='Why didnt you just say so')
    get_test_coconut_conflict(
        business=business_3, coconut=outsmarting_yourself, code='987',
        name='Milling about')
    self.assertFalse(outsmarting_yourself.conflict_actually_exists())
    self.assertTrue(outsmarting_yourself.clean_up_unnecessary_conflicts())
    Coconut.objects.get(code='881', name='Outsmarting yourself')
    Coconut.objects.get(code='123', name='Manufactured contempt')
    Coconut.objects.get(code='321', name='Why didnt you just say so')
    Coconut.objects.get(code='987', name='Milling about')
    self.assertEqual(0, outsmarting_yourself.coconutconflict_set.count())

  def test_sync(self):
    software = {
        'Code': '655', 'Name': 'Company Software', 'Status': 'ACTIVE',
        'Type': 'EXPENSE', 'TaxType': 'INPUT', 'Description': '',
        'Class': 'EXPENSE', 'ReportingCode': 'EXP',
        'ReportingCodeName': 'Expense', 'AccountID': 'ejenjenelskd'}
    barfware = {
        'Code': '655', 'Name': 'Company Barfware', 'Status': 'ACTIVE',
        'Type': 'EXPENSE', 'TaxType': 'INPUT', 'Description': '',
        'Class': 'EXPENSE', 'ReportingCode': 'EXP',
        'ReportingCodeName': 'Expense', 'AccountID': 'skdngloskdnf'}
    owner_management_fees = {
        'Code': '1111', 'Name': 'Management Fees', 'Status': 'ACTIVE',
        'Type': 'EXPENSE1', 'TaxType': 'INPUT', 'Description': '',
        'Class': 'EXPENSE', 'ReportingCode': 'EXP',
        'ReportingCodeName': 'Expense', 'AccountID': 'woeoqoqq'}
    operator_management_fees = {
        'Code': '1111', 'Name': 'Management Fees', 'Status': 'ACTIVE',
        'Type': 'REVENUE1', 'TaxType': 'INPUT', 'Description': '',
        'Class': 'REVENUE', 'ReportingCode': 'EXP',
        'ReportingCodeName': 'Revenue', 'AccountID': '932idnsl'}
    q_and_a = {
        'Code': '777', 'Name': 'Q&A', 'Status': 'ACTIVE',
        'Type': 'EXPENSE', 'TaxType': 'INPUT', 'Description': 'Hey guys',
        'Class': 'EXPENSE', 'ReportingCode': 'EXP',
        'ReportingCodeName': 'Expense', 'AccountID': 'jxjhjfhnskd'}
    Business.objects.init_businesses()
    operator_api = FakeAccountsAPI([
        software, operator_management_fees, q_and_a])
    owner_api = FakeAccountsAPI([barfware, owner_management_fees])
    api_lookup = {
        settings.XERO_EXEC_RESIDENCE_CONSUMER_KEY: owner_api,
        settings.XERO_HI_HOWARD_OPERATIONS_CONSUMER_KEY: operator_api}
    notifier = Mock(spec=Notifier)

    Coconut.objects.sync(notifier=notifier, api_lookup=api_lookup)

    self.assertEqual(3, Coconut.objects.count())
    conflict_at = Coconut.objects.get(code='655', name='Company Software')
    Coconut.objects.get(
        code='1111',
        name='Management Fees',
        owner_type='EXPENSE1',  # Not real data, just for better testing.
        operator_type='REVENUE1',
        tax_type='INPUT',
        owner_class='EXPENSE',
        operator_class='REVENUE',
        reporting_code='EXP',
        owner_reporting_code_name='Expense',
        operator_reporting_code_name='Revenue')
    Coconut.objects.get(code='777', name='Q&A', description='Hey guys')
    self.assertEqual(2, CoconutConflict.objects.count())
    CoconutConflict.objects.get(
        coconut=conflict_at,
        business=Business.objects.get(name='STAYD Inc'),
        code='655',
        name='Company Software')
    CoconutConflict.objects.get(
        coconut=conflict_at,
        business=Business.objects.get(name='ExecResidence Housing LLC'),
        code='655',
        name='Company Barfware')

  def test_push(self):
    original_really_short_horses_data = {
        'AccountID': '8f3ee590-a0fb-a5b9-b772-111111111111',
        'Code': '766',
        'Name': 'Really short horses',
        'Status': 'ACTIVE',
        'Type': 'CURRENT',
        'TaxType': 'NONE',
        'Description': 'Outstanding',
        'Class': 'ASSET',
        'BankAccountType': '',
        'ReportingCode': 'ASS.CUR.REC.ACR',
        'ReportingCodeName': 'Accounts receivable (current)'}
    really_short_horses = get_test_coconut(
        code='766', name='Really short horses')
    conflicted_really_short_horses_data = copy.deepcopy(
        original_really_short_horses_data)
    conflicted_really_short_horses_data['Code'] = '677'

    original_system_account_data = {
        'AccountID': '951decd3-88f6-48e8-b05c-63dbaa274b55',
        'Code': '2200',
        'Name': 'Many opinions were shared',
        'Status': 'ACTIVE',
        'Type': 'CURRLIAB',
        'TaxType': 'NONE',
        'Description': 'The balance in this...',
        'Class': 'LIABILITY',
        'BankAccountType': '',
        'ReportingCode': 'LIA.CUR.TAX.SAL'}
    many_opinions = get_test_coconut(
        code='2200', name='Many opinions were shared')
    conflicted_system_account = copy.deepcopy(original_system_account_data)
    conflicted_system_account['Name'] = 'Sales Tax'
    conflicted_system_account['SystemAccount'] = 'GST'

    get_test_coconut(code='123', name='Unfunny "comedians"')
    fine = {
        'AccountID': '8f3ee590-a0fb-a5b9-b772-333333333333',
        'Code': '123',
        'Name': 'Unfunny "comedians"',
        'Status': 'ACTIVE',
        'Type': 'CURRENT',
        'TaxType': 'NONE',
        'Description': 'Outstanding',
        'Class': 'ASSET',
        'BankAccountType': '',
        'ReportingCode': 'ASS.CUR.REC.ACR',
        'ReportingCodeName': 'Accounts receivable (current)'}

    get_test_coconut(code='854', name='Tiny hats')

    push_to = get_test_business(consumer_key='push_to')
    push_to_api = FakeAccountsAPI([
        conflicted_really_short_horses_data, conflicted_system_account, fine])
    other = get_test_business(consumer_key='other')
    other_api = FakeAccountsAPI([
        original_really_short_horses_data, original_system_account_data, fine])
    notifier = Mock(spec=Notifier)
    api_lookup = {'push_to': push_to_api, 'other': other_api}

    # Tiny hats is totally missing, so that should get saved. "Really short
    # horses" and "many opinions were shared" are conflicted, so they should
    # stay the same. Unfunny "comedians" is in both spots so no action is
    # necessary.
    self.assertEqual(0, len(push_to_api.no_id_list))
    Coconut.objects.push(push_to, notifier=notifier, api_lookup=api_lookup)
    self.assertEqual(1, len(push_to_api.no_id_list))
    self.assertEqual('854', push_to_api.no_id_list[0]['Code'])
    self.assertEqual('Tiny hats', push_to_api.no_id_list[0]['Name'])
    self.assertEqual(
        'Really short horses', push_to_api.account_by_code('677')['Name'])
    self.assertEqual('Sales Tax', push_to_api.account_by_code('2200')['Name'])

    self.assertEqual(4, CoconutConflict.objects.count())

    CoconutConflict.objects.get(
        business=push_to, coconut=really_short_horses, code='677',
        name='Really short horses', system_coconut=False)
    CoconutConflict.objects.get(
        business=other, coconut=really_short_horses, code='766',
        name='Really short horses', system_coconut=False)
    CoconutConflict.objects.get(
        business=other, coconut=many_opinions, code='2200',
        name='Many opinions were shared', system_coconut=False)
    CoconutConflict.objects.get(
        business=push_to, coconut=many_opinions, code='2200',
        name='Sales Tax', system_coconut=True)

  def test_get_data(self):
    coconut = get_test_coconut(
        code='766',
        name='Really short horses',
        owner_type='a',
        operator_type='b',
        tax_type='c',
        owner_class='d',
        operator_class='e',
        reporting_code='f',
        owner_reporting_code_name='g',
        operator_reporting_code_name='h',
        description='i')
    owner_data = {
        'Code': '766',
        'Name': 'Really short horses',
        'Type': 'a',
        'TaxType': 'c',
        'Description': 'i',
        'Class': 'd',
        'ReportingCode': 'f',
        'ReportingCodeName': 'g'}
    operator_data = {
        'Code': '766',
        'Name': 'Really short horses',
        'Type': 'b',
        'TaxType': 'c',
        'Description': 'i',
        'Class': 'e',
        'ReportingCode': 'f',
        'ReportingCodeName': 'h'}
    self.assertEqual(owner_data, coconut.get_data(OWNER))
    self.assertEqual(operator_data, coconut.get_data(OPERATOR))

  def test_validate_resolution_and_views_and_resolve(self):
    Business.objects.init_businesses()
    stayd = Business.objects.get(name='STAYD Inc')
    execres = Business.objects.get(name='ExecResidence Housing LLC')
    coconut = get_test_coconut(code='655', name='Company Software')
    stayd_software_conflict = get_test_coconut_conflict(
        business=stayd, coconut=coconut, name='Company Software', code='655')
    execres_barfware_conflict = get_test_coconut_conflict(
        business=execres, coconut=coconut, name='Company Barfware', code='655')

    # test views
    self.login(is_superuser=True)
    self.assert_get_contains(
        reverse('conflicted_coconuts'), 'Company Software')
    self.assert_get_contains(
        reverse('conflicted_coconut', kwargs={'pk': coconut.pk}),
        'Company Software')

    # test_validate_resolution
    post = {
        'name_{}'.format(stayd_software_conflict.pk): 'Company Software',
        'code_{}'.format(stayd_software_conflict.pk): '655',
        'name_{}'.format(execres_barfware_conflict.pk): 'Company Barfware',
        'code_{}'.format(execres_barfware_conflict.pk): '655'}
    self.assertEqual([(
        'STAYD Inc and ExecResidence Housing LLC are using the same code, '
        'but different names.')], Coconut.objects.validate_resolution(post))
    post = {
        'name_{}'.format(stayd_software_conflict.pk): 'Company Software',
        'code_{}'.format(stayd_software_conflict.pk): '666',
        'name_{}'.format(execres_barfware_conflict.pk): 'Company Software',
        'code_{}'.format(execres_barfware_conflict.pk): '555'}
    self.assertEqual([(
        'STAYD Inc and ExecResidence Housing LLC are using the same name, '
        'but different codes.')], Coconut.objects.validate_resolution(post))
    post = {
        'name_{}'.format(stayd_software_conflict.pk): 'Company Golfware',
        'code_{}'.format(stayd_software_conflict.pk): '777',
        'name_{}'.format(execres_barfware_conflict.pk): 'Company Golfware',
        'code_{}'.format(execres_barfware_conflict.pk): '777'}
    self.assertEqual([], Coconut.objects.validate_resolution(post))

    # test resolve
    stayd_api = FakeAccountsAPI(
        [{'AccountID': 'sdsds', 'Name': 'Company Software', 'Code': '655'}])
    execres_api = FakeAccountsAPI(
        [{'AccountID': 'qwqwq', 'Name': 'Company Barfware', 'Code': '655'}])
    api_lookup = {
        stayd.consumer_key: stayd_api, execres.consumer_key: execres_api}

    Coconut.objects.resolve(post, api_lookup)

    self.assertEqual(
        {'AccountID': 'sdsds', 'Name': 'Company Golfware', 'Code': '777'},
        stayd_api.account_by_code('777'))
    self.assertEqual(
        {'AccountID': 'qwqwq', 'Name': 'Company Golfware', 'Code': '777'},
        execres_api.account_by_code('777'))
    self.assertFalse(CoconutConflict.objects.filter(
        pk=stayd_software_conflict.pk).exists())
    self.assertFalse(CoconutConflict.objects.filter(
        pk=execres_barfware_conflict.pk).exists())
    coconut.refresh_from_db()
    self.assertEqual('777', coconut.code)
    self.assertEqual('Company Golfware', coconut.name)

  def test_copy_chart_of_accounts(self):
    only_in_from = {
        'AccountID': '00000000-1111', 'Code': '111', 'Name': 'One'}
    only_in_to = {
        'AccountID': '77777777-2222', 'Code': '222', 'Name': 'Two'}
    in_both_from = {
        'AccountID': '00000000-3333', 'Code': '333', 'Name': 'Three'}
    in_both_to = {
        'AccountID': '77777777-3333', 'Code': '333', 'Name': 'Three'}
    same_name_from = {
        'AccountID': '00000000-4444', 'Code': '444 from', 'Name': 'Four'}
    same_name_to = {
        'AccountID': '77777777-4444', 'Code': '444 to', 'Name': 'Four'}
    same_code_from = {
        'AccountID': '00000000-5555', 'Code': '555', 'Name': 'Five from'}
    same_code_to = {
        'AccountID': '77777777-5555', 'Code': '555', 'Name': 'Five to'}
    from_api = FakeAccountsAPI([
        only_in_from, in_both_from, same_name_from, same_code_from,
        SYSTEM_ACCOUNT])
    to_api = FakeAccountsAPI([
        only_in_to, in_both_to, same_name_to, same_code_to])
    Coconut.objects.copy_chart_of_accounts(from_api, to_api)
    expected = [
        {'Code': '111', 'Name': 'One'},
        {'AccountID': '77777777-2222', 'Code': '222', 'Name': 'Two'},
        {'AccountID': '77777777-3333', 'Code': '333', 'Name': 'Three'},
        {'AccountID': '77777777-4444', 'Code': '444 from', 'Name': 'Four'},
        {'AccountID': '77777777-5555', 'Code': '555', 'Name': 'Five from'}]
    got = list(sorted(to_api.accounts(), key=lambda x: x['Code']))
    self.assertEqual(expected, got)

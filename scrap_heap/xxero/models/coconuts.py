""" Xero is turned off! We can completely rip this stuff out.

Ready for this confusion? Bank accounts and Chart of accounts accounts
(Coconuts) are almost exactly the same object in Xero land. In programmer land,
you add a Coconut to a Transaction. In accountant land, you move a transaction
to an account. """
import re

from django.db import models
from django.shortcuts import reverse

from commands.models import background_command
from errors.models import Notifier, log_error
from util.background import background
from xxero.models.businesses import Business, OWNER, OPERATOR


@background_command
def sync_coconuts_background():
  Coconut.objects.sync()


class BankAccountManager(models.Manager):
  def sync_account(self, account_dict, business):
    account_id = account_dict['AccountID']
    name = account_dict['Name']
    account = self._get_existing_account(account_id, name, business)
    if not account:
      account = BankAccount()
    if (not account.account_id) or account.name != name:
      account.name = name
      # If an account exists with the name but no id, that account probably
      # exists because we heard about it in a transfer where we don't get an
      # id.
      account.account_id = account_id
      account.business = business
      account.save()
    if account.business:
      if account.business != business:
        log_error(
            'Same bank account for different businesses?!', '{} {} {}'.format(
                account_dict, business, account.business))
    else:
      account.business = business
      account.save()
    return account

  def _get_existing_account(self, account_id, name, business):
    by_id = self.filter(account_id=account_id).first()
    if by_id:
      return by_id
    return self.filter(
        account_id__isnull=True, name=name, business=business).first()

  def get_by_name_and_business(self, name, business):
    return self.get_or_create(name=name, business=business)[0]


class BankAccount(models.Model):
  account_id = models.UUIDField(
      blank=True, null=True, db_index=True, unique=True, help_text=(
          'This can be null because bank transfers only come back with '
          'a name for the account transfered from.'))
  name = models.CharField(max_length=200)
  business = models.ForeignKey(
      Business, on_delete=models.PROTECT, help_text=(
          'Transfer line items simply say bank account name, and different '
          'businesses can have bank accounts with the same name.'))

  objects = BankAccountManager()

  def __repr__(self):
    return '<BankAccount {}: {}>'.format(self.pk, self.name)

  def __str__(self):
    return self.name


class ConflictAnswer(object):
  """ This describes a new code and name to resolve the given conflict. It
  gets passed to a background function, so I'm avoiding pushing a potentially
  large object through the background pipeline by lazy loading
  coconut_conflict. """
  def __init__(self, coconut_conflict_id):
    self.coconut_conflict_id = coconut_conflict_id
    self._coconut_conflict = None
    self.code = None
    self.name = None

  def get_coconut_conflict(self):
    if not self._coconut_conflict:
      self._coconut_conflict = CoconutConflict.objects.get(
          pk=self.coconut_conflict_id)
    return self._coconut_conflict


@background
def push_coconut_resolution(answer, api_lookup):
  api = answer.get_coconut_conflict().business.get_api(api_lookup)
  data = api.account_by_code(answer.get_coconut_conflict().code)
  data['Code'] = answer.code
  data['Name'] = answer.name
  # Cannot update account details and STATUS on the same request (even if
  # you're updating to the exact same status). Status is always there in
  # real ones, but not necessarily in tests.
  if 'Status' in data:
    del data['Status']
  api.save_account(data)
  coconut = answer.get_coconut_conflict().coconut
  coconut.code = answer.code
  coconut.name = answer.name
  coconut.save()
  answer.get_coconut_conflict().delete()


class CoconutManager(models.Manager):
  def validate_resolution(self, post):
    """ Is this submitted set of names and codes a valid resolution? """
    resolution = self._get_resolution(post)
    problems = []
    for i in range(len(resolution)):
      for j in range(i + 1, len(resolution)):
        i_business = resolution[i].get_coconut_conflict().business.name
        j_business = resolution[j].get_coconut_conflict().business.name
        codes_match = resolution[i].code == resolution[j].code
        names_match = resolution[i].name == resolution[j].name
        if codes_match and not names_match:
          problems.append(
              '{} and {} are using the same code, but different names.'.format(
                  i_business, j_business))
        if names_match and not codes_match:
          problems.append((
              '{} and {} are using the same name, '
              'but different codes.').format(
                  i_business, j_business))
    return problems

  def _get_resolution(self, post):
    """ post variables are like
    code_{{ conflict.pk }}
    name_{{ conflict.pk }}. This returns a list of ConflictAnswer objects which
    describe the proposed solution to the problem. """
    lookup = {}  # conflict.pk -> ConflictAnswer
    field_finder = re.compile(r'(code|name)_(\d+)')
    for key, value in post.items():
      match = field_finder.match(key)
      if match:
        code_or_name, pk = match.groups()
        pk = int(pk)
        conflict_answer = lookup.get(pk, None)
        if not conflict_answer:
          conflict_answer = ConflictAnswer(pk)
          lookup[pk] = conflict_answer
        if code_or_name == 'code':
          conflict_answer.code = value
        elif code_or_name == 'name':
          conflict_answer.name = value
    return list(lookup.values())

  def resolve(self, post, api_lookup=None):
    """ Use the submitted set of names and codes as a resolution. post should
    have returned an empty list from validate_resolution. """
    for answer in self._get_resolution(post):
      push_coconut_resolution(answer, api_lookup)

  def push(self, business, notifier=None, api_lookup=None):
    """ For each Coconut in the master list, either it's already there or put
    it there.. """
    existing_codes = set()
    api = business.get_api(api_lookup)
    for data in self.api_coconuts(api):
      self.sync_data(
          data, business.get_operator_or_owner(), notifier, api_lookup)
      existing_codes.add(data['Code'])
    for coconut in Coconut.objects.all():
      if not coconut.coconutconflict_set.exists() and (
          coconut.code not in existing_codes):
        api.save_account(coconut.get_data(business.get_operator_or_owner()))

  def copy_chart_of_accounts(self, from_api, to_api):
    """ So for instance you could do
    execres_api = API(consumer_key=settings.XERO_EXEC_RESIDENCE_CONSUMER_KEY)
    hihoward_api = API(
        consumer_key=settings.XERO_HI_HOWARD_OPERATIONS_CONSUMER_KEY)
    copy_chart_of_account(execres_api, hihoward_api)

    All owners share the same chart of accounts. StaydInc has its own very
    special mostly-the-same-but-slightly-different chart of accouts. For
    owners, the management fee is an expense. For Stayd Inc, its income. """
    for account_dict in from_api.accounts():
      code = account_dict.get('Code', None)
      if not code:
        continue
      # System accounts may not be created
      if account_dict.get('SystemAccount', None):
        continue
      name = account_dict['Name']
      existing_by_code = to_api.account_by_code(code)

      def _fix_status(data):
        # Status is always present in real accounts. The default is for tests.
        if data.get('Status', None) != account_dict.get('Status', None):
          log_error(
              'copy_chart_of_accounts needs to handle status',
              'Trying to copy {} to {}'.format(data, account_dict))
        # Cannot update account details and STATUS on the same request (even if
        # you're updating to the exact same status)
        if 'Status' in data:
          del data['Status']
        return data
      if existing_by_code:
        if existing_by_code['Name'] != name:
          existing_by_code['Name'] = name
          to_api.save_account(_fix_status(existing_by_code))
      else:
        existing_by_name = to_api.account_by_name(name)
        if existing_by_name:
          existing_by_name['Code'] = code
          to_api.save_account(_fix_status(existing_by_name))
        else:
          del account_dict['AccountID']
          to_api.save_account(account_dict)

  def sync(self, notifier=None, api_lookup=None):
    to_return = []
    for business in Business.objects.all():
      api = business.get_api(api_lookup)
      for coconut_data in self.api_coconuts(api):
        coconut = self.sync_data(
            coconut_data, business.get_operator_or_owner(), notifier,
            api_lookup)
        to_return.append(coconut)
    return to_return

  def get_by_code(self, code, api):
    """ Xero will send transactions back, like,
    'LineItems': [{'AccountCode': 'BENTO1', ...
    and at the same time send back a list of Coconuts, like,
    'Name': 'Bento Reconciliation', 'Code': 'Bento1' """
    coconut = self.filter(code__iexact=code).first()
    if coconut:
      return coconut
    by_code = api.account_by_code(code)
    if by_code:
      return self.sync_data(by_code, OWNER)

  def sync_data(
      self, coconut_data, owner_or_operator, notifier=None, api_lookup=None):
    """ The master list is for pushing and synchonizing charts of accounts.
    You can't create or modify system accounts so for now I just don't put
    system accounts in the master list when you sync them. But I do detect
    conflicts.

    If you aren't sure on owner_or_operator, it's probably not a big deal.
    The vast majority of the time it's the same either way, and if not,
    it'll get rectified when we sync Coconuts which happens nightly. """
    if 'UpdatedDateUTC' in coconut_data:
      # "Object of type 'datetime' is not JSON serializable" and anyway this
      # field is useless.
      del coconut_data['UpdatedDateUTC']
    notifier = notifier or Notifier()
    code = coconut_data['Code']
    name = coconut_data['Name']
    coconut = self.filter(code=code, name=name).first()
    if not coconut:
      existing_name = self.filter(name=name).first()
      existing_code = self.filter(code=code).first()
      conflicted_coconut = existing_name or existing_code
      if conflicted_coconut:
        if conflicted_coconut.create_coconut_conflicts(api_lookup):
          # I used to alert here, but we aren't using Xero any more.
          pass
        return
      coconut = Coconut(code=code, name=name)
    if coconut_data.get('SystemAccount', None):
      return
    if owner_or_operator == OWNER or not coconut.pk:
      coconut.owner_type = coconut_data['Type']
    if owner_or_operator == OPERATOR or not coconut.pk:
      coconut.operator_type = coconut_data['Type']
    coconut.tax_type = coconut_data['TaxType']
    if owner_or_operator == OWNER or not coconut.pk:
      coconut.owner_class = coconut_data['Class']
    if owner_or_operator == OPERATOR or not coconut.pk:
      coconut.operator_class = coconut_data['Class']
    coconut.reporting_code = coconut_data['ReportingCode']
    rcn = coconut_data.get('ReportingCodeName', None)
    if owner_or_operator == OWNER or not coconut.pk:
      coconut.owner_reporting_code_name = rcn
    if owner_or_operator == OPERATOR or not coconut.pk:
      coconut.operator_reporting_code_name = rcn
    coconut.description = coconut_data['Description']
    coconut.save()
    return coconut

  def api_coconuts(self, api):
    return [acc for acc in api.accounts() if self._is_coconut(acc)]

  def _is_coconut(self, account_dict):
    has_code = bool(account_dict.get('Code', None))
    is_active = account_dict['Status'] == 'ACTIVE'
    return has_code and is_active

  def conflicted(self):
    return set([cc.coconut for cc in CoconutConflict.objects.all()])


class Coconut(models.Model):
  """ A Chart of Accounts is a list of (code, name) tuples. Every transaction
  gets one of these tuples. It's a form of categorization. An example would be
  ('655', 'Company Software') which would be a good one for that time you spent
  $40 on software.

  So what do we call one of these tuples. Well accountants call them Accounts.
  I have a hard time imagining a more confusing term. In my world, an Account
  is, like, my Facebook Account, or maybe a Bank Account.  I was calling them
  "Chart of accounts... account" and I think we should still do that in the
  outside world for clarity. But for brevity sake, in here I started calling
  them "CoaAccount" and from there the obvious move is to call them "Coconut".

  In Xero, every business (Stayd Inc, ExecResidence Housing LLC, things that
  show in the upper left drop down on Xero) gets its own chart of accounts.
  Here's how we manage that. The Coconut table contains our master chart.
  Whenever any business we manage adds a new Coconut, it gets added to this
  list too. When we create a new business, we set it up with our master chart.

  We only complain when somebody creates or modifies a Coconut on Xero such
  that it has the same code but a different name, or the same name but a
  different code, to an existing Coconut in this master chart.

  While each Xero copy of a Coconut (should) have the same code and name, some
  of the metadata may be different. For example, we're the only operator, and
  for our business/XERO_HI_HOWARD_OPERATIONS_CONSUMER_KEY, "management fees"
  are income. For our owners (an example being
  XERO_EXEC_RESIDENCE_CONSUMER_KEY) "management fees" are an expense. Hence the
  distinction between, for example, owner_class and operator_class.

  I'm still not totally clear on how to handle System Accounts. The API can't
  create, change, or delete them for starters. """
  code = models.CharField(unique=True, max_length=10, help_text=(
      'Typically a number in the hundreds, but sometimes a string like '
      'Bento1.'))
  name = models.CharField(unique=True, max_length=200, help_text=(
      'For example, Company Software'))

  # Type examples include 'BANK', 'CURRENT', 'CURRLIAB', 'DEPRECIATN',
  # 'DIRECTCOSTS', 'EQUITY', 'EXPENSE', 'FIXED', 'INVENTORY', 'OTHERINCOME',
  # 'REVENUE', 'SALES', 'TERMLIAB'}
  owner_type = models.CharField(max_length=20)
  operator_type = models.CharField(max_length=20)

  # Examples include {'INPUT', 'NONE', 'OUTPUT'}
  tax_type = models.CharField(max_length=20)

  # Examples include {'ASSET', 'EQUITY', 'EXPENSE', 'LIABILITY', 'REVENUE'}
  owner_class = models.CharField(max_length=20)
  operator_class = models.CharField(max_length=20)

  # Examples include {'ASS', 'ASS.CUR.CAS.CAS', 'ASS.CUR.INY',
  # 'ASS.CUR.REC.ACR', 'ASS.CUR.REC.PRE', 'ASS.NCA.FIX.PLA',
  # 'ASS.NCA.FIX.PLA.ACC', 'ASS.NCA.FIX.VEH', 'ASS.NCA.FIX.VEH.ACC', 'EQU',
  # 'EQU.ADV', 'EQU.DRA', 'EQU.RET', 'EXP', 'EXP.ADV', 'EXP.BAD', 'EXP.COS',
  # 'EXP.DEP', 'EXP.ENT', 'EXP.FOR.UGL', 'EXP.GEX', 'EXP.TAX', 'EXP.VEH',
  # 'LIA', 'LIA.CUR', 'LIA.CUR.ACC', 'LIA.CUR.DEF', 'LIA.CUR.LOA',
  # 'LIA.CUR.PAY.EMP', 'LIA.CUR.PAY.TRA', 'LIA.CUR.TAX.SAL', 'REV', 'REV.OTH',
  # 'REV.SAL.GOO'}
  reporting_code = models.CharField(max_length=30)

  # Examples include {'', 'Assets', 'Cash', 'Cash on hand', "Equity/Owners'
  # capital", 'Expense', 'Employee-related liabilites  (wages, vacation leave,
  # etc)', 'Liabilities', 'Revenue'}
  owner_reporting_code_name = models.CharField(
      max_length=200, blank=True, null=True)
  operator_reporting_code_name = models.CharField(
      max_length=200, blank=True, null=True)

  description = models.TextField()

  def get_data(self, owner_or_operator):
    # Note that by returning a dict without an 'AccountID' I'm making it so
    # you'll create a new account if you save it with the API.
    if owner_or_operator == OWNER:
      ttype = self.owner_type
      cclass = self.owner_class
      reporting_code_name = self.owner_reporting_code_name
    elif owner_or_operator == OPERATOR:
      ttype = self.operator_type
      cclass = self.operator_class
      reporting_code_name = self.operator_reporting_code_name
    else:
      raise Exception(owner_or_operator)
    return {
        'Code': self.code,
        'Name': self.name,
        'Type': ttype,
        'TaxType': self.tax_type,
        'Description': self.description,
        'Class': cclass,
        'ReportingCode': self.reporting_code,
        'ReportingCodeName': reporting_code_name}

  def create_coconut_conflicts(self, api_lookup=None):
    for business in Business.objects.get_all():
      coconut_conflict = CoconutConflict.objects.filter(
          coconut=self, business=business).first()
      if not coconut_conflict:
        coconut_conflict = CoconutConflict(coconut=self, business=business)
      api_lookup = api_lookup or Business.objects.get_api_lookup()
      api = api_lookup[business.consumer_key]
      account_dict_by_name = api.account_by_name(self.name)
      account_dict_by_code = api.account_by_code(self.code)
      account_dict = account_dict_by_name or account_dict_by_code
      # Not every business necessarily has the coconut in question.
      if account_dict:
        coconut_conflict.code = account_dict['Code']
        coconut_conflict.name = account_dict['Name']
        coconut_conflict.system_coconut = bool(
            account_dict.get('SystemAccount', None))
        coconut_conflict.save()
    self.clean_up_unnecessary_conflicts()
    return self.coconutconflict_set.exists()

  def clean_up_unnecessary_conflicts(self):
    """ I assume that at this point we've synced with all businesses and have a
    complete picture of what they all believe the coconuts to be. """
    if self.conflict_actually_exists():
      return False
    for conflict in self.coconutconflict_set.all():
      by_code = Coconut.objects.filter(code=conflict.code).first()
      by_name = Coconut.objects.filter(name=conflict.name).first()
      if by_code and not by_name:
        by_code.name = conflict.name
        by_code.save()
      elif by_name and not by_code:
        by_name.code = conflict.code
        by_name.save()
      elif not by_name and not by_code:
        Coconut.objects.create(code=conflict.code, name=conflict.name)
      conflict.delete()
    return True

  def conflict_actually_exists(self):
    conflicts = list(self.coconutconflict_set.all())
    for i in range(len(conflicts)):
      for j in range(len(conflicts)):
        if i != j:
          codes_equal = conflicts[i].code == conflicts[j].code
          names_equal = conflicts[i].name == conflicts[j].name
          if codes_equal != names_equal:
            return True
    return False

  def conflict_url(self):
    return reverse('conflicted_coconut', kwargs={'pk': self.pk})

  objects = CoconutManager()

  def __repr__(self):
    return '<Coconut {}: {}, {}>'.format(self.pk, self.code, self.name)

  def __str__(self):
    return self.__repr__()

  class Meta:
    ordering = ('code',)


class CoconutConflict(models.Model):
  """ What does this particular business think this particular Coconut is? """
  business = models.ForeignKey(Business, on_delete=models.CASCADE)
  coconut = models.ForeignKey(Coconut, on_delete=models.CASCADE)
  code = models.CharField(max_length=10, help_text=(
      'What does this business think the code is?'))
  name = models.CharField(max_length=200, help_text=(
      'What does this business think the name is?'))
  system_coconut = models.BooleanField(default=False, help_text=(
      'The trick with systme coconuts is that you cant modify them.'))

  def __repr__(self):
    return '<CoconutConflict {}: {} {}>'.format(self.pk, self.code, self.name)

  def __str__(self):
    return self.__repr__()

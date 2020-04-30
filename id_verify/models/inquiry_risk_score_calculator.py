""" Inquiry level reservations should have a whole rad automated workflow. But
we're not totally sure what that looks like yet. We ran out of money to use
Typeform I guess, so the team really just needs a web form they can use in the
meantime. """

from django import forms


class InquiryRiskScoreForm(forms.Form):
  is_airbnb = forms.BooleanField(
      label='Did the guest book on Airbnb?', required=False)
  has_negative_reviews = forms.BooleanField(
      label='Does the guest have any negative reviews? (only on Airbnb)',
      required=False)
  is_reserving_for_self = forms.BooleanField(
      label='Is the guest making the reservation staying in the apartment?',
      required=False)
  explained_purpose = forms.BooleanField(label=(
      'Did the guest include a message with their initial request explaining '
      'the purpose of their trip?'), required=False)
  positive_review_count = forms.IntegerField(label=(
      'How many positive reviews does the guest have? (only on Airbnb)'))
  old_enough = forms.ChoiceField(label=(
      'How old is the guest?'), choices=[
          ('young', 'Younger than 25'),
          ('old', 'Older than 25'),
          ('no_idea', 'Don\'t know')])
  too_close = forms.BooleanField(label=(
      'Is the guest located within 45 miles of the listing?'), required=False)
  guest_count = forms.IntegerField(label=(
      'How many guests are on the reservation?'))
  night_count = forms.IntegerField(label=(
      'How many nights the reservation for?'))
  starts_fri_or_sat = forms.BooleanField(label=(
      'Does the reservation start on a Friday or Saturday?'), required=False)
  days_out = forms.ChoiceField(label=(
      'How many days out did the guest book?'), choices=[
          (0, 'Same day'),
          (3, '1-3 days before their stay'),
          (7, '4-7 days before their stay'),
          (8, '8 or more days before their stay')])

  def score(self):
    if self.is_valid():
      score = 0
      if not self.cleaned_data['is_airbnb']:
        score += 5
      if self.cleaned_data['has_negative_reviews']:
        score += 100
      if not self.cleaned_data['is_reserving_for_self']:
        score += 10
      if not self.cleaned_data['explained_purpose']:
        score += 10
      positive_review_count = self.cleaned_data['positive_review_count']
      if isinstance(positive_review_count, str):
        raise Exception()
      if positive_review_count == 0:
        score += 10
      elif positive_review_count == 1:
        pass
      elif positive_review_count <= 4:
        score -= 5
      elif positive_review_count <= 7:
        score -= 7
      else:
        score -= 10
      if self.cleaned_data['old_enough'] == 'young':
        score += 40
      if self.cleaned_data['too_close']:
        score += 75
      guest_count = self.cleaned_data['guest_count']
      if guest_count >= 6:
        score += 10
      elif guest_count == 5:
        score += 5
      night_count = self.cleaned_data['night_count']
      if night_count == 1:
        score += 15
      elif night_count == 2:
        score += 10
      if self.cleaned_data['starts_fri_or_sat']:
        score += 20
      days_out = int(self.cleaned_data['days_out'])
      if days_out == 0:
        score += 15
      elif days_out == 3:
        score += 10
      elif days_out == 7:
        pass
      elif days_out == 8:
        score -= 5
      else:
        raise Exception(days_out)
      return score

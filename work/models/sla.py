NOW = 'Now (< 4 hours)'
URGENT = 'Urgent (< 24 hours)'
NEXT_CHECKOUT = 'Next checkout'
NEXT_VACANT_NIGHT = 'Next vacant night'
NEXT_VISIT = 'Next visit to property'
DONT_SCHEDULE = 'Don\'t schedule'
SLAS = [
    NOW, URGENT, NEXT_CHECKOUT, NEXT_VISIT, NEXT_VACANT_NIGHT, DONT_SCHEDULE]
SLA_CHOICES = [(sla, sla) for sla in SLAS]

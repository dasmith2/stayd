class ReportableField {
  constructor(key, name, is_money) {
    this.key = key;
    this.name = name;
    this.is_money = is_money;
  }
}

var reportable_fields = [
    new ReportableField('net', 'Net revenue', true),
    new ReportableField('total_income', 'Total income', true),
    new ReportableField('total_expenses', 'Total expenses', true),
    new ReportableField('rent', 'Market rent', true),
    new ReportableField('nights_available', 'Max occupancy', false),
    new ReportableField('nights_occupied', 'Occupied rooms', false),
    new ReportableField('occupancy_rate', '% occupancy', false),
    new ReportableField('adr', 'ADR', true),
    new ReportableField('rev_par', 'RevPAR', true),
    new ReportableField('cleaning_fees', 'Cleaning fees', true),
    new ReportableField('channel_fees', 'Channel fees', true),
    new ReportableField('taxes', 'Taxes', true)];

var reportable_field_lookup = {};
reportable_fields.forEach(function(field) {
  reportable_field_lookup[field.key] = field;
});

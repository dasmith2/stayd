class ReportableField {
  constructor(key, name, is_money) {
    this.key = key;
    this.name = name;
    this.is_money = is_money;
  }
}

var reportable_fields = [
    new ReportableField('net', 'Net revenue', true),
    new ReportableField('revenue', 'Revenue', true),
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

var use_series = [];

function create_series_checkboxes(on_change_callback) {
  var outer_box = $("#series_checkboxes").empty();
  reportable_fields.forEach(function(field) {
    var label = $("<label></label>");
    var box = $("<input type='checkbox'>");
    label.append(box);
    label.append(field.name);
    outer_box.append(label);

    box.prop('checked', use_series.indexOf(field.key) !== -1);
    box.change(function() {
      var index = use_series.indexOf(field.key);
      var checked = $(this).is(':checked');
      if (index !== -1 && !checked) {
        use_series.splice(index, 1);
      } else if (index == -1 && checked) {
        use_series.push(field.key);
      }
      on_change_callback();
      set_query_string();
    });
  });
}

function set_use_series_by_query_string() {
  var query_str_obj = get_query_string_obj();
  var series = query_str_obj['series'];
  if (series) {
    use_series = series.split(',');
  }
}

function set_query_string() {
  var qs_obj = get_query_string_obj();
  var new_options = get_options_object();
  for (var key in new_options) {
    if (typeof new_options[key] == 'undefined') {
      if (key in qs_obj) {
        delete qs_obj[key];
      }
    }
    qs_obj[key] = new_options[key];
  }
  var new_url = window.location.pathname + query_string_obj_to_str(qs_obj);
  window.history.pushState('whatever', get_page_title(), new_url);
}

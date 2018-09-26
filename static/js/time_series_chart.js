class TimeSeriesChart {
  constructor() {
    // All that really matters is the ratio between the width and the height.
    // The chart expands to fill the width of the containing element.
    this.width = 200;
    this.height = 50;
    this.all_datasets = {};
    var me = this;
    reportable_fields.forEach(function(field) {
      me.all_datasets[field.key] = {label: field.name, data: []};
    });
    this.labels = [];
    this.clear_chart_datasets();
  }

  load_points(fromDate, toDate, interval, ownerId, callback) {
    var urlBase = '/stats/time_series_data/' + interval;
    var fromDateString = server_date_format(fromDate);
    var toDateString = server_date_format(toDate);
    var url =
        urlBase + '/' + fromDateString + '/' + toDateString
        + '?owner_id=' + ownerId;
    var me = this;
    $.get(url, function(data) {
      data.results.forEach(function(point) {
        me.add_point(point);
      });
      callback();
    });
  }

  add_point(point) {
    this.labels.push(point.label);
    for (var key in point) {
      if (key in this.all_datasets) {
        this.all_datasets[key].data.push(Math.round(point[key]));
      }
    }
  }

  clear_chart_datasets() {
    this.chart_datasets = [];
    this.hasMoneyYAxis = false;
  }

  add_chart_dataset(field_key, color) {
    this.hasMoneyYAxis =
        this.hasMoneyYAxis
        || reportable_field_lookup[field_key].is_money;
    var dataset = this.all_datasets[field_key];
    dataset.backgroundColor = 'rgba(0, 0, 0, 0.0)'; // Full transparency
    dataset.borderColor = color;
    dataset.lineTension = 0.1;
    this.chart_datasets.push(dataset);
  }

  put_chart_in(chart_holder, options) {
    if (!options) {
      options = {};
    }
    var me = this;
    options['scales'] = {
      yAxes: [{
        ticks: {
          beginAtZero: true,
          callback: function(value, index, values) {
            if (me.hasMoneyYAxis) {
              return formatMoney(value);
            }
            return value;
          }
        }
      }]
    };
    chart_holder.empty();
    var canvas = $("<canvas/>");
    if (this.width) {
      canvas.width(this.width);
    }
    if (this.height) {
      canvas.height(this.height);
    }
    chart_holder.append(canvas)
    var ctx = canvas[0].getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
          labels: this.labels,
          datasets: this.chart_datasets
        },
        options: options
    });
  }
}

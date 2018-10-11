class Series {
  constructor(label, data, type, color, point_color) {
    this.label = label;
    this.data = data;
    this.type = type;
    this.color = color;
    this.point_color = point_color;
  }
}

function draw_dashboard_chart() {
  // Put the bars last so they go in back. Put the Future revenue bar dead last
  // so it's stacked on top of Past Revenue.
  var serieses = [
    //new Series('Future profit', booked_profit_data, 'line', '#ac9800'),
    new Series('Profit', past_profit_data, 'line', '#d9b8ed', '#8573e9'),
    //new Series('Future expenses', booked_expenses_data, 'line', '#9700ac'),
    //new Series('YTD expenses', past_expenses_data, 'line', '#640071'),
    new Series('Booked revenue', past_income_data, 'bar', 'rgba(0, 143, 230, 1)'),
    new Series(
        'Future bookings', booked_income_data, 'bar', 'rgba(207, 233, 251, 1)')
    // We're thinking it's just a bad idea to include projected revenue. new
    // Series('Projected revenue', projected_income_data, 'line', '#00eace'),
  ];
  var use_max = 0;
  var use_min = 0;
  for (var i = 0; i < serieses.length; i++) {
    var data = serieses[i].data;
    for (var j = 0; j < data.length; j++) {
      if (typeof data[j] == 'number') {
        use_max = Math.max(use_max, data[j]);
        use_min = Math.min(use_min, data[j]);
      }
    }
  }
  var new_min_max = nice_min_max(use_min, use_max);
  use_min = new_min_max[0];
  use_max = new_min_max[1];

  var chart_holder = $('#chart_holder');
  var chart = new ChartBase();
  chart.hasMoneyYAxis = true;
  chart.type = 'bar';
  chart.labels = month_labels;
  chart.width = 200;
  chart.height = 100;

  for (var i = 0; i < serieses.length; i++) {
    var series = serieses[i];
    var dataset = {
      label: series.label,
      data: series.data,
      type: series.type
    };
    if (series.type == 'bar') {
      dataset.yAxisID = 'bar-stacked';
      dataset.backgroundColor = series.color;
    } else if (series.type == 'line') {
      dataset.yAxisID = 'line-unstacked';
      dataset.backgroundColor = 'rgba(0, 0, 0, 0.0)'; // Full transparency
      dataset.borderColor = series.color;
      dataset.borderWidth = 2.5;
      dataset.lineTension = 0.6;
      dataset.pointRadius = 3;
      dataset.pointBackgroundColor = series.point_color;
      dataset.pointBorderColor = series.point_color;
    } else {
      throw 'Unknown series type: ' + series.type;
    }
    if (series.label == 'Projected income') {
      dataset.borderDash = [10, 5];
    }
    chart.chart_datasets.push(dataset);
  }

  // This is a bit advanced. We want the bar charts stacked, but the line
  // graphs unstacked. So we make 2 yAxes entries. The first will mainly be
  // populated by put_chart_in and applies to the line data series. We can hide
  // one of the y axes lables because we use the same ticks in both.
  ticks = {
    beginAtZero: true,
    min: use_min,
    max: use_max,
    callback: function(value, index, values) {
      return readable_money(value);
    }
  };
  var options = {
    tooltips: {
      callbacks: {
        label: function(tooltipItem, data) {
          return serieses[tooltipItem.datasetIndex].label +
              ': ' + format_money(tooltipItem.yLabel);
        }
      }
    },
    legend: {
      display: true
    },
    scales: {
      xAxes: [{stacked: true}],
      yAxes: [
        {
          id: 'line-unstacked',
          stacked: false,
          ticks: ticks
        }, {
          id: 'bar-stacked',
          stacked: true,
          display: false, // OK because we use the same ticks in both axes
          ticks: ticks
        }
      ]
    }
  };
  chart.put_chart_in(chart_holder, options);
}

$(draw_dashboard_chart);
$(window).resize(draw_dashboard_chart);

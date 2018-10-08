class Series {
  constructor(label, data, color, type) {
    this.label = label;
    this.data = data;
    this.color = color;
    this.type = type;
  }
}

function draw_dashboard_chart() {
  // Put the bars last so they go in back.
  var serieses = [
    // We're thinking it's just a bad idea to include projected revenue. new
    // Series('Projected revenue', projected_income_data, '#00eace', 'line'),
    new Series('Future profit', booked_profit_data, '#ac9800', 'line'),
    new Series('Past profit', past_profit_data, '#716500', 'line'),
    new Series('Future expenses', booked_expenses_data, '#9700ac', 'line'),
    new Series('Past expenses', past_expenses_data, '#640071', 'line'),
    new Series('Past revenue', past_income_data, 'rgba(0, 113, 97, 1)', 'bar'),
    new Series(
        'Future revenue', booked_income_data, 'rgba(0, 172, 152, 1)', 'bar')
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
  use_min = niceNum(use_min, true);
  use_max = niceNum(use_max, true);

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
      dataset.lineTension = 0.1;
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
      display: false
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

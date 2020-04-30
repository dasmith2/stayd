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
  chart.width = 740;
  chart.height = 260;

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
    maxTicksLimit: 5,
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

$(function() {
  var canvas = $('#hardcoded_doughnut_holder canvas');
  var ctx = canvas[0].getContext('2d');

  new Chart(ctx,
    {
      type: 'doughnut',
      data: {
        labels: ['Gross Operating Profit'],
        datasets: [
          {
            data: [
              65,
              35
            ],
            borderColor: 'transparent',
            backgroundColor: [
              app.color.primary
            ],
            label: 'Trafic'
          }
        ]
      },
      options: {
        legend: {
          display: false
        },
        cutoutPercentage: 75
      }
    }
  );
});

/** (-16064, 93843) -> [-20000, 100000], (-16064, 83843) -> [-20000, 90000],
 * (-16064, 100001) -> [-100000, 200000], (0, 123) -> [0, 200]
 */
function nice_min_max(min, max) {
  if (min >= 0) {
    return [0, nice_round_up(max)];
  } else if (max < 0) {
    return [nice_round_up(min), 0];
  }
  var nice_min = nice_round_up(min);
  var nice_max = nice_round_up(max);
  if (first_digit(nice_max) == 1 && nice_max > -nice_min) {
    nice_min = -min_fifths_gt(nice_max, -nice_min);
  } else if (first_digit(nice_min) == 1 && -nice_min > nice_max) {
    nice_max = min_fifths_gt(-nice_min, nice_max);
  } else if (digit_count(nice_max) > digit_count(nice_min)) {
    nice_min = -first_digit_1_all_else_0(nice_max);
  } else if (digit_count(nice_max) < digit_count(nice_min)) {
    nice_max = -first_digit_1_all_else_0(nice_min);
  }
  return [nice_min, nice_max];
}

function min_fifths_gt(fifths_of, gt_what) {
  if (fifths_of < 0 || gt_what < 0) {
    throw 'Both arguments should be gt 0'
  }
  var one_fifth = fifths_of / 5;
  return Math.round(Math.ceil(gt_what / one_fifth) * one_fifth);
}

function first_digit(in_num) {
  return parseInt(('' + Math.abs(in_num)).split('')[0]);
}

// 1 -> 1, -21 -> 2, 321 -> 3, -4321 -> 4
function digit_count(in_num) {
  if (in_num < 0) {
    in_num *= -1;
  }
  return ('' + Math.round(in_num)).length
}

// 1 -> 1, -21 -> -10, 321 -> 100, -4321 -> -1000
function first_digit_1_all_else_0(for_num) {
  var negative = for_num < 0;
  if (negative) {
    for_num *= -1;
  }
  var digits = ('' + for_num).split('');
  digits[0] = '1';
  for (var i = 1; i < digits.length; i++) {
    digits[i] = '0';
  }
  for_num = parseInt(digits.join(''));
  if (negative) {
    for_num *= -1;
  }
  return for_num;
}

// 1 -> 2, -21 -> -30, 321 -> 400, -4321 -> -5000, 54321 -> 60000
function nice_round_up(range) {
  var negative = range < 0;
  if (negative) {
    range *= -1;
  }
  var digits = ('' + Math.round(range)).split('')
  digits[0] = '' + (parseInt(digits[0]) + 1)
  for (var i = 1; i < digits.length; i++) {
    digits[i] = '0';
  }
  range = parseInt(digits.join(''));
  if (negative) {
    range *= -1;
  }
  return range;
}

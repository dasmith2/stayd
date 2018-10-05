class Series {
  constructor(label, data, color, type) {
    this.label = label;
    this.data = data;
    this.color = color;
    this.type = type;
  }
}
$(function() {
  var series = [
    new Series('Booked revenue', booked_income_data, 'rgba(0, 172, 152, 1)', 'bar')
  ];
  var datas = [
      past_expenses_data, past_profit_data,
      booked_expenses_data, booked_profit_data,
      projected_income_data, past_income_data, booked_income_data];
  var use_max = 0;
  var use_min = 0;
  for (var i = 0; i < datas.length; i++) {
    var data = datas[i];
    for (var j = 0; j < data.length; j++) {
      if (typeof data[j] == 'number') {
        use_max = Math.max(use_max, data[j]);
        use_min = Math.min(use_min, data[j]);
      }
    }
  }
  use_min = niceNum(use_min, true);
  use_max = niceNum(use_max, true);
  // Keep these in sync with dashboard/dashboard.scss
  var colors = [
      '#417986', // rgb(65, 121, 134)
      '#67939e', // rgb(103, 147, 158)
      '#8daeb6', // rgb(141, 174, 182)
      '#324755', // rgb(50, 71, 85)
      '#5b6b77', // rgb(91, 107, 119)
      '#849099', // rgb(132, 144, 153)
      '#d79e80'] // rgb(215, 158, 128)
  var background_colors = [
      'rgba(65, 121, 134, 1)',
      'rgba(103, 147, 158, 1)',
      'rgba(141, 174, 182, 1)',
      'rgba(50, 71, 85, 1)',
      'rgba(91, 107, 119, 1)',
      'rgba(0, 113, 97, 1)',
      'rgba(0, 172, 152, 1)']
  var labels = [
      'Past expenses', 'Past profit', 'Booked expenses', 'Booked profit',
      'Projected revenue', 'Past revenue', 'Booked revenue']

  var chart = new ChartBase();
  chart.hasMoneyYAxis = true;
  chart.type = 'bar';
  chart.labels = month_labels;

  for (var i = 0; i < datas.length; i++) {
    var dataset = {
      label: labels[i],
      data: datas[i],
      backgroundColor: background_colors[i],
      borderColor: colors[i],
      lineTension: 0.1
    };
    if (labels[i] == 'Projected income') {
      dataset.borderDash = [10, 5];
    }
    if (labels[i] == 'Past revenue' || labels[i] == 'Booked revenue') {
      dataset.yAxisID = 'bar-stacked';
      dataset.type = 'bar';
    } else {
      dataset.yAxisID = 'line-unstacked';
      dataset.type = 'line';
      dataset.backgroundColor = 'rgba(0, 0, 0, 0.0)'; // Full transparency
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
    max: use_max
  };
  var options = {
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
  chart.put_chart_in($('#chart_holder'), options);
});

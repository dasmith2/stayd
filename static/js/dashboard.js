$(function() {
  window.past_income_data_was = past_income_data;
  var datas = [
      past_income_data, past_expenses_data, past_profit_data,
      booked_income_data, booked_expenses_data, booked_profit_data,
      projected_income_data]
  var colors = [
      '#ff9999',
      '#9999ff',
      '#99ff99',
      '#ffbb77',
      '#77bbff',
      '#bbff77',
      '#ff77bb']
  var labels = [
      'Past income', 'Past expenses', 'Past profit', 'Booked income',
      'Booked expenses', 'Booked profit', 'Projected income']

  var chart = new ChartBase();
  chart.labels = month_labels;

  for (var i = 0; i < datas.length; i++) {
    var dataset = {
      label: labels[i],
      data: datas[i],
      backgroundColor: 'rgba(0, 0, 0, 0.0)', // Full transparency
      borderColor: colors[i],
      lineTension: 0.1
    };
    if (labels[i] == 'Projected income') {
      dataset.borderDash = [10, 5];
    }
    chart.chart_datasets.push(dataset);
  }

  chart.put_chart_in($('#chart_holder'));
});

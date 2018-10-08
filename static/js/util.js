/* A Javascript version of readable in util/money.py
   123 -> 123
   1,234 -> 1.2k
   12,345 -> 12k
   123,456 -> 123k
   1,234,567 -> 1.2M */
function readable(num) {
  var suffix_i = 0;
  var on_num = num;
  while (on_num > 1000) {
    on_num = on_num / 1000.0;
    suffix_i++;
  }
  var display_num = Math.round(on_num);
  if (on_num < 10) {
    display_num = Math.round(on_num * 10) / 10.0;
  }
  return display_num + ['', 'K', 'M', 'B', 'T'][suffix_i];
}

function format_money(value) {
  if (parseInt(value) >= 1000) {
    return '$' + value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  } else {
    return '$' + value;
  }
}

function readable_money(value) {
  return '$' + readable(value);
}

/* Ripped (almost) directly from
https://github.com/chartjs/Chart.js/blob/master/src/core/core.helpers.js */
function niceNum(range, round) {
  var exponent = Math.floor(Math.log10(range));
  var fraction = range / Math.pow(10, exponent);
  var niceFraction;

  if (round) {
    if (fraction < 1.5) {
      niceFraction = 1;
    } else if (fraction < 3) {
      niceFraction = 2;
    } else if (fraction < 7) {
      niceFraction = 5;
    } else {
      niceFraction = 10;
    }
  } else if (fraction <= 1.0) {
    niceFraction = 1;
  } else if (fraction <= 2) {
    niceFraction = 2;
  } else if (fraction <= 5) {
    niceFraction = 5;
  } else {
    niceFraction = 10;
  }

  return niceFraction * Math.pow(10, exponent);
};

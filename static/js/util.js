/* A Javascript version of readable in util/money.py
   123 -> 123
   1,234 -> 1.2k
   12,345 -> 12k
   123,456 -> 123k
   1,234,567 -> 1.2M */
function readable(num, money) {
  var negative = num < 0;
  if (negative) {
    num *= -1;
  }
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
  display_num += ['', 'K', 'M', 'B', 'T'][suffix_i];
  if (money) {
    display_num = '$' + display_num;
  }
  if (negative) {
    display_num = '-' + display_num;
  }
  return display_num;
}

function format_money(value) {
  if (parseInt(value) >= 1000) {
    return '$' + value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  } else {
    return '$' + value;
  }
}

function readable_money(value) {
  return readable(value, true);
}

/** (100, 2123) -> [0, 3000], (-100, 2123) -> (-1000, 3000), (-2345, 3456) ->
 * (-3000, 4000), (-54321, 4321) -> [-60000, 10000], (-1234, -1000) -> [-2000,
 * 0]
 */
function nice_min_max(min, max) {
  if (min >= 0) {
    return [0, nice_round_up(max)];
  } else if (max < 0) {
    return [nice_round_up(min), 0];
  }
  var nice_min = nice_round_up(min);
  var nice_max = nice_round_up(max);
  if (digit_count(nice_max) > digit_count(nice_min)) {
    nice_min = -first_digit_1_all_else_0(nice_max);
  } else if (digit_count(nice_max) < digit_count(nice_min)) {
    nice_max = -first_digit_1_all_else_0(nice_min);
  }
  return [nice_min, nice_max];
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

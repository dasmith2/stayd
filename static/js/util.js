/* 123 -> 123
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

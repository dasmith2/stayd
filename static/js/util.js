/* This stuff should be widely useful and not specific to any particular corner
 * of the website. */

/* Form stuff, like validation messages */
function get_feedback_elt_after(after) {
  var feedback = after.parent().find('.feedback');
  if (!feedback.length) {
    feedback = $('<span class="feedback"></span>').insertAfter(after);
  }
  return feedback;
}

function get_feedback_elt_append(append) {
  var feedback = append.find('.feedback');
  if (!feedback.length) {
    feedback = $('<span class="feedback"></span>').appendTo(append);
  }
  return feedback;
}

/* csrf token stuff */
function add_csrf_token(data) {
  data['csrfmiddlewaretoken'] = get_csrf_token();
  return data;
}

function before_send_delete() {
  // https://stackoverflow.com/questions/13089613/ajax-csrf-and-delete
  return function(xhr) {
    xhr.setRequestHeader("X-CSRFToken", get_csrf_token());
  };
}

function get_csrf_token() {
  return $('input[name=csrfmiddlewaretoken]').val();
}

/* Ajax stuff */
function ok(response) {
  return response['OK'];
}

function show_problem(response, feedback_or_append_to) {
  var feedback;
  if (feedback_or_append_to.hasClass('feedback')) {
    feedback = feedback_or_append_to;
  } else {
    feedback = get_feedback_elt_append(feedback_or_append_to);
  }
  if (response['problem']) {
    feedback.text(response['problem']).show();
    return true;
  } else {
    feedback.hide();
    return false;
  }
}

function post(url, data, success) {
  $.post(url, add_csrf_token(data), success);
}

/* Error handling stuff */
window.onerror = function(msg, url, line, col, error) {
  url = url || window.location.href;
  $.post('/js_error', {
      msg: msg, url: url, line: line, col: col, stack: error && error.stack});
};

/* Query string stuff */
function query_string_obj_to_str(obj) {
  var parts = [];
  for (var key in obj) {
    if (obj[key]) {
      if (Array.isArray(obj[key])) {
        for (var i = 0; i < obj[key].length; i++) {
          parts.push(key + '=' + obj[key][i]);
        }
      } else {
        parts.push(key + '=' + obj[key]);
      }
    }
  }
  if (parts.length) {
    return '?' + parts.join('&');
  }
  return '';
}

function get_query_string_obj(search) {
  if (typeof(search) == 'undefined') {
    search = window.location.search;
  }
  var obj = {};
  if (search) {
    if (search.substring(0, 1) == "?") {
      search = search.substring(1);
    }
    search.split('&').forEach(function(part) {
        if (Boolean(part)) {
          var sub_parts = part.split('=');
          if (sub_parts.length == 2) {
            obj[sub_parts[0]] = sub_parts[1];
          }
        }
      });
  }
  return obj;
}

function refresh_with_qs(key, value) {
  // Go to the exact same URL we're on with one difference: the query string
  // key=value. Or, if value is null, with that query string variable not set.
  var search_obj = get_query_string_obj();
  if (typeof(value) == 'undefined' || value === null) {
    if (key in search_obj) {
      delete search_obj[key];
    }
  } else {
    search_obj[key] = value;
  }
  window.location = (
      window.location.pathname + query_string_obj_to_str(search_obj));
}

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

window.onerror = function(msg, url, line, col, error) {
  $.post('/js_error', {msg: msg, url: url, line: line, col: col});
};

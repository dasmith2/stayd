/* Sets up those buttons on /admin/work/oneoff/ so you can click to kick off a
 * one off. */
$(function() {
  var create_one_off_job_request = function() {
    var button = $(this);
    var wrapper = button.parent();
    var id = wrapper.attr('data-id');
    var readonly_url = wrapper.attr('data-readonly');
    wrapper.parents('tr').find('a').attr('href', readonly_url);
    var data_url = '/work/kick_off_one_off/' + id + '/';
    var success = function(data) {
      var message = '?';
      var load_again = false;
      if (data.creation_error) {
        message = data.creation_error;
      } else if (data.creation_confirmed) {
        message = 'OFFERED';
      } else if (data.creation_started) {
        message = 'Still creating... (wait, like, 15 minutes)';
        load_again = true;
      } else if (data.just_started) {
        message = 'Creating... (wait, like, 15 minutes)';
        load_again = true;
      }
      wrapper.html(message);
      if (load_again) {
        window.setTimeout(function() {
          $.getJSON(data_url, success);
        }, 1000);
      }
    };
    $.getJSON(data_url, success);
  };
  $('.create_wrapper button').click(create_one_off_job_request);

  var only_allow_one_type_of_checklist = function() {
    var line_items_wrapper = $('h2:contains(Line items)').parent();
    var line_item_text_boxes = line_items_wrapper.find('input[type=text]');
    var existing_wrapper = $('h2:contains(Existing checklist)').parent();
    var existing_text_box = existing_wrapper.find('input[type=text]');
    var hide_line_items_if_existing = function() {
      if (existing_text_box.val()) {
        line_items_wrapper.hide();
      } else {
        line_items_wrapper.show();
      }
    };
    var has_text = function() {
      return $(this).val() != '';
    };
    var hide_existing_if_line_items = function() {
      if (line_item_text_boxes.filter(has_text).length) {
        existing_wrapper.hide();
      } else {
        existing_wrapper.show();
      }
    };
    hide_line_items_if_existing();
    hide_existing_if_line_items();
    line_item_text_boxes.keyup(hide_existing_if_line_items);
    existing_text_box.keyup(hide_line_items_if_existing);
  };

  only_allow_one_type_of_checklist();
});

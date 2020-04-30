// This puts helpdoc links at the top of django admin pages.
$(function() {
  var config = {
    '/admin/work/worker/': {
      'url': 'https://stayd.helpdocs.io/article/wpu3vqzknx-add-a-new-service-provider',
      'title': 'Add a new service provider'},
    '/admin/work/properlyrental/': {
      'url': 'https://stayd.helpdocs.io/article/viw89vi54r-add-and-edit-properly-rentals',
      'title': 'Add and edit Properly Rentals'},
    '/admin/rentals/monthlyexpense/': {
      'url': 'https://stayd.helpdocs.io/article/66b5iw4h4u-add-lease-amount-to-keys-to-the-kingdom',
      'title': 'Add lease amount to Keys to the Kingdom'},
    '/admin/work/worktype/': {
      'url': 'https://stayd.helpdocs.io/article/g643346mf0-add-service-provider-type-for-properly-in-keys-to-the-kingdom',
      'title': 'Add service provider type for Properly in Keys to the Kingdom'},
    '/admin/work/cleaning/': [{
      'url': 'https://stayd.helpdocs.io/article/0qr0jnaw1h-check-the-status-of-properly-cleanings-in-keys-to-the-kingdom',
      'title': 'Check the status of Properly cleanings in Keys to the Kingdom'}, {
      'url': 'https://stayd.helpdocs.io/article/r9lg4om82b-permanently-cancel-a-properly-cleaning-in-keys-to-the-kingdom',
      'title': 'Permanently cancel a Properly cleaning in Keys to the Kingdom'}],
    '/admin/work/oneoff/': {
      'url': 'https://stayd.helpdocs.io/article/bp31v0ojv5-create-a-one-off-job-in-properly',
      'title': 'Create a one off job in Properly'},
    '/admin/work/repeatconfig/': {
      'url': 'https://stayd.helpdocs.io/article/96s91g7u82-creating-regularly-scheduled-properly-jobs',
      'title': 'Creating regularly scheduled Properly jobs'},
  };
  var path = window.location.pathname;
  if (path in config) {
    var instances = config[path];
    if (!Array.isArray(instances)) {
      instances = [instances];
    }
    for (var i = 0; i < instances.length; i++) {
      var instance = instances[i];
      var html = '<p>How to: <a href="' + instance.url + '">' + instance.title + '</a></p>';
      $(html).insertAfter($('#content h1'));
    }
  }
});

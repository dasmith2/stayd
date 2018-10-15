// lazyload config
var MODULE_CONFIG = {
    chat:           [
                      '/static/apply/libs/list.js/dist/list.js',
                      '/static/apply/libs/notie/dist/notie.min.js',
                      '/static/apply/scripts/plugins/notie.js',
                      '/static/apply/scripts/app/chat.js'
                    ],
    mail:           [
                      '/static/apply/libs/list.js/dist/list.js',
                      '/static/apply/libs/notie/dist/notie.min.js',
                      '/static/apply/scripts/plugins/notie.js',
                      '/static/apply/scripts/app/mail.js'
                    ],
    user:           [
                      '/static/apply/libs/list.js/dist/list.js',
                      '/static/apply/libs/notie/dist/notie.min.js',
                      '/static/apply/scripts/plugins/notie.js',
                      '/static/apply/scripts/app/user.js'
                    ],
    screenfull:     [
                      '/static/apply/libs/screenfull/dist/screenfull.js',
                      '/static/apply/scripts/plugins/screenfull.js'
                    ],
    jscroll:        [
                      '/static/apply/libs/jscroll/jquery.jscroll.min.js'
                    ],
    stick_in_parent:[
                      '/static/apply/libs/sticky-kit/jquery.sticky-kit.min.js'
                    ],
    scrollreveal:   [
                      '/static/apply/libs/scrollreveal/dist/scrollreveal.min.js',
                      '/static/apply/scripts/plugins/jquery.scrollreveal.js'
                    ],
    owlCarousel:    [
                      '/static/apply/libs/owl.carousel/dist/assets/owl.carousel.min.css',
                      '/static/apply/libs/owl.carousel/dist/assets/owl.theme.css',
                      '/static/apply/libs/owl.carousel/dist/owl.carousel.min.js'
                    ],
    html5sortable:  [
                      '/static/apply/libs/html5sortable/dist/html.sortable.min.js',
                      '/static/apply/scripts/plugins/jquery.html5sortable.js',
                      '/static/apply/scripts/plugins/sortable.js'
                    ],
    easyPieChart:   [
                      '/static/apply/libs/easy-pie-chart/dist/jquery.easypiechart.min.js' 
                    ],
    peity:          [
                      '/static/apply/libs/peity/jquery.peity.js',
                      '/static/apply/scripts/plugins/jquery.peity.tooltip.js',
                    ],
    chart:          [
                      '/static/apply/libs/moment/min/moment-with-locales.min.js',
                      '/static/apply/libs/chart.js/dist/Chart.min.js',
                      '/static/apply/scripts/plugins/jquery.chart.js',
                      '/static/apply/scripts/plugins/chartjs.js'
                    ],
    dataTable:      [
                      '/static/apply/libs/datatables/media/js/jquery.dataTables.min.js',
                      '/static/apply/libs/datatables.net-bs4/js/dataTables.bootstrap4.js',
                      '/static/apply/libs/datatables.net-bs4/css/dataTables.bootstrap4.css',
                      '/static/apply/scripts/plugins/datatable.js'
                    ],
    bootstrapTable: [
                      '/static/apply/libs/bootstrap-table/dist/bootstrap-table.min.css',
                      '/static/apply/libs/bootstrap-table/dist/bootstrap-table.min.js',
                      '/static/apply/libs/bootstrap-table/dist/extensions/export/bootstrap-table-export.min.js',
                      '/static/apply/libs/bootstrap-table/dist/extensions/mobile/bootstrap-table-mobile.min.js',
                      '/static/apply/scripts/plugins/tableExport.min.js',
                      '/static/apply/scripts/plugins/bootstrap-table.js'
                    ],
    bootstrapWizard:[
                      '/static/apply/libs/twitter-bootstrap-wizard/jquery.bootstrap.wizard.min.js'
                    ],
    dropzone:       [
                      '/static/apply/libs/dropzone/dist/min/dropzone.min.js',
                      '/static/apply/libs/dropzone/dist/min/dropzone.min.css'
                    ],
    datetimepicker: [
                      '/static/apply/libs/tempusdominus-bootstrap-4/build/css/tempusdominus-bootstrap-4.min.css',
                      '/static/apply/libs/moment/min/moment-with-locales.min.js',
                      '/static/apply/libs/tempusdominus-bootstrap-4/build/js/tempusdominus-bootstrap-4.min.js',
                      '/static/apply/scripts/plugins/datetimepicker.js'
                    ],
    datepicker:     [
                      '/static/apply/libs/bootstrap-datepicker/dist/js/bootstrap-datepicker.min.js',
                      '/static/apply/libs/bootstrap-datepicker/dist/css/bootstrap-datepicker.min.css',
                    ],
    fullCalendar:   [
                      '/static/apply/libs/moment/min/moment-with-locales.min.js',
                      '/static/apply/libs/fullcalendar/dist/fullcalendar.min.js',
                      '/static/apply/libs/fullcalendar/dist/fullcalendar.min.css',
                      '/static/apply/scripts/plugins/fullcalendar.js'
                    ],
    parsley:        [
                      '/static/apply/libs/parsleyjs/dist/parsley.min.js'
                    ],
    select2:        [
                      '/static/apply/libs/select2/dist/css/select2.min.css',
                      '/static/apply/libs/select2/dist/js/select2.min.js',
                      '/static/apply/scripts/plugins/select2.js'
                    ],
    summernote:     [
                      '/static/apply/libs/summernote/dist/summernote.css',
                      '/static/apply/libs/summernote/dist/summernote-bs4.css',
                      '/static/apply/libs/summernote/dist/summernote.min.js',
                      '/static/apply/libs/summernote/dist/summernote-bs4.min.js'
                    ],
    vectorMap:      [
                      '/static/apply/libs/jqvmap/dist/jqvmap.min.css',
                      '/static/apply/libs/jqvmap/dist/jquery.vmap.js',
                      '/static/apply/libs/jqvmap/dist/maps/jquery.vmap.world.js',
                      '/static/apply/libs/jqvmap/dist/maps/jquery.vmap.usa.js',
                      '/static/apply/libs/jqvmap/dist/maps/jquery.vmap.france.js',
                      '/static/apply/scripts/plugins/jqvmap.js'
                    ],
    waves:          [
                      '/static/apply/libs/node-waves/dist/waves.min.css',
                      '/static/apply/libs/node-waves/dist/waves.min.js',
                      '/static/apply/scripts/plugins/waves.js'
                    ]
  };

var MODULE_OPTION_CONFIG = {
  parsley: {
    errorClass: 'is-invalid',
    successClass: 'is-valid',
    errorsWrapper: "<ul class='list-unstyled text-sm mt-1 text-muted'></ul>"
  }
}

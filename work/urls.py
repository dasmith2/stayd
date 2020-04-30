from django.urls import path
from django.views.generic.base import RedirectView

from work.views.work_hihoward_com import (
    my_tickets, my_tickets_data, my_tickets_events, maintenance_new_ticket,
    i_got_paid_wrong)
from work.views.cleaning_checklist import (
    new_checklist, edit_checklist, change_checklist_title, list_slides, slide,
    step, create_example_photo)
from work.views.clean_hihoward_com import (
    clean_co_cleanings, clean_co_cleaning, clean_co_all_rentals,
    cleaners, cleaner, set_cleaning_cleaner, clean,
    report_cleaning_ticket, slide_done, close_ticket,
    complete_cleaning, doing_slides, review_cleaning)
from work.views.ui import (
    properly_webhook, raw_event_detail, cleaning_history_detail,
    inspection_history_detail, old_cleaning_schedule, one_off_history_detail,
    kick_off_one_off, child_class_details, pay_service_providers,
    pay_service_provider_totals, pay_service_providers_csv,
    redirect_to_pay_service_providers, cleaning_scores, cleaning_score,
    repeat_work_history_detail, maintenance_history_detail, invoice, tickets,
    set_ticket_sla, ticket)
from work.views.web_tests import (
    get_2_maintenance_datas_for_web_test, is_maintenance_complete,
    get_a_bunch_of_cleanings_for_web_tests, clear_out_cleaning_checklists)


urlpatterns = [
    # Clean, as in, do a cleaning
    path('clean/<cleaning_pk>/', clean, name='clean'),
    path(
        'review_cleaning/<pk>/', review_cleaning, name='review_cleaning'),
    path('doing_slides/<cleaning_pk>/', doing_slides, name='doing_slides'),
    path(
        'report_cleaning_ticket/<cleaning_pk>/', report_cleaning_ticket,
        name='report_cleaning_ticket'),
    path(
        'slide_done/<cleaning_pk>/<slide_pk>/', slide_done,
        name='slide_done'),
    path('close_ticket/<ticket_pk>/', close_ticket, name='close_ticket'),
    path(
        'complete_cleaning/<cleaning_pk>/', complete_cleaning,
        name='complete_cleaning'),

    # Cleaning checklist
    path(
        'admin/work/cleaningchecklist/add/', new_checklist,
        name='new_checklist'),
    path(
        'admin/work/cleaningchecklist/<checklist_pk>/change/', edit_checklist,
        name='edit_checklist'),
    path(
        'change_checklist_title/', change_checklist_title,
        name='change_checklist_title'),
    path(
        'list_slides/<checklist_pk>/', list_slides, name='list_slides'),
    path('slide/', slide, name='slide'),
    path('slide/<slide_pk>/', slide, name='slide'),
    path('step/', step, name='step'),
    path('step/<step_pk>/', step, name='step'),
    path(
        'create_example_photo/', create_example_photo,
        name='create_example_photo'),
    # Web tests for cleaning checklist
    path(
        'clear_out_cleaning_checklists/', clear_out_cleaning_checklists,
        name='clear_out_cleaning_checklists'),

    # Cleaning companies
    path(  # Legacy. Don't use.
        'work_co_landing/', RedirectView.as_view(url='/clean_co_cleanings/')),
    path(  # Legacy. Don't use.
        'work_co_cleanings/',
        RedirectView.as_view(url='/clean_co_cleanings/')),
    path(
        'clean_co_cleanings/<from_date_str>/<to_date_str>/',
        clean_co_cleanings, name='clean_co_cleanings'),
    path('clean_co_cleanings/', clean_co_cleanings, name='clean_co_cleanings'),
    path(
        'clean_co_cleaning/<pk>/', clean_co_cleaning,
        name='clean_co_cleaning'),
    path('clean_co_cleaning/', clean_co_cleaning, name='clean_co_cleaning'),
    path(
        'clean_co_all_rentals/', clean_co_all_rentals,
        name='clean_co_all_rentals'),
    path(  # For web tests.
        'get_a_bunch_of_cleanings_for_web_tests/',
        get_a_bunch_of_cleanings_for_web_tests,
        name='get_a_bunch_of_cleanings_for_web_tests'),
    path(
        'get_a_bunch_of_cleanings_for_web_tests/<cleaning_checklist_pk>/',
        get_a_bunch_of_cleanings_for_web_tests,
        name='get_a_bunch_of_cleanings_for_web_tests'),
    path('cleaners/', cleaners, name='cleaners'),
    path('cleaner/<pk>/', cleaner, name='cleaner'),
    path(
        'set_cleaning_cleaner/<int:cleaning_pk>/<int:cleaner_pk>/',
        set_cleaning_cleaner, name='set_cleaning_cleaner'),

    # Maintenance pages web tests
    path(
        'get_2_maintenance_datas_for_web_test/',
        get_2_maintenance_datas_for_web_test,
        name='get_2_maintenance_datas_for_web_test'),
    path(
        'is_maintenance_complete/<pk>/', is_maintenance_complete,
        name='is_maintenance_complete'),

    # Maintenance pages
    path('maintenance/', my_tickets, name='my_tickets'),
    path(
        'maintenance/my_tickets_data/', my_tickets_data,
        name='my_tickets_data'),
    path(
        'maintenance/my_tickets_events/', my_tickets_events,
        name='my_tickets_events'),
    path(
        'maintenance/new_ticket/', maintenance_new_ticket,
        name='maintenance_new_ticket'),
    path(
        'maintenance/i_got_paid_wrong/', i_got_paid_wrong,
        name='i_got_paid_wrong'),

    # Admin
    path('tickets/', tickets, name='tickets'),
    path('tickets/<from_date_str>/<to_date_str>/', tickets, name='tickets'),
    path('tickets/set_sla/', set_ticket_sla, name='set_ticket_sla'),
    path('ticket/', ticket, name='new_ticket'),
    path('ticket/<int:pk>/', ticket, name='ticket'),
    path('invoice/<int:pay_pk>/', invoice, name='invoice'),

    path(
        'cleaning_schedule', old_cleaning_schedule, name='cleaning_schedule'),
    path(
        'cleaning_schedule/', old_cleaning_schedule, name='cleaning_schedule'),
    path('properly/webhook', properly_webhook, name='properly_webhook'),
    path(
        'admin/work/rawevent/<int:pk>/change/',
        raw_event_detail, name='raw_event_detail'),
    path(
        'admin/work/cleaning/<pk>/change/', cleaning_history_detail,
        name='cleaning_history_detail'),
    path(
        'admin/work/inspection/<pk>/change/', inspection_history_detail,
        name='inspection_history_detail'),
    path(
        'admin/work/oneoff/<pk>/readonly/', one_off_history_detail,
        name='one_off_history_detail'),
    path(
        'admin/work/repeatwork/<pk>/change/', repeat_work_history_detail,
        name='repeat_work_history_detail'),
    path(
        'admin/work/maintenance/<pk>/change/', maintenance_history_detail,
        name='maintenance_history_detail'),
    path(
        'work/kick_off_one_off/<pk>/', kick_off_one_off,
        name='kick_off_one_off'),
    path(
        'work/child_class_details/<pk>/', child_class_details,
        name='child_class_details'),
    path(
        'work/pay_service_provider_totals/',
        pay_service_provider_totals, name='pay_service_provider_totals'),
    path(
        'work/pay_service_provider_totals/<from_date_str>/<to_date_str>/',
        pay_service_provider_totals, name='pay_service_provider_totals'),
    path(
        'work/pay_service_providers/',
        pay_service_providers, name='pay_service_providers'),
    path(
        'work/pay_service_providers/<from_date_str>/<to_date_str>/',
        pay_service_providers, name='pay_service_providers'),
    path(
        'work/pay_service_providers_csv/<from_date_str>/<to_date_str>/',
        pay_service_providers_csv, name='pay_service_providers_csv'),
    path('work/cleaning_scores/', cleaning_scores, name='cleaning_scores'),
    path(
        'work/cleaning_scores/<worker_pk>/', cleaning_score,
        name='cleaning_score'),
    # This is a bit hacky. I wired up the types of payment in the admin so I
    # had a quick and dirty save flow. So you hit save and it tries to go back
    # to the list but then I redirect it to the pay_service_providers view.
    path('admin/work/workpayment/', redirect_to_pay_service_providers),
    path('admin/work/manualpayment/', redirect_to_pay_service_providers)]

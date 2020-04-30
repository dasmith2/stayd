from django.urls import path

from netsuite.views import (
    netsuite_csv_worker_payments, netsuite_csv_bill,
    netsuite_classes)


urlpatterns = [
    # I moved these over from work and resisted the urge to change the url.
    path(
        'netsuite_csv/revenue/', netsuite_csv_bill,
        name='netsuite_csv_bill'),
    path(
        'netsuite_csv/revenue/<from_date_str>/<to_date_str>/',
        netsuite_csv_bill, name='netsuite_csv_bill'),

    path(
        'netsuite_csv/worker_payments/',
        netsuite_csv_worker_payments,
        name='netsuite_csv_worker_payments'),
    path(
        'netsuite_csv/worker_payments/<from_date_str>/<to_date_str>/',
        netsuite_csv_worker_payments,
        name='netsuite_csv_worker_payments'),
    path(
        'netsuite_classes/', netsuite_classes, name='netsuite_classes'),

    path(  # Legacy
        'work/netsuite_csv/', netsuite_csv_worker_payments),
    path(  # Legacy
        'work/netsuite_csv/<from_date_str>/<to_date_str>/',
        netsuite_csv_worker_payments)]

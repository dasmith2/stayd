from django.urls import path

from reports.cash_basis.views import (
    cash_basis, cash_basis_csv, coconut_details, coconut_details_csv,
    revenue_details, revenue_details_csv, refund_details, refund_details_csv)


coconut_details_path = (
    'reports/coconut_details/<from_date_str>/<to_date_str>/'
    '<coconut_id>/<building_id>/')
coconut_details_csv_path = (
    'reports/coconut_details_csv/<from_date_str>/<to_date_str>/'
    '<coconut_id>/<building_id>/')
revenue_details_path = (
    'reports/revenue_details/<from_date_str>/<to_date_str>/<building_id>/')
revenue_details_csv_path = (
    'reports/revenue_details_csv/<from_date_str>/<to_date_str>/<building_id>/')
refund_details_path = (
    'reports/refund_details/<from_date_str>/<to_date_str>/<building_id>/')
refund_details_csv_path = (
    'reports/refund_details_csv/<from_date_str>/<to_date_str>/<building_id>/')

urlpatterns = [
    path('reports/cash_basis/', cash_basis, name='cash_basis'),
    path(
        'reports/cash_basis/<from_date_str>/<to_date_str>/',
        cash_basis, name='cash_basis'),
    path(
        'reports/cash_basis_csv/<from_date_str>/<to_date_str>/',
        cash_basis_csv, name='cash_basis_csv'),
    path(coconut_details_path, coconut_details, name='coconut_details'),
    path(
        coconut_details_csv_path, coconut_details_csv,
        name='coconut_details_csv'),
    path(revenue_details_path, revenue_details, name='revenue_details'),
    path(
        revenue_details_csv_path, revenue_details_csv,
        name='revenue_details_csv'),
    path(refund_details_path, refund_details, name='refund_details'),
    path(
        refund_details_csv_path, refund_details_csv,
        name='refund_details_csv')]

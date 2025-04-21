from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('widgets/personnel-count/', views.personnel_count, name='personnel_count'),
    path('widgets/weapons-count/', views.weapons_count, name='weapons_count'),
    path('widgets/face-records-count/', views.face_records_count, name='face_records_count'),
    path('widgets/transaction-logs/', views.transaction_logs, name='transaction_logs'),
    path('events/transactions/', views.transaction_sse, name='transaction_sse'),

    path('export/csv/', views.export_transactions_csv, name='export_csv'),
    path('export/excel/', views.export_transactions_excel, name='export_excel'),
    path('export/pdf/', views.export_transactions_pdf, name='export_pdf'),
    path('reports/', views.reports, name='reports'),
]
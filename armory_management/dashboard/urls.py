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
]
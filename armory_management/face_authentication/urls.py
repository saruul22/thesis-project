from django.urls import path
from . import views

app_name = 'face_authentication'

urlpatterns = [
    path('register/', views.register_face, name='register_face'),
    path('verify/', views.verify_face, name='verify_face'),
    path('list_faces/', views.list_faces, name='list_faces'),
    path('get_face_data/<str:personnel_id>/', views.get_face_data, name='get_face_data'),
]
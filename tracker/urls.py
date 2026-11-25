from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_router, name='dashboard_router'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/admin/export-csv/', views.export_appointments_csv, name='export_appointments_csv'),
    path('dashboard/faculty/', views.faculty_dashboard, name='faculty_dashboard'),
    path('dashboard/student/', views.student_dashboard, name='student_dashboard'),

    path('faculty/', views.faculty_directory, name='faculty_directory'),
    path('faculty/<int:faculty_id>/', views.faculty_detail, name='faculty_detail'),
    path('notifications/read/', views.mark_notifications_read, name='mark_notifications_read'),
]

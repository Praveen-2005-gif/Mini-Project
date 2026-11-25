from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm
from django import forms
from .models import (
    User, Department, Subject, Faculty, Student, Timetable,
    TimetableSlot, FacultyCommitment, Appointment, AvailabilityRecord,
    Notification, PredictionHistory
)

class FacultyUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'role', 'phone')


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = FacultyUserCreationForm
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username', 'first_name', 'last_name', 'email', 'role', 'phone',
                'password1', 'password2',
            ),
        }),
    )
    fieldsets = UserAdmin.fieldsets + (
        ('Faculty tracker', {'fields': ('role', 'phone')}),
    )

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if request.GET.get('_popup') == '1':
            initial['role'] = 'FACULTY'
        return initial


admin.site.register(Department)
admin.site.register(Subject)
class FacultyAdminForm(forms.ModelForm):
    class Meta:
        model = Faculty
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        available_users = User.objects.filter(
            role='FACULTY', faculty_profile__isnull=True
        )
        if self.instance and self.instance.pk:
            available_users = available_users | User.objects.filter(pk=self.instance.user_id)
        self.fields['user'].queryset = available_users.distinct()
        self.fields['user'].help_text = (
            'Only unassigned accounts with the Faculty role are listed. '
            'Create or update a faculty account in Users first.'
        )


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    form = FacultyAdminForm
    list_display = ('employee_id', 'user', 'department', 'designation')
    list_filter = ('department', 'designation')
    search_fields = ('employee_id', 'user__username', 'user__first_name', 'user__last_name')


admin.site.register(Student)
admin.site.register(Timetable)
admin.site.register(TimetableSlot)
admin.site.register(FacultyCommitment)
admin.site.register(Appointment)
admin.site.register(AvailabilityRecord)
admin.site.register(Notification)
admin.site.register(PredictionHistory)

from django import forms
from django.db import transaction
from django.utils import timezone
from .models import (
    User, Student, Faculty, Department, Subject,
    Appointment, FacultyCommitment, TEACHING_PERIOD_CHOICES, DAY_CHOICES
)


class StudentRegistrationForm(forms.ModelForm):
    first_name = forms.CharField(max_length=60, required=True)
    last_name = forms.CharField(max_length=60, required=True)
    email = forms.EmailField(required=True)
    password = forms.CharField(widget=forms.PasswordInput, required=True)
    roll_number = forms.CharField(max_length=30, required=True)
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=True)
    semester = forms.IntegerField(min_value=1, max_value=8, initial=3)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password']

    def clean_roll_number(self):
        roll_number = self.cleaned_data['roll_number'].strip()
        if Student.objects.filter(roll_number__iexact=roll_number).exists():
            raise forms.ValidationError('A student with this roll number is already registered.')
        return roll_number

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.role = 'STUDENT'
        if commit:
            user.save()
            Student.objects.create(
                user=user,
                roll_number=self.cleaned_data['roll_number'],
                department=self.cleaned_data['department'],
                semester=self.cleaned_data['semester'],
            )
        return user


class AppointmentRequestForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ['date', 'period_code', 'purpose', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'min': timezone.localdate().isoformat()}),
            'notes': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Briefly describe your topic or project query...'}),
        }


class CommitmentForm(forms.ModelForm):
    class Meta:
        model = FacultyCommitment
        fields = ['date', 'period_code', 'commitment_type', 'title']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'min': timezone.localdate().isoformat()}),
        }


class CSVTimetableUploadForm(forms.Form):
    csv_file = forms.FileField(help_text="Columns: employee_id,day_of_week,period_code,slot_type,subject_code,room_number")

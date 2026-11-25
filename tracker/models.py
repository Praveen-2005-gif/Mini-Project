from datetime import time
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError

# Exact College Working Timetable Constants
COLLEGE_SCHEDULE = [
    {'code': 'P1', 'name': 'Period 1', 'start': time(8, 45), 'end': time(9, 40), 'is_break': False},
    {'code': 'P2', 'name': 'Period 2', 'start': time(9, 40), 'end': time(10, 35), 'is_break': False},
    {'code': 'TB', 'name': 'Tea Break', 'start': time(10, 35), 'end': time(10, 50), 'is_break': True},
    {'code': 'P3', 'name': 'Period 3', 'start': time(10, 50), 'end': time(11, 45), 'is_break': False},
    {'code': 'P4', 'name': 'Period 4', 'start': time(11, 45), 'end': time(12, 40), 'is_break': False},
    {'code': 'LB', 'name': 'Lunch Break', 'start': time(12, 40), 'end': time(13, 40), 'is_break': True},
    {'code': 'P5', 'name': 'Period 5', 'start': time(13, 40), 'end': time(14, 35), 'is_break': False},
    {'code': 'P6', 'name': 'Period 6', 'start': time(14, 35), 'end': time(15, 30), 'is_break': False},
    {'code': 'P7', 'name': 'Period 7', 'start': time(15, 30), 'end': time(16, 25), 'is_break': False},
    {'code': 'P8', 'name': 'Period 8', 'start': time(16, 25), 'end': time(17, 20), 'is_break': False},
]

TEACHING_PERIOD_CHOICES = [
    ('P1', 'Period 1 (08:45 AM - 09:40 AM)'),
    ('P2', 'Period 2 (09:40 AM - 10:35 AM)'),
    ('P3', 'Period 3 (10:50 AM - 11:45 AM)'),
    ('P4', 'Period 4 (11:45 AM - 12:40 PM)'),
    ('P5', 'Period 5 (01:40 PM - 02:35 PM)'),
    ('P6', 'Period 6 (02:35 PM - 03:30 PM)'),
    ('P7', 'Period 7 (03:30 PM - 04:25 PM)'),
    ('P8', 'Period 8 (04:25 PM - 05:20 PM)'),
]

DAY_CHOICES = [
    ('MON', 'Monday'),
    ('TUE', 'Tuesday'),
    ('WED', 'Wednesday'),
    ('THU', 'Thursday'),
    ('FRI', 'Friday'),
    ('SAT', 'Saturday'),
]


class User(AbstractUser):
    ROLE_CHOICES = [
        ('ADMIN', 'Admin'),
        ('FACULTY', 'Faculty'),
        ('STUDENT', 'Student'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='STUDENT')
    phone = models.CharField(max_length=20, blank=True)

    @property
    def initials(self):
        parts = (self.get_full_name() or self.username).split()
        return "".join([p[0].upper() for p in parts[:2]])


class Department(models.Model):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=15, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.code} - {self.name}"


class Subject(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='subjects')
    semester = models.PositiveSmallIntegerField(default=1)

    def __str__(self):
        return f"{self.code}: {self.name}"


class Faculty(models.Model):
    STATUS_OVERRIDE_CHOICES = [
        ('AUTO', 'Auto (Follow Schedule)'),
        ('AVAILABLE', 'Available for Consultation'),
        ('BUSY', 'Busy / Do Not Disturb'),
        ('IN_MEETING', 'In Meeting'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='faculty_profile')
    employee_id = models.CharField(max_length=30, unique=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='faculties')
    designation = models.CharField(max_length=100, default='Assistant Professor')
    cabin_location = models.CharField(max_length=100, default='Block A, Room 204')
    subjects = models.ManyToManyField(Subject, blank=True, related_name='faculties')
    manual_status = models.CharField(max_length=15, choices=STATUS_OVERRIDE_CHOICES, default='AUTO')
    preferred_periods = models.CharField(
        max_length=50, default='P4,P7',
        help_text='Comma-separated preferred consultation periods e.g. P4,P7'
    )

    def get_preferred_list(self):
        return [p.strip() for p in self.preferred_periods.split(',') if p.strip()]

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.department.code})"


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    roll_number = models.CharField(max_length=30, unique=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='students')
    semester = models.PositiveSmallIntegerField(default=3)

    def __str__(self):
        return f"{self.roll_number} - {self.user.get_full_name()}"


class Timetable(models.Model):
    faculty = models.OneToOneField(Faculty, on_delete=models.CASCADE, related_name='timetable')
    academic_year = models.CharField(max_length=20, default='2026-2027')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Timetable: {self.faculty.user.get_full_name()}"


class TimetableSlot(models.Model):
    SLOT_TYPE_CHOICES = [
        ('CLASS', 'Regular Class'),
        ('LAB', 'Laboratory Session'),
        ('CONSULTATION', 'Confirmed Consultation Hour'),
    ]
    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE, related_name='slots')
    day_of_week = models.CharField(max_length=3, choices=DAY_CHOICES)
    period_code = models.CharField(max_length=3, choices=TEACHING_PERIOD_CHOICES)
    slot_type = models.CharField(max_length=15, choices=SLOT_TYPE_CHOICES, default='CLASS')
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    room_number = models.CharField(max_length=50, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['timetable', 'day_of_week', 'period_code'],
                name='unique_faculty_day_period'
            )
        ]

    def __str__(self):
        return f"{self.timetable.faculty.user.username} | {self.day_of_week} {self.period_code} ({self.slot_type})"


class FacultyCommitment(models.Model):
    COMMITMENT_TYPES = [
        ('MEETING', 'Department / Committee Meeting'),
        ('PERSONAL', 'Personal Commitment / Leave'),
        ('RESEARCH', 'Research / Evaluation Duty'),
    ]
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='commitments')
    date = models.DateField()
    period_code = models.CharField(max_length=3, choices=TEACHING_PERIOD_CHOICES)
    commitment_type = models.CharField(max_length=15, choices=COMMITMENT_TYPES, default='MEETING')
    title = models.CharField(max_length=150)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['faculty', 'date', 'period_code'],
                name='unique_faculty_commitment_slot'
            )
        ]

    def __str__(self):
        return f"{self.faculty} - {self.date} {self.period_code}: {self.title}"


class Appointment(models.Model):
    PURPOSE_CHOICES = [
        ('PROJECT', 'Project Guidance'),
        ('DOUBT', 'Academic / Subject Doubt'),
        ('MENTORING', 'Career & Mentoring'),
        ('ADMIN_WORK', 'Document / Lab Approval'),
    ]
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
        ('COMPLETED', 'Completed'),
    ]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='appointments')
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='appointments')
    date = models.DateField()
    period_code = models.CharField(max_length=3, choices=TEACHING_PERIOD_CHOICES)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='DOUBT')
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='PENDING')
    faculty_remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if not self.faculty_id:
            return
        # Prevent double booking if an accepted appointment already exists
        conflict = Appointment.objects.filter(
            faculty=self.faculty,
            date=self.date,
            period_code=self.period_code,
            status='ACCEPTED'
        ).exclude(pk=self.pk).exists()
        if conflict:
            raise ValidationError("Faculty already has an accepted appointment in this period.")
    def __str__(self):
        return f"{self.student.roll_number} -> {self.faculty.user.username} ({self.date} {self.period_code})"


class AvailabilityRecord(models.Model):
    """Historical log used to train the Random Forest model."""
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='availability_records')
    date = models.DateField()
    day_of_week = models.CharField(max_length=3, choices=DAY_CHOICES)
    period_code = models.CharField(max_length=3, choices=TEACHING_PERIOD_CHOICES)
    daily_teaching_load = models.PositiveSmallIntegerField(default=0)
    is_preferred_period = models.BooleanField(default=False)
    was_available_and_accepted = models.BooleanField(default=True)
    recorded_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class PredictionHistory(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE)
    target_date = models.DateField()
    recommended_period = models.CharField(max_length=3)
    probability_score = models.FloatField()
    model_mode = models.CharField(max_length=30)  # 'PROVISIONAL_RULE' or 'RANDOM_FOREST'
    created_at = models.DateTimeField(auto_now_add=True)

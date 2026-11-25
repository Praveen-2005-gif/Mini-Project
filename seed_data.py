import os
import django
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tracker.models import (
    User, Department, Subject, Faculty, Student,
    Timetable, TimetableSlot, Appointment
)

def run_seed():
    # Departments
    cs, _ = Department.objects.get_or_create(code='CSE', defaults={'name': 'Computer Science & Engineering'})
    ece, _ = Department.objects.get_or_create(code='ECE', defaults={'name': 'Electronics & Communication'})

    # Subjects
    s1, _ = Subject.objects.get_or_create(code='CS301', defaults={'name': 'Machine Learning', 'department': cs, 'semester': 5})
    s2, _ = Subject.objects.get_or_create(code='CS302', defaults={'name': 'Database Management Systems', 'department': cs, 'semester': 5})
    s3, _ = Subject.objects.get_or_create(code='EC201', defaults={'name': 'Digital Signal Processing', 'department': ece, 'semester': 4})

    # Admin User
    if not User.objects.filter(username='admin').exists():
        admin = User.objects.create_superuser('admin', 'admin@college.edu', 'pass1234', first_name='System', last_name='Admin', role='ADMIN')

    # Faculty 1
    u_fac1, created = User.objects.get_or_create(username='dr_sharma', defaults={'first_name': 'Arvind', 'last_name': 'Sharma', 'email': 'sharma@college.edu', 'role': 'FACULTY'})
    if created:
        u_fac1.set_password('pass1234')
        u_fac1.save()
    fac1, _ = Faculty.objects.get_or_create(
        user=u_fac1,
        defaults={'employee_id': 'FAC101', 'department': cs, 'designation': 'Professor', 'cabin_location': 'CS Block 301', 'preferred_periods': 'P4,P7'}
    )
    fac1.subjects.set([s1, s2])

    # Faculty 2
    u_fac2, created = User.objects.get_or_create(username='prof_nair', defaults={'first_name': 'Meera', 'last_name': 'Nair', 'email': 'nair@college.edu', 'role': 'FACULTY'})
    if created:
        u_fac2.set_password('pass1234')
        u_fac2.save()
    fac2, _ = Faculty.objects.get_or_create(
        user=u_fac2,
        defaults={'employee_id': 'FAC102', 'department': ece, 'designation': 'Associate Professor', 'cabin_location': 'EC Block 105', 'preferred_periods': 'P2,P6'}
    )
    fac2.subjects.set([s3])

    # Timetables
    tt1, _ = Timetable.objects.get_or_create(faculty=fac1)
    sample_slots = [
        ('MON', 'P1', 'CLASS', s1, 'LH-101'),
        ('MON', 'P2', 'CLASS', s2, 'LH-101'),
        ('MON', 'P5', 'LAB', s1, 'AI-Lab'),
        ('TUE', 'P3', 'CLASS', s1, 'LH-102'),
        ('WED', 'P1', 'CLASS', s2, 'LH-101'),
        ('THU', 'P2', 'CLASS', s1, 'LH-104'),
        ('FRI', 'P6', 'CLASS', s2, 'LH-101'),
        ('SAT', 'P1', 'CLASS', s1, 'LH-101'),
    ]
    for day, p, stype, subj, room in sample_slots:
        TimetableSlot.objects.get_or_create(
            timetable=tt1, day_of_week=day, period_code=p,
            defaults={'slot_type': stype, 'subject': subj, 'room_number': room}
        )

    # Student 1
    u_stu, created = User.objects.get_or_create(username='student1', defaults={'first_name': 'Rohan', 'last_name': 'Verma', 'email': 'rohan@college.edu', 'role': 'STUDENT'})
    if created:
        u_stu.set_password('pass1234')
        u_stu.save()
    stu1, _ = Student.objects.get_or_create(user=u_stu, defaults={'roll_number': '23CS045', 'department': cs, 'semester': 5})

    # Sample Pending Appointment
    Appointment.objects.get_or_create(
        student=stu1, faculty=fac1, date=date.today() + timedelta(days=1), period_code='P4',
        defaults={'purpose': 'PROJECT', 'notes': 'Final year ML project synopsis review', 'status': 'PENDING'}
    )
    print("Database seeded successfully!")

if __name__ == '__main__':
    run_seed()


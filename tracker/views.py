import csv
import io
import json
from datetime import datetime, date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db.models import Q, Count

from .models import (
    User, Faculty, Student, Department, Subject, Timetable, TimetableSlot,
    FacultyCommitment, Appointment, AvailabilityRecord, Notification,
    COLLEGE_SCHEDULE, DAY_CHOICES, TEACHING_PERIOD_CHOICES
)
from .forms import (
    StudentRegistrationForm, AppointmentRequestForm,
    CommitmentForm, CSVTimetableUploadForm
)
from .availability_engine import get_faculty_live_status, evaluate_slot_status, WEEKDAY_MAP
from .ml_engine import predict_best_slots, train_availability_model


def notification_context(request):
    if request.user.is_authenticated:
        unread = Notification.objects.filter(recipient=request.user, is_read=False).order_by('-created_at')[:5]
        return {'unread_notifications': unread, 'unread_count': unread.count()}
    return {'unread_notifications': [], 'unread_count': 0}


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_router')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard_router')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'auth/login.html')


def register_view(request):
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Student account created successfully!')
            return redirect('student_dashboard')
    else:
        form = StudentRegistrationForm()
    return render(request, 'auth/register.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard_router(request):
    if request.user.role == 'ADMIN' or request.user.is_superuser:
        return redirect('admin_dashboard')
    elif request.user.role == 'FACULTY':
        return redirect('faculty_dashboard')
    return redirect('student_dashboard')


# ==================== ADMIN DASHBOARD & ANALYTICS ====================
@login_required
def admin_dashboard(request):
    if request.user.role != 'ADMIN' and not request.user.is_superuser:
        return redirect('dashboard_router')

    faculties = Faculty.objects.select_related('user', 'department').all()
    students = Student.objects.select_related('user', 'department').all()
    departments = Department.objects.annotate(
        faculty_count=Count('faculties', distinct=True),
        student_count=Count('students', distinct=True)
    )

    status_counts = {'AVAILABLE': 0, 'POTENTIALLY AVAILABLE': 0, 'BUSY': 0, 'BREAK': 0}
    for f in faculties:
        st = get_faculty_live_status(f)['current']['status']
        if st == 'AVAILABLE':
            status_counts['AVAILABLE'] += 1
        elif st == 'POTENTIALLY AVAILABLE':
            status_counts['POTENTIALLY AVAILABLE'] += 1
        elif st == 'BREAK':
            status_counts['BREAK'] += 1
        else:
            status_counts['BUSY'] += 1

    # Handle CSV Timetable Upload
    csv_form = CSVTimetableUploadForm()
    if request.method == 'POST' and 'upload_csv' in request.POST:
        csv_form = CSVTimetableUploadForm(request.POST, request.FILES)
        if csv_form.is_valid():
            decoded = request.FILES['csv_file'].read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(decoded))
            created_count = 0
            for row in reader:
                fac = Faculty.objects.filter(employee_id=row['employee_id'].strip()).first()
                if fac:
                    tt, _ = Timetable.objects.get_or_create(faculty=fac)
                    subj = Subject.objects.filter(code=row.get('subject_code', '').strip()).first()
                    TimetableSlot.objects.update_or_create(
                        timetable=tt,
                        day_of_week=row['day_of_week'].strip().upper(),
                        period_code=row['period_code'].strip().upper(),
                        defaults={
                            'slot_type': row.get('slot_type', 'CLASS').strip().upper(),
                            'subject': subj,
                            'room_number': row.get('room_number', '').strip(),
                        }
                    )
                    created_count += 1
            messages.success(request, f"Successfully imported/updated {created_count} timetable slots.")
            return redirect('admin_dashboard')

    # Handle Manual ML Retraining
    ml_status = None
    if request.method == 'POST' and 'retrain_ml' in request.POST:
        ml_status = train_availability_model()
        messages.info(request, ml_status['message'])

    dept_labels = [d.code for d in departments]
    dept_fac_counts = [d.faculty_count for d in departments]
    pending_appts = Appointment.objects.filter(status='PENDING').count()

    context = {
        'total_faculty': faculties.count(),
        'total_students': students.count(),
        'available_now': status_counts['AVAILABLE'] + status_counts['POTENTIALLY AVAILABLE'],
        'busy_now': status_counts['BUSY'],
        'pending_appointments': pending_appts,
        'departments': departments,
        'faculties': faculties,
        'csv_form': csv_form,
        'status_chart_json': json.dumps(status_counts),
        'dept_labels_json': json.dumps(dept_labels),
        'dept_counts_json': json.dumps(dept_fac_counts),
        'ml_record_count': AvailabilityRecord.objects.count(),
    }
    return render(request, 'dashboards/admin_dashboard.html', context)


@login_required
def export_appointments_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="appointments_report.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Date', 'Period', 'Faculty', 'Department', 'Student Roll', 'Purpose', 'Status'])

    appts = Appointment.objects.select_related('faculty__user', 'faculty__department', 'student').all()
    for a in appts:
        writer.writerow([
            a.id, a.date, a.period_code, a.faculty.user.get_full_name(),
            a.faculty.department.code, a.student.roll_number, a.get_purpose_display(), a.status
        ])
    return response


# ==================== FACULTY DASHBOARD ====================
@login_required
def faculty_dashboard(request):
    if request.user.role != 'FACULTY':
        return redirect('dashboard_router')

    faculty = get_object_or_404(Faculty, user=request.user)
    today = timezone.localdate()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_status':
            faculty.manual_status = request.POST.get('manual_status', 'AUTO')
            faculty.preferred_periods = request.POST.get('preferred_periods', faculty.preferred_periods)
            faculty.save()
            messages.success(request, 'Live availability status & consultation hours updated.')
        elif action == 'add_commitment':
            c_form = CommitmentForm(request.POST)
            if c_form.is_valid():
                comm = c_form.save(commit=False)
                comm.faculty = faculty
                comm.save()
                messages.success(request, 'Personal commitment / meeting added to schedule.')
        elif action == 'respond_appointment':
            appt_id = request.POST.get('appointment_id')
            decision = request.POST.get('decision')  # ACCEPTED or REJECTED
            remarks = request.POST.get('remarks', '')
            appt = get_object_or_404(Appointment, id=appt_id, faculty=faculty)

            if decision == 'ACCEPTED':
                conflict = Appointment.objects.filter(
                    faculty=faculty, date=appt.date, period_code=appt.period_code, status='ACCEPTED'
                ).exclude(id=appt.id).exists()
                if conflict:
                    messages.error(request, 'Cannot accept: You already have an accepted appointment in this period.')
                    return redirect('faculty_dashboard')

            appt.status = decision
            appt.faculty_remarks = remarks
            appt.save()

            # Log ground truth for Machine Learning training
            day_code = WEEKDAY_MAP.get(appt.date.weekday(), 'MON')
            tt = getattr(faculty, 'timetable', None)
            load = TimetableSlot.objects.filter(timetable=tt, day_of_week=day_code).count() if tt else 0
            AvailabilityRecord.objects.create(
                faculty=faculty,
                date=appt.date,
                day_of_week=day_code,
                period_code=appt.period_code,
                daily_teaching_load=load,
                is_preferred_period=appt.period_code in faculty.get_preferred_list(),
                was_available_and_accepted=(decision == 'ACCEPTED')
            )
            train_availability_model()

            Notification.objects.create(
                recipient=appt.student.user,
                message=f"Prof. {faculty.user.get_full_name()} {decision.lower()} your appointment on {appt.date} ({appt.period_code})."
            )
            messages.success(request, f"Appointment marked as {decision}.")

        return redirect('faculty_dashboard')

    live_info = get_faculty_live_status(faculty)
    pending_requests = Appointment.objects.filter(faculty=faculty, status='PENDING').select_related('student__user').order_by('date')
    upcoming_meetings = Appointment.objects.filter(faculty=faculty, status='ACCEPTED', date__gte=today).select_related('student__user').order_by('date', 'period_code')
    commitments = FacultyCommitment.objects.filter(faculty=faculty, date__gte=today).order_by('date')

    context = {
        'faculty': faculty,
        'live_info': live_info,
        'pending_requests': pending_requests,
        'upcoming_meetings': upcoming_meetings,
        'commitments': commitments,
        'commitment_form': CommitmentForm(),
    }
    return render(request, 'dashboards/faculty_dashboard.html', context)


# ==================== STUDENT DASHBOARD ====================
@login_required
def student_dashboard(request):
    if request.user.role != 'STUDENT':
        return redirect('dashboard_router')

    student = get_object_or_404(Student, user=request.user)
    today = timezone.localdate()

    faculties = Faculty.objects.select_related('user', 'department').prefetch_related('subjects').all()
    available_faculties = []
    recommended_slots = []

    for f in faculties:
        live = get_faculty_live_status(f)
        if live['current']['status'] in ('AVAILABLE', 'POTENTIALLY AVAILABLE'):
            available_faculties.append({'faculty': f, 'live': live})
        preds = predict_best_slots(f, today)
        if preds:
            recommended_slots.append({'faculty': f, 'top_slot': preds[0]})

    recommended_slots.sort(key=lambda x: x['top_slot']['probability'], reverse=True)

    upcoming_appts = Appointment.objects.filter(student=student, date__gte=today).select_related('faculty__user', 'faculty__department').order_by('date')
    past_appts = Appointment.objects.filter(student=student, date__lt=today).select_related('faculty__user').order_by('-date')[:10]

    context = {
        'student': student,
        'available_faculties': available_faculties[:6],
        'recommended_slots': recommended_slots[:5],
        'upcoming_appts': upcoming_appts,
        'past_appts': past_appts,
    }
    return render(request, 'dashboards/student_dashboard.html', context)


# ==================== FACULTY DIRECTORY & DETAIL BOOKING ====================
@login_required
def faculty_directory(request):
    query = request.GET.get('q', '').strip()
    dept_id = request.GET.get('department', '').strip()

    faculties = Faculty.objects.select_related('user', 'department').prefetch_related('subjects').all()
    if query:
        faculties = faculties.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(subjects__name__icontains=query) |
            Q(subjects__code__icontains=query)
        ).distinct()
    if dept_id:
        faculties = faculties.filter(department_id=dept_id)

    cards = []
    for f in faculties:
        cards.append({'faculty': f, 'live': get_faculty_live_status(f)})

    context = {
        'cards': cards,
        'departments': Department.objects.all(),
        'query': query,
        'selected_dept': dept_id,
    }
    return render(request, 'directory/faculty_list.html', context)


@login_required
def faculty_detail(request, faculty_id):
    faculty = get_object_or_404(Faculty.objects.select_related('user', 'department'), id=faculty_id)
    selected_date_str = request.GET.get('date', timezone.localdate().isoformat())
    try:
        target_date = date.fromisoformat(selected_date_str)
    except ValueError:
        target_date = timezone.localdate()

    # Handle Appointment Booking Submission
    if request.method == 'POST' and request.user.role == 'STUDENT':
        student = get_object_or_404(Student, user=request.user)
        form = AppointmentRequestForm(request.POST)
        if form.is_valid():
            appt = form.save(commit=False)
            appt.student = student
            appt.faculty = faculty

            # Validate slot availability before creating request
            slot_check = evaluate_slot_status(faculty, appt.date, appt.period_code)
            if not slot_check['bookable']:
                messages.error(request, f"Selected slot is unavailable ({slot_check['status']}: {slot_check['detail']}).")
                return redirect('faculty_detail', faculty_id=faculty.id)

            duplicate = Appointment.objects.filter(
                student=student, faculty=faculty, date=appt.date,
                period_code=appt.period_code, status__in=['PENDING', 'ACCEPTED']
            ).exists()
            if duplicate:
                messages.warning(request, "You already have an active request for this exact slot.")
                return redirect('faculty_detail', faculty_id=faculty.id)

            appt.save()
            Notification.objects.create(
                recipient=faculty.user,
                message=f"New meeting request from {student.user.get_full_name()} ({student.roll_number}) for {appt.date} ({appt.period_code})."
            )
            messages.success(request, "Appointment request sent! You will be notified once the faculty responds.")
            return redirect('student_dashboard')
    else:
        form = AppointmentRequestForm(initial={'date': target_date})

    # Build Weekly Timetable Matrix
    timetable = getattr(faculty, 'timetable', None)
    slots_qs = TimetableSlot.objects.filter(timetable=timetable).select_related('subject') if timetable else []
    slot_lookup = {(s.day_of_week, s.period_code): s for s in slots_qs}

    weekly_grid = []
    for item in COLLEGE_SCHEDULE:
        row = {
            'code': item['code'],
            'name': item['name'],
            'time': f"{item['start'].strftime('%I:%M %p')} - {item['end'].strftime('%I:%M %p')}",
            'is_break': item['is_break'],
            'days': []
        }
        for d_code, _ in DAY_CHOICES:
            if item['is_break']:
                row['days'].append({'type': 'BREAK', 'label': item['name']})
            else:
                s = slot_lookup.get((d_code, item['code']))
                if s:
                    row['days'].append({
                        'type': s.slot_type,
                        'label': s.subject.code if s.subject else s.slot_type,
                        'room': s.room_number
                    })
                elif item['code'] in faculty.get_preferred_list():
                    row['days'].append({'type': 'PREFERRED', 'label': 'Available'})
                else:
                    row['days'].append({'type': 'FREE', 'label': 'Potentially Avail.'})
        weekly_grid.append(row)

    ml_recommendations = predict_best_slots(faculty, target_date, log_prediction=True)
    live_info = get_faculty_live_status(faculty)

    context = {
        'faculty': faculty,
        'live_info': live_info,
        'weekly_grid': weekly_grid,
        'days': DAY_CHOICES,
        'target_date': target_date.isoformat(),
        'ml_recommendations': ml_recommendations,
        'form': form,
    }
    return render(request, 'directory/faculty_detail.html', context)


@login_required
def mark_notifications_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok'})
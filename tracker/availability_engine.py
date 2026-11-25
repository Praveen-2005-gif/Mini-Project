from datetime import datetime, date
from django.utils import timezone
from .models import (
    COLLEGE_SCHEDULE, TimetableSlot, FacultyCommitment, Appointment
)

WEEKDAY_MAP = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}


def get_current_period_info(now_dt=None):
    """Identifies the active college period or break for a given datetime."""
    if now_dt is None:
        now_dt = timezone.localtime(timezone.now())
    current_t = now_dt.time()

    for item in COLLEGE_SCHEDULE:
        if item['start'] <= current_t < item['end']:
            return item
    return None


def evaluate_slot_status(faculty, target_date: date, period_code: str):
    """
    Determines exact status for a faculty member on a specific date & period.
    Strict hierarchy:
      1. Break check
      2. Regular Class / Lab -> IN CLASS
      3. Faculty Commitment -> IN MEETING / BUSY
      4. Accepted Appointment -> IN MEETING
      5. Explicit Consultation Slot or Preferred Period -> AVAILABLE
      6. Empty Slot -> POTENTIALLY AVAILABLE (Never confused with confirmed AVAILABLE)
    """
    if period_code in ('TB', 'LB'):
        label = 'Tea Break' if period_code == 'TB' else 'Lunch Break'
        return {'status': 'BREAK', 'badge': 'orange', 'detail': label, 'bookable': False}

    day_code = WEEKDAY_MAP.get(target_date.weekday(), 'SUN')
    if day_code == 'SUN':
        return {'status': 'BUSY', 'badge': 'red', 'detail': 'Sunday Holiday', 'bookable': False}

    # 1. Check Timetable Slot
    timetable = getattr(faculty, 'timetable', None)
    if timetable:
        slot = TimetableSlot.objects.filter(
            timetable=timetable, day_of_week=day_code, period_code=period_code
        ).select_related('subject').first()
        if slot:
            if slot.slot_type in ('CLASS', 'LAB'):
                subj_name = slot.subject.code if slot.subject else slot.slot_type
                return {
                    'status': 'IN CLASS',
                    'badge': 'red',
                    'detail': f"{subj_name} ({slot.room_number or 'Class'})",
                    'bookable': False,
                }
            elif slot.slot_type == 'CONSULTATION':
                return {
                    'status': 'AVAILABLE',
                    'badge': 'green',
                    'detail': 'Confirmed Consultation Hour',
                    'bookable': True,
                }

    # 2. Check Ad-Hoc Commitments
    commitment = FacultyCommitment.objects.filter(
        faculty=faculty, date=target_date, period_code=period_code
    ).first()
    if commitment:
        st = 'IN MEETING' if commitment.commitment_type == 'MEETING' else 'BUSY'
        return {'status': st, 'badge': 'red', 'detail': commitment.title, 'bookable': False}

    # 3. Check Accepted Appointments
    appt = Appointment.objects.filter(
        faculty=faculty, date=target_date, period_code=period_code, status='ACCEPTED'
    ).select_related('student__user').first()
    if appt:
        return {
            'status': 'IN MEETING',
            'badge': 'red',
            'detail': f"Student Meeting ({appt.student.roll_number})",
            'bookable': False,
        }

    # 4. Check Faculty Preferred Consultation Periods
    if period_code in faculty.get_preferred_list():
        return {
            'status': 'AVAILABLE',
            'badge': 'green',
            'detail': 'Preferred Consultation Slot',
            'bookable': True,
        }

    # 5. Free period without explicit confirmation
    return {
        'status': 'POTENTIALLY AVAILABLE',
        'badge': 'teal',
        'detail': 'No scheduled class or meeting',
        'bookable': True,
    }


def get_faculty_live_status(faculty, now_dt=None):
    """Computes real-time current status + next available period today."""
    if now_dt is None:
        now_dt = timezone.localtime(timezone.now())
    today = now_dt.date()
    active_period = get_current_period_info(now_dt)

    # Honor explicit live override if set by faculty
    if faculty.manual_status == 'BUSY':
        current_info = {'status': 'BUSY', 'badge': 'red', 'detail': 'Marked Busy by Faculty'}
    elif faculty.manual_status == 'IN_MEETING':
        current_info = {'status': 'IN MEETING', 'badge': 'red', 'detail': 'Currently in Meeting'}
    elif faculty.manual_status == 'AVAILABLE':
        current_info = {'status': 'AVAILABLE', 'badge': 'green', 'detail': 'Available in Cabin'}
    elif active_period is None:
        current_info = {'status': 'POTENTIALLY AVAILABLE', 'badge': 'teal', 'detail': 'Outside Class Hours'}
    elif active_period['is_break']:
        current_info = {'status': 'BREAK', 'badge': 'orange', 'detail': active_period['name']}
    else:
        current_info = evaluate_slot_status(faculty, today, active_period['code'])

    # Find next available / potentially available period today
    next_slot = "Tomorrow 8:45 AM"
    current_t = now_dt.time()
    for item in COLLEGE_SCHEDULE:
        if item['is_break']:
            continue
        if item['start'] > current_t or (active_period and item['code'] == active_period['code'] and current_info['status'] in ('AVAILABLE', 'POTENTIALLY AVAILABLE')):
            eval_res = evaluate_slot_status(faculty, today, item['code'])
            if eval_res['bookable']:
                next_slot = f"{item['name']} ({item['start'].strftime('%I:%M %p')})"
                break

    # Build full today's timeline
    daily_timeline = []
    for item in COLLEGE_SCHEDULE:
        slot_eval = evaluate_slot_status(faculty, today, item['code'])
        daily_timeline.append({
            'code': item['code'],
            'name': item['name'],
            'time_range': f"{item['start'].strftime('%I:%M %p')} - {item['end'].strftime('%I:%M %p')}",
            'is_break': item['is_break'],
            **slot_eval
        })

    return {
        'current': current_info,
        'next_available': next_slot,
        'daily_timeline': daily_timeline,
    }

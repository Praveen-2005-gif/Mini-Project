import os
import joblib
import numpy as np
import pandas as pd
from datetime import date
from django.conf import settings
from sklearn.ensemble import RandomForestClassifier
from .models import (
    COLLEGE_SCHEDULE, AvailabilityRecord, Appointment,
    TimetableSlot, PredictionHistory
)
from .availability_engine import evaluate_slot_status, WEEKDAY_MAP

MODEL_PATH = os.path.join(settings.ML_MODELS_DIR, 'availability_rf_model.joblib')
MIN_TRAINING_SAMPLES = 30  # Cold-start threshold to prevent fake ML accuracy claims

PERIOD_INDEX = {'P1': 1, 'P2': 2, 'P3': 3, 'P4': 4, 'P5': 5, 'P6': 6, 'P7': 7, 'P8': 8}
DAY_INDEX = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5}


def _extract_features(faculty_id: int, day_code: str, period_code: str, daily_load: int, is_preferred: bool, hist_accept_rate: float):
    return [
        faculty_id,
        DAY_INDEX.get(day_code, 0),
        PERIOD_INDEX.get(period_code, 1),
        daily_load,
        int(is_preferred),
        hist_accept_rate,
    ]


def train_availability_model():
    """
    Trains RandomForestClassifier on AvailabilityRecord + resolved Appointments.
    Returns status dictionary indicating whether ML model is active or in cold-start mode.
    """
    records = AvailabilityRecord.objects.all()
    if records.count() < MIN_TRAINING_SAMPLES:
        if os.path.exists(MODEL_PATH):
            os.remove(MODEL_PATH)
        return {
            'trained': False,
            'mode': 'PROVISIONAL_RULE',
            'sample_count': records.count(),
            'message': f"Insufficient historical records ({records.count()}/{MIN_TRAINING_SAMPLES}). Using provisional rule-based scoring."
        }

    rows = []
    for r in records:
        total_appts = Appointment.objects.filter(faculty_id=r.faculty_id).exclude(status='PENDING').count()
        accepted_appts = Appointment.objects.filter(faculty_id=r.faculty_id, status__in=['ACCEPTED', 'COMPLETED']).count()
        accept_rate = (accepted_appts / total_appts) if total_appts > 0 else 0.75

        feats = _extract_features(
            r.faculty_id, r.day_of_week, r.period_code,
            r.daily_teaching_load, r.is_preferred_period, accept_rate
        )
        rows.append(feats + [int(r.was_available_and_accepted)])

    df = pd.DataFrame(rows, columns=['faculty_id', 'day', 'period', 'load', 'preferred', 'accept_rate', 'target'])

    # Ensure both classes exist before fitting RandomForest
    if df['target'].nunique() < 2:
        return {
            'trained': False,
            'mode': 'PROVISIONAL_RULE',
            'sample_count': len(df),
            'message': "Waiting for diverse outcome samples (both accepted and rejected/busy outcomes) to train Random Forest."
        }

    X = df[['faculty_id', 'day', 'period', 'load', 'preferred', 'accept_rate']]
    y = df['target']

    clf = RandomForestClassifier(n_estimators=100, max_depth=6, random_state=42)
    clf.fit(X, y)
    joblib.dump(clf, MODEL_PATH)

    return {
        'trained': True,
        'mode': 'RANDOM_FOREST',
        'sample_count': len(df),
        'message': f"Random Forest Classifier trained successfully on {len(df)} historical slot records."
    }


def predict_best_slots(faculty, target_date: date, log_prediction=False):
    """
    Ranks all bookable periods for a faculty member on `target_date`.
    Uses Random Forest if trained; falls back transparently to Provisional Rule-Based Engine.
    """
    day_code = WEEKDAY_MAP.get(target_date.weekday(), 'MON')
    timetable = getattr(faculty, 'timetable', None)
    daily_load = TimetableSlot.objects.filter(
        timetable=timetable, day_of_week=day_code, slot_type__in=['CLASS', 'LAB']
    ).count() if timetable else 0

    total_appts = Appointment.objects.filter(faculty=faculty).exclude(status='PENDING').count()
    accepted_appts = Appointment.objects.filter(faculty=faculty, status__in=['ACCEPTED', 'COMPLETED']).count()
    hist_accept_rate = (accepted_appts / total_appts) if total_appts > 0 else 0.75

    clf = joblib.load(MODEL_PATH) if os.path.exists(MODEL_PATH) else None
    mode = 'RANDOM_FOREST' if clf is not None else 'PROVISIONAL_RULE'

    recommendations = []
    for item in COLLEGE_SCHEDULE:
        if item['is_break']:
            continue
        p_code = item['code']
        slot_eval = evaluate_slot_status(faculty, target_date, p_code)
        if not slot_eval['bookable']:
            continue

        is_pref = p_code in faculty.get_preferred_list()

        if clf is not None:
            feats = np.array([_extract_features(
                faculty.id, day_code, p_code, daily_load, is_pref, hist_accept_rate
            )])
            prob = float(clf.predict_proba(feats)[0][1]) * 100.0
            reason = "Predicted via Random Forest historical patterns"
        else:
            # Transparent Provisional Rule-Based Heuristic
            base_score = 88.0 if slot_eval['status'] == 'AVAILABLE' else 68.0
            load_penalty = daily_load * 3.5
            pref_bonus = 8.0 if is_pref else 0.0
            afternoon_bonus = 4.0 if p_code in ('P4', 'P7', 'P8') else 0.0
            prob = max(25.0, min(97.0, base_score - load_penalty + pref_bonus + afternoon_bonus))
            reason = "Provisional Rule-Based Score (Preferred Hour)" if is_pref else "Provisional Rule-Based Score (Free Period)"

        recommendations.append({
            'period_code': p_code,
            'period_name': item['name'],
            'time_range': f"{item['start'].strftime('%I:%M %p')} - {item['end'].strftime('%I:%M %p')}",
            'status': slot_eval['status'],
            'probability': round(prob, 1),
            'mode': mode,
            'is_provisional': mode == 'PROVISIONAL_RULE',
            'reason': reason,
        })

    recommendations.sort(key=lambda x: x['probability'], reverse=True)

    if log_prediction and recommendations:
        top = recommendations[0]
        PredictionHistory.objects.create(
            faculty=faculty,
            target_date=target_date,
            recommended_period=top['period_code'],
            probability_score=top['probability'],
            model_mode=mode,
        )

    return recommendations
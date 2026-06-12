from datetime import date as date_type
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.schedule import FillingWindow, DoctorRoutine, DoctorRestriction, DoctorWindowConfirmation, Holiday
from app.utils.decorators import medico_required
from app.utils.audit import log as audit
from app.utils.calendar_helpers import (
    build_calendar_weeks, group_entries_by_date, location_palette, WEEKDAY_NAMES,
    default_schedule_month,
)

doctor_bp = Blueprint('doctor', __name__, url_prefix='/medico')

DAYS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
WEEKS = {1: '1ª sem.', 2: '2ª sem.', 3: '3ª sem.', 4: '4ª sem.', 5: '5ª sem.'}
FREQ_LABELS = {'weekly': 'Semanal', 'biweekly': 'Quinzenal', 'monthly': 'Mensal'}


def _get_open_window():
    return FillingWindow.query.filter_by(status='open').order_by(FillingWindow.year.desc()).first()


@doctor_bp.context_processor
def inject_open_window_flag():
    return dict(has_open_window=_get_open_window() is not None)


def _is_confirmed(doctor_id, window_id):
    return DoctorWindowConfirmation.query.filter_by(
        doctor_id=doctor_id, window_id=window_id
    ).first() is not None


@doctor_bp.route('/dashboard')
@login_required
@medico_required
def dashboard():
    from datetime import datetime as dt
    from app.services.kpi_service import get_doctor_month_stats
    from app.services.mednews_service import get_mednews_dashboard_context

    open_window = _get_open_window()
    confirmed = _is_confirmed(current_user.id, open_window.id) if open_window else False
    routines_count = (DoctorRoutine.query
                      .filter_by(doctor_id=current_user.id, window_id=open_window.id)
                      .count()) if open_window else 0
    restrictions_count = (DoctorRestriction.query
                          .filter_by(doctor_id=current_user.id, window_id=open_window.id)
                          .count()) if open_window else 0

    published_window = (FillingWindow.query.filter_by(status='published')
                        .order_by(FillingWindow.year.desc()).first())
    month = request.args.get('month', type=int, default=dt.now().month)
    if month < 1 or month > 12:
        month = 1
    if published_window:
        month = default_schedule_month(published_window, month)
    month_stats = get_doctor_month_stats(current_user.id, published_window.id, month) if published_window else {}
    month_names = ['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

    mednews_ctx = get_mednews_dashboard_context()

    return render_template('doctor/dashboard.html',
                           window=open_window, confirmed=confirmed,
                           routines_count=routines_count,
                           restrictions_count=restrictions_count,
                           published_window=published_window,
                           month_stats=month_stats,
                           month=month,
                           month_names=month_names,
                           **mednews_ctx)


@doctor_bp.route('/rotinas', methods=['GET', 'POST'])
@login_required
@medico_required
def routines():
    from app.forms.doctor import DoctorRoutineForm
    window = _get_open_window()
    if not window:
        flash('Não há janela de preenchimento aberta no momento.', 'warning')
        return redirect(url_for('doctor.dashboard'))

    confirmed = _is_confirmed(current_user.id, window.id)
    form = DoctorRoutineForm(doctor=current_user)
    routines = (DoctorRoutine.query
                .filter_by(doctor_id=current_user.id, window_id=window.id)
                .order_by(DoctorRoutine.day_of_week)
                .all())

    if not confirmed and form.validate_on_submit():
        routine = DoctorRoutine(
            doctor_id=current_user.id,
            location_id=form.location_id.data,
            window_id=window.id,
            frequency=form.frequency.data,
            day_of_week=form.day_of_week.data,
            week_of_month=form.week_of_month.data if form.week_of_month.data else None,
            scale_type=form.scale_type.data.strip() or None,
        )
        db.session.add(routine)
        audit('add_routine', 'DoctorRoutine', None, {'window_id': window.id})
        db.session.commit()
        flash('Rotina adicionada.', 'success')
        return redirect(url_for('doctor.routines'))

    return render_template('doctor/routines.html',
                           form=form, window=window, routines=routines,
                           confirmed=confirmed, days=DAYS,
                           freq_labels=FREQ_LABELS, weeks=WEEKS)


@doctor_bp.route('/rotinas/<int:id>/excluir', methods=['POST'])
@login_required
@medico_required
def routines_delete(id):
    routine = db.session.get(DoctorRoutine, id) or abort(404)
    if routine.doctor_id != current_user.id:
        abort(403)
    window = db.session.get(FillingWindow, routine.window_id)
    if _is_confirmed(current_user.id, window.id):
        flash('Você já confirmou seus dados. Solicite ao ADMIN para desbloquear.', 'warning')
        return redirect(url_for('doctor.routines'))
    audit('delete_routine', 'DoctorRoutine', routine.id, {})
    db.session.delete(routine)
    db.session.commit()
    flash('Rotina removida.', 'info')
    return redirect(url_for('doctor.routines'))


@doctor_bp.route('/restricoes', methods=['GET', 'POST'])
@login_required
@medico_required
def restrictions():
    from app.forms.doctor import DoctorRestrictionForm
    window = _get_open_window()
    if not window:
        flash('Não há janela de preenchimento aberta no momento.', 'warning')
        return redirect(url_for('doctor.dashboard'))

    confirmed = _is_confirmed(current_user.id, window.id)
    form = DoctorRestrictionForm()
    restrictions = (DoctorRestriction.query
                    .filter_by(doctor_id=current_user.id, window_id=window.id)
                    .order_by(DoctorRestriction.restricted_date)
                    .all())

    if not confirmed and form.validate_on_submit():
        existing = DoctorRestriction.query.filter_by(
            doctor_id=current_user.id,
            restricted_date=form.restricted_date.data,
        ).first()
        if existing:
            flash('Esta data já está cadastrada.', 'warning')
        else:
            restr = DoctorRestriction(
                doctor_id=current_user.id,
                window_id=window.id,
                restricted_date=form.restricted_date.data,
                reason=form.reason.data.strip() or None,
            )
            db.session.add(restr)
            audit('add_restriction', 'DoctorRestriction', None,
                  {'date': str(form.restricted_date.data)})
            db.session.commit()
            flash('Restrição adicionada.', 'success')
            return redirect(url_for('doctor.restrictions'))

    return render_template('doctor/restrictions.html',
                           form=form, window=window, restrictions=restrictions,
                           confirmed=confirmed)


@doctor_bp.route('/restricoes/<int:id>/excluir', methods=['POST'])
@login_required
@medico_required
def restrictions_delete(id):
    restr = db.session.get(DoctorRestriction, id) or abort(404)
    if restr.doctor_id != current_user.id:
        abort(403)
    window = db.session.get(FillingWindow, restr.window_id)
    if _is_confirmed(current_user.id, window.id):
        flash('Você já confirmou seus dados. Solicite ao ADMIN para desbloquear.', 'warning')
        return redirect(url_for('doctor.restrictions'))
    audit('delete_restriction', 'DoctorRestriction', restr.id, {})
    db.session.delete(restr)
    db.session.commit()
    flash('Restrição removida.', 'info')
    return redirect(url_for('doctor.restrictions'))


@doctor_bp.route('/confirmacao')
@login_required
@medico_required
def confirmation():
    window = _get_open_window()
    if not window:
        flash('Não há janela de preenchimento aberta.', 'warning')
        return redirect(url_for('doctor.dashboard'))

    confirmed = _is_confirmed(current_user.id, window.id)
    routines = (DoctorRoutine.query
                .filter_by(doctor_id=current_user.id, window_id=window.id)
                .order_by(DoctorRoutine.day_of_week)
                .all())
    restrictions = (DoctorRestriction.query
                    .filter_by(doctor_id=current_user.id, window_id=window.id)
                    .order_by(DoctorRestriction.restricted_date)
                    .all())
    return render_template('doctor/confirm.html',
                           window=window, confirmed=confirmed,
                           routines=routines, restrictions=restrictions,
                           days=DAYS, freq_labels=FREQ_LABELS, weeks=WEEKS)


@doctor_bp.route('/confirmar', methods=['POST'])
@login_required
@medico_required
def confirm():
    window = _get_open_window()
    if not window:
        abort(404)
    if _is_confirmed(current_user.id, window.id):
        flash('Você já confirmou seus dados.', 'info')
        return redirect(url_for('doctor.dashboard'))
    conf = DoctorWindowConfirmation(doctor_id=current_user.id, window_id=window.id)
    db.session.add(conf)
    audit('confirm_window', 'DoctorWindowConfirmation', None, {'window_id': window.id})
    db.session.commit()
    flash('Dados confirmados com sucesso! Para alterar, solicite ao administrador.', 'success')
    return redirect(url_for('doctor.dashboard'))


@doctor_bp.route('/escala')
@login_required
@medico_required
def schedule():
    from app.models.schedule import FillingWindow, Schedule
    from app.models.location import Location

    # Janela publicada mais recente
    window = (FillingWindow.query
              .filter_by(status='published')
              .order_by(FillingWindow.year.desc())
              .first())
    if not window:
        flash('Nenhuma escala publicada disponível.', 'info')
        return redirect(url_for('doctor.dashboard'))

    month = request.args.get('month', type=int, default=1)
    if month < 1 or month > 12:
        month = 1
    month = default_schedule_month(window, month)

    import calendar
    last_day = date_type(window.year, month, calendar.monthrange(window.year, month)[1])

    entries = (Schedule.query
               .filter_by(window_id=window.id, doctor_id=current_user.id)
               .filter(
                   Schedule.date >= date_type(window.year, month, 1),
                   Schedule.date <= last_day,
               )
               .order_by(Schedule.date)
               .all())

    locations = {l.id: l for l in Location.query.all()}
    month_names = ['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

    # Dados para a grade de calendário
    calendar_weeks = build_calendar_weeks(window.year, month)
    entries_by_date = group_entries_by_date(entries)
    holidays_by_date = {h.date: h for h in Holiday.query.filter_by(window_id=window.id).all()}
    location_list = sorted(locations.values(), key=lambda l: l.id)
    loc_color = location_palette(location_list)
    today = date_type.today()

    return render_template('doctor/schedule.html',
                           window=window, entries=entries, locations=locations,
                           month=month, month_names=month_names,
                           calendar_weeks=calendar_weeks, entries_by_date=entries_by_date,
                           holidays_by_date=holidays_by_date, location_list=location_list,
                           loc_color=loc_color, today=today, weekday_names=WEEKDAY_NAMES)


@doctor_bp.route('/escala-grupo')
@login_required
@medico_required
def group_schedule():
    from app.services.schedule_view_service import get_schedule_review_context

    # Janela publicada mais recente
    window = (FillingWindow.query
              .filter_by(status='published')
              .order_by(FillingWindow.year.desc())
              .first())
    if not window:
        flash('Nenhuma escala publicada disponível.', 'info')
        return redirect(url_for('doctor.dashboard'))

    month = request.args.get('month', type=int, default=1)
    if month < 1 or month > 12:
        month = 1
    month = default_schedule_month(window, month)

    ctx = get_schedule_review_context(window, month)
    return render_template('doctor/group_schedule.html', window=window, **ctx)


# ── Trocas ────────────────────────────────────────────────────────────────────

@doctor_bp.route('/trocas')
@login_required
@medico_required
def swaps():
    from app.models.swap import ScheduleSwap, SwapNotification
    from app.models.location import Location
    from app.services.swap_service import build_swap_view_data

    # Marcar notificações como vistas
    SwapNotification.query.filter_by(
        notified_doctor_id=current_user.id, seen=False
    ).update({'seen': True})
    db.session.commit()

    # Minhas solicitações
    my_swaps = (ScheduleSwap.query
                .filter_by(requester_id=current_user.id)
                .order_by(ScheduleSwap.requested_at.desc())
                .all())

    # Todas as trocas em aberto solicitadas por outros médicos
    open_swaps = (ScheduleSwap.query
                  .filter(ScheduleSwap.status == 'open',
                          ScheduleSwap.requester_id != current_user.id)
                  .order_by(ScheduleSwap.requested_at.asc())
                  .all())

    locations = {l.id: l for l in Location.query.all()}
    from app.models.user import User
    doctors = {u.id: u for u in User.query.all()}

    eligible_by_swap, eligible_names_by_swap, days_open_by_swap = build_swap_view_data(
        my_swaps + open_swaps, doctors
    )

    return render_template('doctor/swaps/list.html',
                           my_swaps=my_swaps, open_swaps=open_swaps,
                           locations=locations, doctors=doctors,
                           eligible_by_swap=eligible_by_swap,
                           eligible_names_by_swap=eligible_names_by_swap,
                           days_open_by_swap=days_open_by_swap)


@doctor_bp.route('/trocas/solicitar/<int:schedule_id>', methods=['POST'])
@login_required
@medico_required
def swaps_request(schedule_id):
    from app.services.swap_service import request_swap
    try:
        swap = request_swap(schedule_id, current_user.id)
        audit('request_swap', 'ScheduleSwap', swap.id, {'schedule_id': schedule_id})
        flash('Solicitação de troca criada. Médicos disponíveis foram notificados.', 'success')
    except ValueError as e:
        flash(str(e), 'warning')
    return redirect(url_for('doctor.swaps'))


@doctor_bp.route('/trocas/<int:swap_id>/aceitar', methods=['POST'])
@login_required
@medico_required
def swaps_accept(swap_id):
    from app.services.swap_service import accept_swap
    try:
        accept_swap(swap_id, current_user.id)
        audit('accept_swap', 'ScheduleSwap', swap_id, {})
        flash('Troca aceita! O plantão foi adicionado à sua escala.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    return redirect(url_for('doctor.swaps'))


@doctor_bp.route('/trocas/<int:swap_id>/cancelar', methods=['POST'])
@login_required
@medico_required
def swaps_cancel(swap_id):
    from app.services.swap_service import cancel_swap
    try:
        cancel_swap(swap_id, current_user.id)
        audit('cancel_swap', 'ScheduleSwap', swap_id, {})
        flash('Solicitação cancelada.', 'info')
    except ValueError as e:
        flash(str(e), 'warning')
    return redirect(url_for('doctor.swaps'))


@doctor_bp.route('/trocas/notificacoes')
@login_required
@medico_required
def swaps_notifications_count():
    from flask import jsonify
    from app.models.swap import SwapNotification, ScheduleSwap
    count = (SwapNotification.query
             .join(ScheduleSwap, SwapNotification.swap_id == ScheduleSwap.id)
             .filter(SwapNotification.notified_doctor_id == current_user.id,
                     SwapNotification.seen == False,
                     ScheduleSwap.status == 'open')
             .count())
    return jsonify({'count': count})

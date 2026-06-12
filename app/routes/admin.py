from collections import defaultdict
from datetime import datetime, date as date_type, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.user import User
from app.models.location import Location, DoctorLocationLink
from app.models.schedule import FillingWindow, DoctorWindowConfirmation, Holiday, Schedule, CoverageException, CoverageAcceptance
from app.utils.decorators import admin_required
from app.utils.audit import log as audit
from app.utils.calendar_helpers import (
    build_calendar_weeks, group_entries_by_date, location_palette,
    location_abbr, WEEKDAY_NAMES, default_schedule_month,
)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    from app.models.swap import ScheduleSwap
    from app.services.kpi_service import get_coverage_summary
    from app.services.mednews_service import get_mednews_dashboard_context
    total_doctors = User.query.filter_by(role='medico', active=True).count()
    total_locations = Location.query.filter_by(active=True).count()
    total_swaps = ScheduleSwap.query.filter_by(status='open').count()

    today = date_type.today()
    current_window = (FillingWindow.query
                       .filter_by(status='published', year=today.year)
                       .first())
    coverage = get_coverage_summary(current_window.id, today.month) if current_window else None
    month_names = ['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

    if today.month == 12:
        next_month, next_year = 1, today.year + 1
    else:
        next_month, next_year = today.month + 1, today.year

    if current_window and next_year == current_window.year:
        next_window = current_window
    else:
        next_window = (FillingWindow.query
                        .filter_by(status='published', year=next_year)
                        .first())
    coverage_next = get_coverage_summary(next_window.id, next_month) if next_window else None

    mednews_ctx = get_mednews_dashboard_context()

    return render_template('admin/dashboard.html',
                           total_doctors=total_doctors,
                           total_locations=total_locations,
                           total_swaps=total_swaps,
                           current_window=current_window,
                           coverage=coverage,
                           current_month=today.month,
                           month_names=month_names,
                           next_month=next_month,
                           next_year=next_year,
                           next_window=next_window,
                           coverage_next=coverage_next,
                           **mednews_ctx)


# ── Médicos ───────────────────────────────────────────────────────────────────

@admin_bp.route('/medicos')
@login_required
@admin_required
def doctors():
    q = request.args.get('q', '').strip()
    query = User.query.filter_by(role='medico')
    if q:
        query = query.filter(User.name.ilike(f'%{q}%') | User.crm.ilike(f'%{q}%'))
    doctors = query.order_by(User.name).all()
    return render_template('admin/doctors/list.html', doctors=doctors, q=q)


@admin_bp.route('/medicos/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def doctors_new():
    from app.forms.admin import DoctorForm
    from app.services.location_service import link_doctor_to_all_positions
    form = DoctorForm()
    if form.validate_on_submit():
        if not form.password.data:
            flash('A senha é obrigatória para novos médicos.', 'danger')
            return render_template('admin/doctors/form.html', form=form, title='Novo Médico')
        doctor = User(
            name=form.name.data.strip(),
            crm=form.crm.data.strip() or None,
            login=form.login.data.strip(),
            email=form.email.data.strip(),
            role='medico',
        )
        doctor.set_password(form.password.data)
        db.session.add(doctor)
        db.session.flush()
        link_doctor_to_all_positions(doctor.id)
        audit('create_doctor', 'User', doctor.id, {'login': doctor.login})
        db.session.commit()
        flash(f'Médico "{doctor.name}" cadastrado com sucesso.', 'success')
        return redirect(url_for('admin.doctors'))
    return render_template('admin/doctors/form.html', form=form, title='Novo Médico')


@admin_bp.route('/medicos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def doctors_edit(id):
    from app.forms.admin import DoctorForm
    from app.services.location_service import get_position_universe
    doctor = db.session.get(User, id) or abort(404)
    form = DoctorForm(doctor=doctor, obj=doctor)
    if form.validate_on_submit():
        doctor.name = form.name.data.strip()
        doctor.crm = form.crm.data.strip() or None
        doctor.login = form.login.data.strip()
        doctor.email = form.email.data.strip()
        if form.password.data:
            doctor.set_password(form.password.data)
        audit('edit_doctor', 'User', doctor.id, {'login': doctor.login})
        db.session.commit()
        flash(f'Médico "{doctor.name}" atualizado.', 'success')
        return redirect(url_for('admin.doctors'))

    universe = get_position_universe()
    universe_by_loc = defaultdict(list)
    for loc_id, scale_type in universe:
        universe_by_loc[loc_id].append(scale_type)
    doctor_links = {(lk.location_id, lk.scale_type): lk.active for lk in doctor.location_links}
    links_by_location = []
    for loc in Location.query.filter_by(active=True).order_by(Location.name).all():
        combos = [{'scale_type': st, 'active': doctor_links.get((loc.id, st), False)}
                  for st in sorted(universe_by_loc.get(loc.id, []))]
        links_by_location.append({'location': loc, 'combos': combos})

    return render_template('admin/doctors/form.html', form=form, title='Editar Médico', doctor=doctor,
                           links_by_location=links_by_location)


@admin_bp.route('/medicos/<int:id>/vinculos', methods=['POST'])
@login_required
@admin_required
def doctors_links(id):
    from app.services.location_service import get_position_universe, set_doctor_link, add_new_position
    doctor = db.session.get(User, id) or abort(404)

    for location_id, scale_type in get_position_universe():
        checked = request.form.get(f'link_{location_id}_{scale_type}') == 'on'
        set_doctor_link(doctor.id, location_id, scale_type, checked)

    for loc in Location.query.filter_by(active=True).all():
        new_st = request.form.get(f'new_position_{loc.id}', '').strip()
        if new_st:
            add_new_position(loc.id, new_st)

    audit('edit_doctor_links', 'User', doctor.id, {})
    db.session.commit()
    flash('Vínculos atualizados.', 'success')
    return redirect(url_for('admin.doctors_edit', id=id))


@admin_bp.route('/medicos/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def doctors_toggle(id):
    doctor = db.session.get(User, id) or abort(404)
    doctor.active = not doctor.active
    audit('toggle_doctor', 'User', doctor.id, {'active': doctor.active})
    db.session.commit()
    status = 'ativado' if doctor.active else 'desativado'
    flash(f'Médico "{doctor.name}" {status}.', 'info')
    return redirect(url_for('admin.doctors'))


# ── Locais ────────────────────────────────────────────────────────────────────

@admin_bp.route('/locais')
@login_required
@admin_required
def locations():
    q = request.args.get('q', '').strip()
    query = Location.query
    if q:
        query = query.filter(Location.name.ilike(f'%{q}%'))
    locations = query.order_by(Location.name).all()
    return render_template('admin/locations/list.html', locations=locations, q=q)


@admin_bp.route('/locais/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def locations_new():
    from app.forms.admin import LocationForm
    form = LocationForm()
    if form.validate_on_submit():
        loc = Location(
            name=form.name.data.strip(),
            scale_type=form.scale_type.data.strip() or None,
        )
        db.session.add(loc)
        db.session.flush()
        audit('create_location', 'Location', loc.id, {'name': loc.name})
        db.session.commit()
        flash(f'Local "{loc.name}" cadastrado.', 'success')
        return redirect(url_for('admin.locations'))
    return render_template('admin/locations/form.html', form=form, title='Novo Local')


@admin_bp.route('/locais/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@admin_required
def locations_edit(id):
    from app.forms.admin import LocationForm
    from app.models.location import DoctorLocationLink, LocationScaleRequirement
    loc = db.session.get(Location, id) or abort(404)
    form = LocationForm(obj=loc)
    if form.validate_on_submit():
        loc.name = form.name.data.strip()
        loc.scale_type = form.scale_type.data.strip() or None
        audit('edit_location', 'Location', loc.id, {'name': loc.name})
        db.session.commit()
        flash(f'Local "{loc.name}" atualizado.', 'success')
        return redirect(url_for('admin.locations'))

    scale_types = sorted({lk.scale_type for lk in
                           DoctorLocationLink.query.filter_by(location_id=id, active=True).all()
                           if lk.scale_type})
    existing = {r.scale_type: r.required for r in
                LocationScaleRequirement.query.filter_by(location_id=id).all()}
    scale_requirements = [{'scale_type': st, 'required': existing.get(st, True)} for st in scale_types]
    return render_template('admin/locations/form.html', form=form, title='Editar Local', location=loc,
                           scale_requirements=scale_requirements)


@admin_bp.route('/locais/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def locations_toggle(id):
    loc = db.session.get(Location, id) or abort(404)
    loc.active = not loc.active
    audit('toggle_location', 'Location', loc.id, {'active': loc.active})
    db.session.commit()
    status = 'ativado' if loc.active else 'desativado'
    flash(f'Local "{loc.name}" {status}.', 'info')
    return redirect(url_for('admin.locations'))


@admin_bp.route('/locais/<int:id>/requisitos', methods=['POST'])
@login_required
@admin_required
def locations_scale_requirements(id):
    from app.models.location import DoctorLocationLink, LocationScaleRequirement
    loc = db.session.get(Location, id) or abort(404)
    scale_types = sorted({lk.scale_type for lk in
                           DoctorLocationLink.query.filter_by(location_id=id, active=True).all()
                           if lk.scale_type})
    for st in scale_types:
        required = request.form.get(f'required_{st}') == 'on'
        req = LocationScaleRequirement.query.filter_by(location_id=id, scale_type=st).first()
        if req is None:
            req = LocationScaleRequirement(location_id=id, scale_type=st)
            db.session.add(req)
        req.required = required
    audit('edit_location_scale_requirements', 'Location', loc.id, {'scale_types': scale_types})
    db.session.commit()
    flash('Requisitos de cobertura atualizados.', 'success')
    return redirect(url_for('admin.locations_edit', id=id))


@admin_bp.route('/locais/<int:id>/escalas/adicionar', methods=['POST'])
@login_required
@admin_required
def locations_scale_type_add(id):
    from app.services.location_service import add_new_position
    loc = db.session.get(Location, id) or abort(404)
    new_st = request.form.get('new_scale_type', '').strip()
    if new_st:
        add_new_position(loc.id, new_st)
        audit('add_location_scale_type', 'Location', loc.id, {'scale_type': new_st})
        db.session.commit()
        flash(f'Posição "{new_st}" adicionada e vinculada a todos os médicos.', 'success')
    else:
        flash('Informe um nome para a nova posição.', 'warning')
    return redirect(url_for('admin.locations_edit', id=id))


@admin_bp.route('/locais/<int:id>/escalas/remover', methods=['POST'])
@login_required
@admin_required
def locations_scale_type_remove(id):
    from app.services.location_service import remove_position
    loc = db.session.get(Location, id) or abort(404)
    scale_type = request.form.get('scale_type', '').strip()
    if scale_type:
        remove_position(loc.id, scale_type)
        audit('remove_location_scale_type', 'Location', loc.id, {'scale_type': scale_type})
        db.session.commit()
        flash(f'Posição "{scale_type}" removida de {loc.name}. Médicos desvinculados; '
              f'plantões já lançados permanecem no histórico.', 'info')
    return redirect(url_for('admin.locations_edit', id=id))


# ── Janela de Preenchimento ───────────────────────────────────────────────────

@admin_bp.route('/janela')
@login_required
@admin_required
def windows():
    windows = FillingWindow.query.order_by(FillingWindow.year.desc()).all()
    return render_template('admin/window/list.html', windows=windows)


@admin_bp.route('/janela/nova', methods=['GET', 'POST'])
@login_required
@admin_required
def windows_new():
    from app.forms.window import FillingWindowForm
    form = FillingWindowForm()
    if form.validate_on_submit():
        window = FillingWindow(
            year=form.year.data,
            open_at=form.open_at.data,
            close_at=form.close_at.data,
            created_by=current_user.id,
        )
        db.session.add(window)
        db.session.flush()
        audit('create_window', 'FillingWindow', window.id, {'year': window.year})
        db.session.commit()
        flash(f'Janela {window.year} criada.', 'success')
        return redirect(url_for('admin.windows'))
    return render_template('admin/window/form.html', form=form, title='Nova Janela')


@admin_bp.route('/janela/<int:id>/abrir', methods=['POST'])
@login_required
@admin_required
def windows_open(id):
    window = db.session.get(FillingWindow, id) or abort(404)
    if window.status not in ('draft',):
        flash('Só é possível abrir janelas em rascunho.', 'warning')
        return redirect(url_for('admin.windows'))
    window.status = 'open'
    window.open_at = window.open_at or datetime.utcnow()
    audit('open_window', 'FillingWindow', window.id, {'year': window.year})
    db.session.commit()
    flash(f'Janela {window.year} aberta para preenchimento.', 'success')
    return redirect(url_for('admin.windows'))


@admin_bp.route('/janela/<int:id>/fechar', methods=['POST'])
@login_required
@admin_required
def windows_close(id):
    window = db.session.get(FillingWindow, id) or abort(404)
    if window.status != 'open':
        flash('Só é possível fechar janelas abertas.', 'warning')
        return redirect(url_for('admin.windows'))
    window.status = 'closed'
    window.close_at = window.close_at or datetime.utcnow()
    audit('close_window', 'FillingWindow', window.id, {'year': window.year})
    db.session.commit()
    flash(f'Janela {window.year} encerrada.', 'success')
    return redirect(url_for('admin.windows'))


@admin_bp.route('/janela/<int:id>')
@login_required
@admin_required
def windows_detail(id):
    window = db.session.get(FillingWindow, id) or abort(404)
    doctors = User.query.filter_by(role='medico', active=True).order_by(User.name).all()
    confirmed_ids = {
        c.doctor_id
        for c in DoctorWindowConfirmation.query.filter_by(window_id=id).all()
    }
    return render_template('admin/window/detail.html',
                           window=window, doctors=doctors, confirmed_ids=confirmed_ids)


@admin_bp.route('/janela/<int:window_id>/desbloquear/<int:doctor_id>', methods=['POST'])
@login_required
@admin_required
def windows_unlock(window_id, doctor_id):
    conf = DoctorWindowConfirmation.query.filter_by(
        window_id=window_id, doctor_id=doctor_id
    ).first()
    if conf:
        db.session.delete(conf)
        audit('unlock_doctor_window', 'DoctorWindowConfirmation', conf.id,
              {'doctor_id': doctor_id, 'window_id': window_id})
        db.session.commit()
        flash('Médico desbloqueado para edição.', 'success')
    return redirect(url_for('admin.windows_detail', id=window_id))


# ── Geração e Publicação da Escala ────────────────────────────────────────────

@admin_bp.route('/janela/<int:id>/gerar', methods=['POST'])
@login_required
@admin_required
def schedule_generate(id):
    window = db.session.get(FillingWindow, id) or abort(404)
    if window.status not in ('closed',):
        flash('A janela precisa estar encerrada antes de gerar a escala.', 'warning')
        return redirect(url_for('admin.windows'))
    from app.services.scheduler import generate_schedule
    result = generate_schedule(id)
    audit('generate_schedule', 'FillingWindow', id, {
        'total': result['total_slots'],
        'routine': result['routine_slots'],
        'generated': result['generated_slots'],
        'uncovered': len(result['uncovered_slots']),
    })
    flash(
        f"Escala gerada: {result['routine_slots']} por rotina, "
        f"{result['generated_slots']} distribuídas, "
        f"{len(result['uncovered_slots'])} sem cobertura.",
        'success' if not result['uncovered_slots'] else 'warning',
    )
    return redirect(url_for('admin.schedule_review', id=id))


@admin_bp.route('/janela/<int:id>/escala')
@login_required
@admin_required
def schedule_review(id):
    window = db.session.get(FillingWindow, id) or abort(404)
    from app.services.schedule_view_service import get_schedule_review_context

    month = request.args.get('month', type=int, default=1)
    if month < 1 or month > 12:
        month = 1
    month = default_schedule_month(window, month)

    ctx = get_schedule_review_context(window, month)

    # Dados extras só usados pelos forms de edição do dia
    all_links = DoctorLocationLink.query.filter_by(active=True).all()
    doctors_list = sorted((u for u in ctx['doctors'].values() if u.active), key=lambda u: u.name)
    doctors_list_ids = {u.id for u in doctors_list}
    scale_types_by_location = defaultdict(set)
    for lk in all_links:
        if lk.scale_type:
            scale_types_by_location[lk.location_id].add(lk.scale_type)
    scale_types_by_location = {k: sorted(v) for k, v in scale_types_by_location.items()}

    return render_template('admin/window/schedule.html',
                           window=window, **ctx,
                           doctors_list=doctors_list,
                           doctors_list_ids=doctors_list_ids,
                           scale_types_by_location=scale_types_by_location)


@admin_bp.route('/janela/<int:id>/escala/entradas', methods=['POST'])
@login_required
@admin_required
def schedule_entry_create(id):
    db.session.get(FillingWindow, id) or abort(404)
    entry_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    location_id = request.form.get('location_id', type=int)
    doctor_id = request.form.get('doctor_id', type=int)
    scale_type = (request.form.get('scale_type') or '').strip()
    month = request.form.get('month', type=int, default=1)
    day = request.form.get('day', entry_date.isoformat())

    location = db.session.get(Location, location_id) or abort(404)
    doctor = db.session.get(User, doctor_id) if doctor_id else None
    if not doctor or doctor.role != 'medico':
        flash('Selecione um médico válido.', 'danger')
        return redirect(url_for('admin.schedule_review', id=id, month=month, day=day))

    entry = Schedule(window_id=id, date=entry_date, location_id=location_id,
                      doctor_id=doctor_id, scale_type=scale_type or None, source='manual')
    db.session.add(entry)
    db.session.flush()
    audit('create_schedule_entry', 'Schedule', entry.id, {
        'window_id': id, 'date': entry_date.isoformat(), 'location_id': location_id,
        'doctor_id': doctor_id, 'scale_type': scale_type or None,
    })
    db.session.commit()
    flash(f'Plantão adicionado: {location.name} — {doctor.name} ({scale_type or "—"}).', 'success')
    return redirect(url_for('admin.schedule_review', id=id, month=month, day=day))


@admin_bp.route('/janela/<int:id>/escala/entradas/<int:entry_id>/editar', methods=['POST'])
@login_required
@admin_required
def schedule_entry_update(id, entry_id):
    entry = Schedule.query.filter_by(id=entry_id, window_id=id).first() or abort(404)
    location_id = request.form.get('location_id', type=int)
    doctor_id = request.form.get('doctor_id', type=int)
    scale_type = (request.form.get('scale_type') or '').strip()
    month = request.form.get('month', type=int, default=1)
    day = request.form.get('day', entry.date.isoformat())

    location = db.session.get(Location, location_id) or abort(404)
    doctor = db.session.get(User, doctor_id) if doctor_id else None
    if not doctor or doctor.role != 'medico':
        flash('Selecione um médico válido.', 'danger')
        return redirect(url_for('admin.schedule_review', id=id, month=month, day=day))

    before = {'location_id': entry.location_id, 'doctor_id': entry.doctor_id, 'scale_type': entry.scale_type}
    entry.location_id = location_id
    entry.doctor_id = doctor_id
    entry.scale_type = scale_type or None
    audit('update_schedule_entry', 'Schedule', entry.id, {
        'before': before,
        'after': {'location_id': location_id, 'doctor_id': doctor_id, 'scale_type': scale_type or None},
    })
    db.session.commit()
    flash(f'Plantão atualizado: {location.name} — {doctor.name} ({scale_type or "—"}).', 'success')
    return redirect(url_for('admin.schedule_review', id=id, month=month, day=day))


@admin_bp.route('/janela/<int:id>/escala/entradas/<int:entry_id>/excluir', methods=['POST'])
@login_required
@admin_required
def schedule_entry_delete(id, entry_id):
    entry = Schedule.query.filter_by(id=entry_id, window_id=id).first() or abort(404)
    month = request.form.get('month', type=int, default=1)
    day = request.form.get('day', entry.date.isoformat())

    from app.models.swap import ScheduleSwap
    if ScheduleSwap.query.filter_by(schedule_id=entry.id).first():
        flash('Não é possível excluir: este plantão possui solicitação(ões) de troca vinculada(s).', 'warning')
        return redirect(url_for('admin.schedule_review', id=id, month=month, day=day))

    audit('delete_schedule_entry', 'Schedule', entry.id, {
        'window_id': id, 'date': entry.date.isoformat(), 'location_id': entry.location_id,
        'doctor_id': entry.doctor_id, 'scale_type': entry.scale_type,
    })
    db.session.delete(entry)
    db.session.commit()
    flash('Plantão removido.', 'success')
    return redirect(url_for('admin.schedule_review', id=id, month=month, day=day))


@admin_bp.route('/janela/<int:id>/escala/excecoes', methods=['POST'])
@login_required
@admin_required
def schedule_exception_create(id):
    db.session.get(FillingWindow, id) or abort(404)
    exc_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    location_id = request.form.get('location_id', type=int)
    month = request.form.get('month', type=int, default=1)
    location = db.session.get(Location, location_id) or abort(404)

    existing = CoverageException.query.filter_by(
        window_id=id, date=exc_date, location_id=location_id).first()
    if existing:
        flash(f'{location.name} já está marcado como sem escala prevista em {exc_date.strftime("%d/%m")}.', 'info')
    else:
        exc = CoverageException(window_id=id, location_id=location_id,
                                 date=exc_date, created_by=current_user.id)
        db.session.add(exc)
        db.session.flush()
        audit('create_coverage_exception', 'CoverageException', exc.id,
              {'window_id': id, 'date': exc_date.isoformat(), 'location_id': location_id})
        db.session.commit()
        flash(f'{location.name}: sem escala prevista em {exc_date.strftime("%d/%m")}.', 'success')
    return redirect(url_for('admin.schedule_review', id=id, month=month))


@admin_bp.route('/janela/<int:id>/escala/excecoes/<int:exc_id>/excluir', methods=['POST'])
@login_required
@admin_required
def schedule_exception_delete(id, exc_id):
    exc = db.session.get(CoverageException, exc_id) or abort(404)
    if exc.window_id != id:
        abort(404)
    month = request.form.get('month', type=int, default=1)
    audit('delete_coverage_exception', 'CoverageException', exc.id,
          {'window_id': id, 'date': exc.date.isoformat(), 'location_id': exc.location_id})
    db.session.delete(exc)
    db.session.commit()
    flash('Marcação de "sem escala prevista" removida.', 'info')
    return redirect(url_for('admin.schedule_review', id=id, month=month))


@admin_bp.route('/janela/<int:id>/escala/excecoes/lote', methods=['POST'])
@login_required
@admin_required
def schedule_exception_bulk(id):
    window = db.session.get(FillingWindow, id) or abort(404)
    month = request.form.get('month', type=int, default=1)
    if month < 1 or month > 12:
        month = 1
    start_m = date_type(window.year, month, 1)
    end_m = _last_day(window.year, month)

    entries = (Schedule.query
               .filter(Schedule.window_id == id,
                       Schedule.date >= start_m, Schedule.date <= end_m)
               .all())
    covered_locations_by_date = defaultdict(set)
    for e in entries:
        covered_locations_by_date[e.date].add(e.location_id)

    existing = {(e.date, e.location_id) for e in
                CoverageException.query.filter(
                    CoverageException.window_id == id,
                    CoverageException.date >= start_m,
                    CoverageException.date <= end_m).all()}

    locations = Location.query.filter_by(active=True).all()
    created = 0
    d = start_m
    while d <= end_m:
        for loc in locations:
            if loc.id not in covered_locations_by_date.get(d, set()) and (d, loc.id) not in existing:
                db.session.add(CoverageException(window_id=id, location_id=loc.id,
                                                   date=d, created_by=current_user.id))
                created += 1
        d += timedelta(days=1)

    if created:
        audit('bulk_create_coverage_exceptions', 'FillingWindow', id, {'month': month, 'count': created})
        db.session.commit()
        flash(f'{created} marcação(ões) de "sem escala prevista" criadas.', 'success')
    else:
        flash('Nenhum local/dia sem cobertura encontrado para marcar neste mês.', 'info')
    return redirect(url_for('admin.schedule_review', id=id, month=month))


@admin_bp.route('/janela/<int:id>/escala/aceites', methods=['POST'])
@login_required
@admin_required
def coverage_acceptance_create(id):
    db.session.get(FillingWindow, id) or abort(404)
    acc_date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
    location_id = request.form.get('location_id', type=int)
    scale_type = (request.form.get('scale_type') or '').strip() or None
    justification = (request.form.get('justification') or '').strip()
    month = request.form.get('month', type=int, default=1)
    day = request.form.get('day', acc_date.isoformat())
    location = db.session.get(Location, location_id) or abort(404)

    if not justification:
        flash('Informe uma justificativa para aceitar a lacuna.', 'danger')
        return redirect(url_for('admin.schedule_review', id=id, month=month, day=day))

    existing = CoverageAcceptance.query.filter_by(
        window_id=id, date=acc_date, location_id=location_id, scale_type=scale_type).first()
    if existing:
        flash('Esta lacuna já foi aceita.', 'info')
    else:
        acc = CoverageAcceptance(window_id=id, location_id=location_id, date=acc_date,
                                  scale_type=scale_type, justification=justification,
                                  created_by=current_user.id)
        db.session.add(acc)
        db.session.flush()
        audit('create_coverage_acceptance', 'CoverageAcceptance', acc.id, {
            'window_id': id, 'date': acc_date.isoformat(), 'location_id': location_id,
            'scale_type': scale_type, 'justification': justification,
        })
        db.session.commit()
        flash(f'Lacuna aceita: {location.name} — {scale_type or "sem tipo"}.', 'success')
    return redirect(url_for('admin.schedule_review', id=id, month=month, day=day))


@admin_bp.route('/janela/<int:id>/escala/aceites/<int:acc_id>/excluir', methods=['POST'])
@login_required
@admin_required
def coverage_acceptance_delete(id, acc_id):
    acc = db.session.get(CoverageAcceptance, acc_id) or abort(404)
    if acc.window_id != id:
        abort(404)
    month = request.form.get('month', type=int, default=1)
    day = request.form.get('day', acc.date.isoformat())
    audit('delete_coverage_acceptance', 'CoverageAcceptance', acc.id, {
        'window_id': id, 'date': acc.date.isoformat(), 'location_id': acc.location_id,
        'scale_type': acc.scale_type, 'justification': acc.justification,
    })
    db.session.delete(acc)
    db.session.commit()
    flash('Aceite removido — lacuna volta a contar em "Sem cobertura".', 'info')
    return redirect(url_for('admin.schedule_review', id=id, month=month, day=day))


@admin_bp.route('/janela/<int:id>/aprovar', methods=['POST'])
@login_required
@admin_required
def schedule_approve(id):
    window = db.session.get(FillingWindow, id) or abort(404)
    from app.models.schedule import Schedule
    Schedule.query.filter_by(window_id=id, status='draft').update({'status': 'published'})
    window.status = 'published'
    audit('approve_schedule', 'FillingWindow', id, {})
    db.session.commit()
    flash(f'Escala {window.year} publicada. Médicos já podem visualizar.', 'success')
    return redirect(url_for('admin.schedule_review', id=id))


def _last_day(year: int, month: int):
    from datetime import date as date_type
    import calendar
    return date_type(year, month, calendar.monthrange(year, month)[1])


# ── Trocas (Admin) ────────────────────────────────────────────────────────────

@admin_bp.route('/trocas')
@login_required
@admin_required
def swaps():
    from app.models.swap import ScheduleSwap
    from app.models.location import Location
    from app.models.user import User as UserModel
    from app.services.swap_service import build_swap_view_data

    status_filter = request.args.get('status', 'open')
    query = ScheduleSwap.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    swaps = query.order_by(ScheduleSwap.requested_at.desc()).all()

    locations = {l.id: l for l in Location.query.all()}
    doctors = {u.id: u for u in UserModel.query.all()}

    eligible_by_swap, eligible_names_by_swap, days_open_by_swap = build_swap_view_data(swaps, doctors)

    return render_template('admin/swaps/list.html',
                           swaps=swaps, locations=locations, doctors=doctors,
                           status_filter=status_filter,
                           eligible_by_swap=eligible_by_swap,
                           eligible_names_by_swap=eligible_names_by_swap,
                           days_open_by_swap=days_open_by_swap)


@admin_bp.route('/trocas/<int:swap_id>/efetivar', methods=['POST'])
@login_required
@admin_required
def swaps_force(swap_id):
    from app.services.swap_service import admin_force_swap
    target_doctor_id = request.form.get('target_doctor_id', type=int)
    if not target_doctor_id:
        flash('Selecione um médico para efetivar a troca.', 'warning')
        return redirect(url_for('admin.swaps'))
    try:
        admin_force_swap(swap_id, target_doctor_id)
        audit('admin_force_swap', 'ScheduleSwap', swap_id,
              {'target_doctor_id': target_doctor_id})
        flash('Troca efetivada pelo administrador.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    return redirect(url_for('admin.swaps'))


# ── Dashboard KPIs ────────────────────────────────────────────────────────────

@admin_bp.route('/kpis')
@login_required
@admin_required
def kpis():
    from app.services.kpi_service import get_dashboard_data
    from datetime import datetime as dt

    windows = FillingWindow.query.filter_by(status='published').order_by(FillingWindow.year.desc()).all()
    window_id = request.args.get('window_id', type=int)
    month = request.args.get('month', type=int, default=dt.now().month)

    if not window_id and windows:
        window_id = windows[0].id
    if month < 1 or month > 12:
        month = 1

    window = db.session.get(FillingWindow, window_id) if window_id else None
    data = get_dashboard_data(window_id, month) if window_id else {}

    month_names = ['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
    return render_template('admin/kpis.html',
                           windows=windows, window=window, window_id=window_id,
                           month=month, month_names=month_names, data=data)

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.user import User
from app.models.location import Location, DoctorLocationLink
from app.models.schedule import FillingWindow, DoctorWindowConfirmation
from app.utils.decorators import admin_required
from app.utils.audit import log as audit

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    from app.models.swap import ScheduleSwap
    total_doctors = User.query.filter_by(role='medico', active=True).count()
    total_locations = Location.query.filter_by(active=True).count()
    total_swaps = ScheduleSwap.query.filter_by(status='open').count()
    return render_template('admin/dashboard.html',
                           total_doctors=total_doctors,
                           total_locations=total_locations,
                           total_swaps=total_swaps)


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
    return render_template('admin/doctors/form.html', form=form, title='Editar Médico', doctor=doctor)


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
            address=form.address.data.strip() or None,
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
    loc = db.session.get(Location, id) or abort(404)
    form = LocationForm(obj=loc)
    if form.validate_on_submit():
        loc.name = form.name.data.strip()
        loc.address = form.address.data.strip() or None
        loc.scale_type = form.scale_type.data.strip() or None
        audit('edit_location', 'Location', loc.id, {'name': loc.name})
        db.session.commit()
        flash(f'Local "{loc.name}" atualizado.', 'success')
        return redirect(url_for('admin.locations'))
    return render_template('admin/locations/form.html', form=form, title='Editar Local', location=loc)


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


# ── Vínculos ──────────────────────────────────────────────────────────────────

@admin_bp.route('/vinculos')
@login_required
@admin_required
def links():
    links = (DoctorLocationLink.query
             .join(User, DoctorLocationLink.doctor_id == User.id)
             .join(Location, DoctorLocationLink.location_id == Location.id)
             .order_by(User.name, Location.name)
             .all())
    return render_template('admin/links/list.html', links=links)


@admin_bp.route('/vinculos/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def links_new():
    from app.forms.admin import DoctorLocationLinkForm
    form = DoctorLocationLinkForm()
    if form.validate_on_submit():
        existing = DoctorLocationLink.query.filter_by(
            doctor_id=form.doctor_id.data,
            location_id=form.location_id.data,
            scale_type=form.scale_type.data.strip() or None,
        ).first()
        if existing:
            flash('Este vínculo já existe.', 'warning')
            return render_template('admin/links/form.html', form=form, title='Novo Vínculo')
        link = DoctorLocationLink(
            doctor_id=form.doctor_id.data,
            location_id=form.location_id.data,
            scale_type=form.scale_type.data.strip() or None,
        )
        db.session.add(link)
        db.session.flush()
        audit('create_link', 'DoctorLocationLink', link.id,
              {'doctor_id': link.doctor_id, 'location_id': link.location_id})
        db.session.commit()
        flash('Vínculo criado com sucesso.', 'success')
        return redirect(url_for('admin.links'))
    return render_template('admin/links/form.html', form=form, title='Novo Vínculo')


@admin_bp.route('/vinculos/<int:id>/toggle', methods=['POST'])
@login_required
@admin_required
def links_toggle(id):
    link = db.session.get(DoctorLocationLink, id) or abort(404)
    link.active = not link.active
    audit('toggle_link', 'DoctorLocationLink', link.id, {'active': link.active})
    db.session.commit()
    status = 'ativado' if link.active else 'desativado'
    flash(f'Vínculo {status}.', 'info')
    return redirect(url_for('admin.links'))


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
    from datetime import date
    window = db.session.get(FillingWindow, id) or abort(404)
    from app.models.schedule import Schedule
    from app.models.location import Location
    from app.models.user import User as UserModel

    month = request.args.get('month', type=int, default=1)
    if month < 1 or month > 12:
        month = 1

    # Entradas do mês selecionado
    entries = (Schedule.query
               .filter_by(window_id=id)
               .filter(
                   Schedule.date >= date(window.year, month, 1),
                   Schedule.date <= _last_day(window.year, month),
               )
               .order_by(Schedule.date, Schedule.location_id)
               .all())

    # Stats gerais
    from app.models.schedule import Schedule as Sch
    stats = {
        'total':     Sch.query.filter_by(window_id=id).count(),
        'routine':   Sch.query.filter_by(window_id=id, source='routine').count(),
        'generated': Sch.query.filter_by(window_id=id, source='generated').count(),
    }

    # Lacunas: (location, scale_type) × (data) sem cobertura
    from app.models.location import DoctorLocationLink
    from collections import defaultdict
    from datetime import date as date_type, timedelta
    all_links = DoctorLocationLink.query.filter_by(active=True).all()
    loc_keys = {(lk.location_id, lk.scale_type) for lk in all_links}
    start_m = date_type(window.year, month, 1)
    end_m = _last_day(window.year, month)
    covered = {(e.date, e.location_id, e.scale_type) for e in entries}
    uncovered = []
    d = start_m
    while d <= end_m:
        for (loc_id, sc) in loc_keys:
            if (d, loc_id, sc) not in covered:
                uncovered.append({'date': d, 'location_id': loc_id, 'scale_type': sc})
        d += timedelta(days=1)

    locations = {l.id: l for l in Location.query.all()}
    doctors = {u.id: u for u in UserModel.query.filter_by(role='medico').all()}
    month_names = ['','Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']

    return render_template('admin/window/schedule.html',
                           window=window, entries=entries, stats=stats,
                           uncovered=uncovered, locations=locations, doctors=doctors,
                           month=month, month_names=month_names)


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
    from app.models.swap import ScheduleSwap, SwapNotification
    from app.models.location import Location
    from app.models.user import User as UserModel
    from app.models.schedule import Schedule

    status_filter = request.args.get('status', 'open')
    query = ScheduleSwap.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    swaps = query.order_by(ScheduleSwap.requested_at.desc()).all()

    locations = {l.id: l for l in Location.query.all()}
    doctors = {u.id: u for u in UserModel.query.all()}

    return render_template('admin/swaps/list.html',
                           swaps=swaps, locations=locations, doctors=doctors,
                           status_filter=status_filter)


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

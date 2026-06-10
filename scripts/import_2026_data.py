"""Importa os dados da planilha "ESCALA SOBREAVISO 2025" (abas JUN_26..DEZ_26)
para a janela de preenchimento de 2026 (FillingWindow id=5).

Faz, em uma única transação:
  - remove dados de teste (médico de teste, locations e vínculos de teste)
  - cria as 3 locations reais (Hospital Santa Rita, Hospital Vitória Apart, CIAS)
  - cria os médicos novos identificados na planilha (login=primeironome.sobrenome,
    senha="senha", e-mail e CRM pendentes)
  - importa os 1058 registros de escala (Schedule, source='manual', status='draft')
  - deriva e cria os vínculos (DoctorLocationLink) a partir das combinações
    (médico, local, tipo de escala) observadas na escala importada
  - importa os feriados (Holiday) e as restrições por médico (DoctorRestriction)
    extraídos da coluna "Restrições e feriados"
"""
import csv
import os
import re
import unicodedata
from collections import defaultdict
from datetime import date

from app import create_app
from app.extensions import db
from app.models import User, Location, DoctorLocationLink, Schedule, Holiday, DoctorRestriction

SHEETS_DIR = '/tmp/sheets'
WINDOW_ID = 5
MONTH_FILES = ['JUN_26', 'JUL_26', 'AGO_26', 'SET_26', 'OUT_26', 'NOV_26', 'DEZ_26']

MONTHS = {'jan': 1, 'fev': 2, 'mar': 3, 'abr': 4, 'mai': 5, 'jun': 6,
          'jul': 7, 'ago': 8, 'set': 9, 'out': 10, 'nov': 11, 'dez': 12}

DOCTORS = [
    'Camila Castelan', 'Carlos Andre', 'Cristina Madeira', 'Eloisa Spinasse',
    'Giuliano Sandri', 'Kamila Braun', 'Luciano Favarato', 'Ludimila Vargas',
    'Mariana Dutra', 'Murilo Hosken', 'Márcia Porto', 'Rodrigo França', 'Thais Duailibi',
]

NAME_NORMALIZE = {
    'Eloísa Spinassé': 'Eloisa Spinasse',
    'Ludmila Vargas': 'Ludimila Vargas',
    'Thaís Duailibi': 'Thais Duailibi',
}

FIRST_NAME_MAP = {
    'Eloisa': 'Eloisa Spinasse',
    'Kamila': 'Kamila Braun',
    'Murilo': 'Murilo Hosken',
    'Márcia': 'Márcia Porto',
    'Rodrigo': 'Rodrigo França',
    'Mariana': 'Mariana Dutra',
    'Cristina': 'Cristina Madeira',
}

HOLIDAY_NAMES = {
    'CORPUS CHRISTI', 'INDEPENDÊNCIA', 'NOSSA SENHORA', 'CONSCIÊNCIA NEGRA',
    'NATAL', 'FINADOS', 'PROC. REPÚBLICA', 'REVEILLON', 'ARACRUZ', 'VITÓRIA', 'DIA DOS PAIS',
}

# (coluna, location, scale_type)
COLUMN_CONFIG = [
    (1, 'Hospital Santa Rita', 'P1'),
    (2, 'Hospital Santa Rita', 'P2'),
    (3, 'Hospital Vitória Apart', 'P1'),
    (4, 'Hospital Vitória Apart', 'P2'),
    (5, 'Hospital Santa Rita', 'Doppler'),
]


def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def make_login(name):
    parts = name.split()
    return strip_accents(f'{parts[0]}.{parts[-1]}').lower()


def resolve_doctor_token(token):
    token = token.strip().rstrip('*').strip()
    if not token:
        return None
    if token in NAME_NORMALIZE:
        return NAME_NORMALIZE[token]
    if token in DOCTORS:
        return token
    return FIRST_NAME_MAP.get(token)


def parse_date(date_str, year=2026):
    m = re.match(r'(\d{1,2})/(\w+)', date_str.strip())
    if not m:
        return None
    day, mon = m.groups()
    mon_num = MONTHS.get(mon.lower()[:3])
    if not mon_num:
        return None
    try:
        return date(year, mon_num, int(day))
    except ValueError:
        return None


def parse_sheets():
    schedule_entries = []  # (date, location_name, scale_type, doctor_name)
    link_keys = set()
    holiday_set = set()  # (date, name)
    restriction_map = defaultdict(list)  # (doctor_name, date) -> [reason, ...]
    skipped = []

    for fname in MONTH_FILES:
        path = os.path.join(SHEETS_DIR, f'{fname}.csv')
        with open(path, newline='', encoding='utf-8') as f:
            rows = list(csv.reader(f))
        for row in rows[2:]:
            if not row or not row[0].strip():
                continue
            d = parse_date(row[0])
            if not d:
                continue

            # P1/P2 HSRC, P1/P2 VAH, Doppler HSRC
            for col_idx, loc_name, scale in COLUMN_CONFIG:
                val = row[col_idx].strip() if col_idx < len(row) else ''
                if not val:
                    continue
                for piece in re.split(r'[/,]', val):
                    doctor_name = resolve_doctor_token(piece)
                    if doctor_name is None:
                        piece_clean = piece.strip().rstrip('*').strip()
                        if piece_clean:
                            skipped.append((fname, row[0], col_idx, piece_clean))
                        continue
                    schedule_entries.append((d, loc_name, scale, doctor_name))
                    link_keys.add((doctor_name, loc_name, scale))

            # CIAS
            val = row[6].strip() if 6 < len(row) else ''
            val_clean = val.rstrip('*').strip()
            if val_clean and val_clean.upper() != 'GRUPO C':
                pieces = [p.strip() for p in re.split(r'[/,]', val_clean) if p.strip()]
                for i, piece in enumerate(pieces):
                    doctor_name = resolve_doctor_token(piece)
                    scale = f'P{i + 1}'
                    if doctor_name is None:
                        skipped.append((fname, row[0], 6, piece.strip()))
                        continue
                    schedule_entries.append((d, 'CIAS', scale, doctor_name))
                    link_keys.add((doctor_name, 'CIAS', scale))

            # Restrições e feriados
            for c in range(7, len(row)):
                val = row[c].strip()
                if not val:
                    continue
                val_clean = val.rstrip('*').strip()
                if val_clean.upper() in HOLIDAY_NAMES:
                    holiday_set.add((d, val_clean.upper()))
                    continue
                if val in NAME_NORMALIZE:
                    doctor_name = NAME_NORMALIZE[val]
                elif val in DOCTORS:
                    doctor_name = val
                else:
                    first_word = val.split()[0].rstrip('*')
                    doctor_name = FIRST_NAME_MAP.get(first_word)
                if doctor_name:
                    restriction_map[(doctor_name, d)].append(val_clean)
                else:
                    skipped.append((fname, row[0], c, val_clean))

    return schedule_entries, link_keys, holiday_set, restriction_map, skipped


def main():
    app = create_app()
    with app.app_context():
        try:
            # ---- Phase 1: limpar dados de teste ----
            DoctorLocationLink.query.delete()
            User.query.filter_by(id=12).delete()
            Location.query.delete()
            db.session.flush()

            # ---- Phase 2: locations ----
            locations = {
                'Hospital Santa Rita': Location(name='Hospital Santa Rita', active=True),
                'Hospital Vitória Apart': Location(name='Hospital Vitória Apart', active=True),
                'CIAS': Location(name='CIAS', active=True),
            }
            db.session.add_all(locations.values())
            db.session.flush()

            # ---- Phase 3: médicos ----
            doctors = {'Márcia Porto': db.session.get(User, 11)}
            for name in DOCTORS:
                if name == 'Márcia Porto':
                    continue
                login = make_login(name)
                user = User(
                    name=name, crm=None, login=login,
                    email=f'{login}@pendente.escalamedica.local',
                    role='medico', active=True,
                )
                user.set_password('senha')
                db.session.add(user)
                doctors[name] = user
            db.session.flush()

            # ---- Phase 4: parse das planilhas mensais ----
            schedule_entries, link_keys, holiday_set, restriction_map, skipped = parse_sheets()

            # ---- Phase 5: vínculos ----
            for doctor_name, loc_name, scale in sorted(link_keys):
                db.session.add(DoctorLocationLink(
                    doctor_id=doctors[doctor_name].id,
                    location_id=locations[loc_name].id,
                    scale_type=scale, active=True,
                ))

            # ---- Phase 6: escala ----
            for d, loc_name, scale, doctor_name in schedule_entries:
                db.session.add(Schedule(
                    window_id=WINDOW_ID, date=d,
                    location_id=locations[loc_name].id, scale_type=scale,
                    doctor_id=doctors[doctor_name].id,
                    source='manual', status='draft',
                ))

            # ---- Phase 7: feriados ----
            for d, name in sorted(holiday_set):
                db.session.add(Holiday(window_id=WINDOW_ID, date=d, name=name))

            # ---- Phase 8: restrições ----
            for (doctor_name, d), reasons in sorted(restriction_map.items(), key=lambda kv: (kv[0][0], kv[0][1])):
                db.session.add(DoctorRestriction(
                    doctor_id=doctors[doctor_name].id, window_id=WINDOW_ID,
                    restricted_date=d, reason='; '.join(reasons),
                ))

            db.session.commit()

            print('OK — importação concluída.')
            print(f'  Locations criadas: {len(locations)}')
            print(f'  Médicos novos criados: {len(DOCTORS) - 1}')
            print(f'  Vínculos criados: {len(link_keys)}')
            print(f'  Registros de escala: {len(schedule_entries)}')
            print(f'  Feriados: {len(holiday_set)}')
            print(f'  Restrições: {len(restriction_map)}')
            print(f'  Tokens ignorados (esperado: FECHAMENTO EM SETEMBRO, OUTUBRO): {skipped}')

        except Exception:
            db.session.rollback()
            raise


if __name__ == '__main__':
    main()

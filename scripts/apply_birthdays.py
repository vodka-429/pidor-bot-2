"""
Применяет дни рождения к БД из локального JSON-файла.

Файл `scripts/birthdays.local.json` лежит в .gitignore, чтобы tg_id и ДР
реальных людей не утекали в публичный репозиторий. Сначала миграция
`p1q2r3s4t5u6_add_birthday_to_tguser.py` добавляет колонки, потом этот
скрипт заливает данные. Идемпотентный — можно гонять сколько угодно раз.

Формат `birthdays.local.json`:
    {
        "105825137": {"month": 6, "day": 17, "name": "kanst9"},
        "5627861754": {"month": null, "day": null, "name": "divnitydat"},
        ...
    }

Записи с null для month или day игнорируются — это плейсхолдеры под
заполнение в будущем.

Запуск:
    DATABASE_URL=... python scripts/apply_birthdays.py [--file path] [--dry-run]
"""
import argparse
import json
import os
import sys
from typing import Dict

from sqlmodel import Session, create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'birthdays.local.json')


def load_file(path: str) -> Dict[int, tuple[int, int]]:
    if not os.path.exists(path):
        print(f'Файл не найден: {path}', file=sys.stderr)
        sys.exit(1)

    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    result: Dict[int, tuple[int, int]] = {}
    for tg_id_str, entry in raw.items():
        try:
            tg_id = int(tg_id_str)
        except ValueError:
            print(f'  Пропускаю некорректный tg_id: {tg_id_str!r}', file=sys.stderr)
            continue
        month = entry.get('month')
        day = entry.get('day')
        if month is None or day is None:
            continue  # плейсхолдер
        result[tg_id] = (int(month), int(day))
    return result


def apply(birthdays: Dict[int, tuple[int, int]], dry_run: bool) -> None:
    db_url = os.environ['DATABASE_URL']
    engine = create_engine(db_url)
    updated = 0
    not_found = []
    with Session(engine) as session:
        for tg_id, (month, day) in birthdays.items():
            stmt = text(
                'UPDATE tguser SET birth_month = :m, birth_day = :d '
                'WHERE tg_id = :tg_id'
            )
            if dry_run:
                # Проверяем существование без записи
                check = session.exec(
                    text('SELECT id FROM tguser WHERE tg_id = :tg_id'),
                    params={'tg_id': tg_id},
                ).first()
                if check is None:
                    not_found.append(tg_id)
                else:
                    print(f'  [dry-run] UPDATE tg_id={tg_id} → {day:02d}.{month:02d}')
                    updated += 1
            else:
                result = session.exec(stmt, params={'m': month, 'd': day, 'tg_id': tg_id})
                if result.rowcount == 0:
                    not_found.append(tg_id)
                else:
                    updated += 1
        if not dry_run:
            session.commit()

    print(f'\n{"[dry-run] " if dry_run else ""}Обновлено: {updated}')
    if not_found:
        print(f'Не найдены в БД ({len(not_found)}): {not_found}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', default=DEFAULT_FILE,
                        help=f'Путь к JSON с ДР (по умолчанию: {DEFAULT_FILE})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Показать что будет сделано, но не писать в БД.')
    args = parser.parse_args()

    birthdays = load_file(args.file)
    if not birthdays:
        print('В файле нет заполненных ДР (только плейсхолдеры или пусто).', file=sys.stderr)
        sys.exit(0)

    print(f'Применяю {len(birthdays)} ДР из {args.file}...', file=sys.stderr)
    apply(birthdays, dry_run=args.dry_run)


if __name__ == '__main__':
    main()

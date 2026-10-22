"""Local Excel exports with exclusive publication and reversible text escaping.

All strings (including headers) double backslashes and escape XML-invalid code
points as \\uXXXX. TEXT_ENCODING marks the workbook description; _restore_text
decodes marked workbooks once, left to right. Unmarked legacy files must not be
decoded. Unicode and blanks are retained; formulas are text, never executed.
Excel's text limit is checked after escaping: oversized values raise, not truncate.
"""

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import Workbook


TEXT_ENCODING = 'tiktok_text_escape:backslash_u_v1'
ID_COLUMNS = {'Comment ID', 'Video ID', 'id_perfil', 'id_post'}


def _excel_text(value):
    # Escape backslashes too, so visible XML escapes can be reversed unambiguously.
    value = value.replace('\\', '\\\\')
    value = ''.join(
        f'\\u{ord(char):04X}'
        if (ord(char) < 32 and char not in '\t\n\r')
        or 0xD800 <= ord(char) <= 0xDFFF or ord(char) in (0xFFFE, 0xFFFF)
        else char for char in value
    )
    if len(value.encode('utf-16-le')) // 2 > 32767:
        raise ValueError('Texto superior al limite Excel de 32767 caracteres; no se truncara.')
    return value


def _restore_text(value):
    if not isinstance(value, str):
        return value
    return re.sub(r'\\(\\|u[0-9A-F]{4})',
                  lambda match: '\\' if match[1] == '\\' else chr(int(match[1][1:], 16)), value)


def write_workbook(destination, sheets):
    """Write a new workbook, never replacing a path; file-like objects are supported."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.description = TEXT_ENCODING
    if not sheets:
        raise ValueError('Se requiere al menos una hoja.')
    for name, frame in sheets.items():
        sheet = workbook.create_sheet(name)
        for row_index, row in enumerate([list(frame.columns), *frame.itertuples(index=False, name=None)]):
            sheet.append([None] * len(row))
            for column, value in enumerate(row, 1):
                cell = sheet.cell(sheet.max_row, column)
                if row_index and frame.columns[column - 1] in ID_COLUMNS and value is not None and not pd.isna(value):
                    if isinstance(value, float):
                        raise ValueError('ID flotante no fiable; use identificadores de texto.')
                    value = str(value)
                if isinstance(value, str):
                    cell.value = _excel_text(value)
                    cell.data_type = 's'
                elif value is None or pd.isna(value):
                    cell.value = None
                else:
                    cell.value = value
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
    if hasattr(destination, 'write'):
        try:
            workbook.save(destination)
        finally:
            workbook.close()
        return destination
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.excel-', suffix='.xlsx', dir=destination.parent)
    os.close(fd)
    try:
        workbook.save(temporary)
        # Hard-link publication is atomic and fails if another writer won the name.
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)
        workbook.close()
    return destination


def _safe_user(profile):
    name = str(profile.get('id_perfil', 'usuario')).strip().lstrip('@')
    name = re.sub(r'[^A-Za-z0-9_.-]', '_', name).strip(' .')[:80]
    if not name or name.upper().split('.')[0] in {
        'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
        *(f'LPT{i}' for i in range(1, 10)),
    }:
        name = 'usuario_' + name
    return name


def _stamp(timestamp=None):
    if timestamp is None:
        timestamp = datetime.now()
    if isinstance(timestamp, datetime):
        return timestamp.strftime('%Y%m%d_%H%M%S_%f')
    result = re.sub(r'[^A-Za-z0-9_-]', '_', str(timestamp))
    if not result:
        raise ValueError('Timestamp vacio.')
    return result


def _write_unique(output_dir, stem, sheets):
    output_dir = Path(output_dir)
    suffix = 0
    while True:
        path = output_dir / f'{stem}{"_" + str(suffix) if suffix else ""}.xlsx'
        try:
            return write_workbook(path, sheets)
        except FileExistsError:
            suffix += 1


def export_raw(profile, posts, comments, output_dir, timestamp=None):
    """Export raw records with stable principal columns and all optional fields."""
    user, stamp = _safe_user(profile), _stamp(timestamp)
    specifications = {
        'perfil': ([profile], ['id_perfil', 'Bio', 'Followers', 'Following', 'Likes']),
        'posts': (posts, ['Video Links', 'Video ID', 'Views', 'id_post', 'Likes', 'Comments',
                          'Shares', 'Saves', 'Metrics Error', 'Comments Collected',
                          'Comments Status', 'Comments Error', 'id_perfil']),
        'comentarios': (comments, ['Video Links', 'Comment ID', 'Author Handle',
                                   'Author', 'Comment Text', 'Comment Likes', 'Video ID', 'id_perfil']),
    }
    frames = {}
    for key, (rows, principal) in specifications.items():
        text_rows = []
        for row in rows:
            record = dict(row)
            for name in ID_COLUMNS & record.keys():
                value = record[name]
                if value is not None and not pd.isna(value):
                    if isinstance(value, float):
                        raise ValueError('ID flotante no fiable; use identificadores de texto.')
                    record[name] = str(value)
            text_rows.append(record)
        frame = pd.DataFrame(text_rows)
        columns = principal + [name for name in frame.columns if name not in principal]
        frames[key] = frame.reindex(columns=columns)
    # Reserve one common suffix for the three filenames, including repeated timestamps.
    output_dir = Path(output_dir)
    suffix = 0
    while True:
        token = stamp + (f'_{suffix}' if suffix else '')
        paths = {key: output_dir / f'{user}_{"post" if key == "posts" else key}_{token}.xlsx'
                 for key in frames}
        if any(path.exists() for path in paths.values()):
            suffix += 1
            continue
        written = []
        try:
            for key, path in paths.items():
                write_workbook(path, {key: frames[key]})
                written.append(path)
            return paths
        except FileExistsError:
            for path in written:
                path.unlink()
            suffix += 1
        except Exception:
            for path in written:
                path.unlink()
            raise

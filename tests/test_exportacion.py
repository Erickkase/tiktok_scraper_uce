import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from exportacion import TEXT_ENCODING, _restore_text, export_raw, write_workbook


class ExportTests(unittest.TestCase):
    def test_raw_all_fields_reversible_blanks_unicode_formulas_and_no_image_columns(self):
        values = ['', ' ', '=1+1', '+SUM(A1)', '-2+3', '@usuario', 'NA',
                  'Se\u00f1al \U0001f600', '\\ruta\\u0000\x00\ud800\uffff', None]
        fields = {f'campo_{index}': value for index, value in enumerate(values)}
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            paths = export_raw({'id_perfil': 'owner', 'Bio': '', **fields},
                               [{'Video ID': '9000000000000000001', **fields}],
                               [{'Comment ID': '0009000000000000001', **fields}], directory)
            for path in paths.values():
                book = load_workbook(path)
                self.assertEqual(book.properties.description, TEXT_ENCODING)
                sheet = book.active
                headers = {cell.value: cell.column for cell in sheet[1]}
                self.assertFalse(any('image' in name.lower() or 'imagen' in name.lower() for name in headers))
                for name, original in fields.items():
                    cell = sheet.cell(2, headers[name])
                    self.assertNotEqual(cell.data_type, 'f')
                    restored = _restore_text(cell.value)
                    self.assertEqual(restored if restored is not None else '', original or '')
                if 'Comment ID' in headers:
                    self.assertEqual(sheet.cell(2, headers['Comment ID']).value, '0009000000000000001')
                book.close()

    def test_text_cells_unicode_ids_and_formulas(self):
        values = ['=1+1', '+SUM(A1)', '-2+3', '@usuario', 'NA',
                  '123456789012345678901234', 'Se\u00f1al: alegr\u00eda']
        stream = io.BytesIO()
        self.assertIs(write_workbook(stream, {'Datos': pd.DataFrame({'texto': values})}), stream)
        stream.seek(0)
        book = load_workbook(stream)
        cells = list(book['Datos'].iter_rows(min_row=2))
        self.assertEqual([row[0].value for row in cells], values)
        self.assertTrue(all(row[0].data_type == 's' for row in cells))

    def test_xml_controls_visible_reversible_and_no_truncation(self):
        stream = io.BytesIO()
        original = 'a\x00b\x0bc\\u0000\nfin'
        write_workbook(stream, {'Datos': pd.DataFrame({'texto': [original]})})
        stream.seek(0)
        self.assertEqual(load_workbook(stream).active['A2'].value,
                         r'a\u0000b\u000Bc\\u0000' + '\nfin')
        for text in ['x' * 32768, '\U0001f600' * 16384, '\x00' * 6000]:
            with self.assertRaisesRegex(ValueError, '32767'):
                write_workbook(io.BytesIO(), {'Datos': pd.DataFrame({'texto': [text]})})

    def test_exclusive_atomic_and_failure_cleanup(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / 'salida.xlsx'
            frame = pd.DataFrame({'a': ['original']})
            self.assertEqual(write_workbook(path, {'Datos': frame}), path)
            original = path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_workbook(path, {'Datos': frame})
            self.assertEqual(path.read_bytes(), original)
            broken = Path(directory) / 'broken.xlsx'
            with self.assertRaisesRegex(ValueError, '32767'):
                write_workbook(broken, {'Datos': pd.DataFrame({'a': ['x' * 32768]})})
            self.assertFalse(broken.exists())
            self.assertEqual(list(Path(directory).glob('.excel-*')), [])

    def test_numeric_integer_ids_are_text_and_floats_rejected(self):
        stream = io.BytesIO()
        value = 9000000000000000001
        write_workbook(stream, {'Datos': pd.DataFrame({'Comment ID': [value]})})
        stream.seek(0)
        cell = load_workbook(stream).active['A2']
        self.assertEqual(cell.value, str(value))
        self.assertEqual(cell.data_type, 's')
        with self.assertRaisesRegex(ValueError, 'flotante'):
            write_workbook(io.BytesIO(), {'Datos': pd.DataFrame({'Video ID': [float(value)]})})

    def test_raw_three_files_shared_timestamp_and_collision(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            args = ({'id_perfil': '../@CON', 'Bio': '=HYPERLINK("x")'}, [], [], directory)
            first = export_raw(*args, timestamp=datetime(2026, 1, 2, 3, 4, 5, 6))
            second = export_raw(*args, timestamp=datetime(2026, 1, 2, 3, 4, 5, 6))
            self.assertEqual(set(first), {'perfil', 'posts', 'comentarios'})
            self.assertEqual(len(set(first.values()) | set(second.values())), 6)
            self.assertTrue(all(path.parent == Path(directory) for path in first.values()))
            self.assertTrue(all('20260102_030405_000006' in path.name for path in first.values()))
            self.assertTrue(all(path.stem.endswith('_1') for path in second.values()))
            comments = pd.read_excel(first['comentarios'], dtype=str, keep_default_na=False)
            self.assertTrue({'Video Links', 'Comment ID', 'Comment Text', 'Author Handle'} <= set(comments))
            bio = load_workbook(first['perfil']).active['B2']
            self.assertEqual(bio.value, '=HYPERLINK("x")')
            self.assertEqual(bio.data_type, 's')


if __name__ == '__main__':
    unittest.main()

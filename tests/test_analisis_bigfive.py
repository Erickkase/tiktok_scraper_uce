import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from openpyxl import Workbook, load_workbook

from analisis_bigfive import analyze_files, analyze_records, create_engine, export_analysis, main
from exportacion import TEXT_ENCODING, _restore_text, export_raw, write_workbook


HAS_MOTOR = importlib.util.find_spec('motor_bigfive') is not None
URL = 'https://www.tiktok.com/@owner/video/7412345678901234567'
OTHER_URL = 'https://www.tiktok.com/@owner/video/7412345678901234568'


class ContractEngine:
    method = 'test_v1'

    def __init__(self):
        self.calls = []

    def analyze(self, text, source='comentario'):
        from motor_bigfive import empty_results
        self.calls.append((text, source))
        results = empty_results(method=self.method, explanation='Sin evidencia literal.')
        if 'curiosidad' in text:
            results[0].update(senal=True, direccion='positiva', evidencia=['curiosidad'],
                              explicacion='Cita literal.', estado='senal_identificada',
                              referencia='autorreferencia')
        return results


@unittest.skipUnless(HAS_MOTOR, 'motor_bigfive pendiente de otro agente')
class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'id_perfil': '@Owner', 'Bio': '=Mi curiosidad: Se\u00f1al'}
        self.posts = [{'Video Links': URL, 'Comments': 50}]
        self.comments = [
            {'Video Links': URL, 'Comment ID': '9000000000000000001',
             'Author Handle': '@OWNER', 'Comment Text': '  curiosidad propia  ', 'Comment Likes': 99999},
            {'Video Links': URL, 'Comment ID': '9000000000000000002',
             'Author Handle': '@Visitante', 'Comment Text': '=curiosidad ajena'},
            {'Video Links': URL, 'Comment ID': '9000000000000000003',
             'Author Handle': 'VISITANTE', 'Comment Text': 'NA'},
            {'Video Links': URL, 'Comment ID': '9000000000000000004',
             'Author': 'owner', 'Comment Text': 'curiosidad an\u00f3nima'},
            {'Video Links': URL, 'Comment ID': '9000000000000000005',
             'Author Handle': '@Visitante', 'Comment Text': float('nan')},
        ]

    def test_schema_groups_denominators_originals_and_metadata(self):
        engine = ContractEngine()
        result = analyze_records(self.profile, self.posts, self.comments, engine)
        self.assertEqual(list(result), ['Biografia', 'Comentarios_Analizados',
                                       'Resultados_por_Video', 'Resumen_General', 'Metodologia'])
        self.assertEqual(len(result['Biografia']), 5)
        self.assertEqual(len(result['Comentarios_Analizados']), 5)
        self.assertEqual(len(result['Resultados_por_Video']), 15)
        frame = result['Comentarios_Analizados']
        self.assertEqual(frame.iloc[0]['Comment Text'], '  curiosidad propia  ')
        self.assertEqual(frame.iloc[3]['Origen'], 'sin_identificar')
        self.assertEqual(frame.iloc[4]['Estado_Analisis'], 'sin_texto')
        self.assertEqual(len(engine.calls), 5)  # Bio and four nonempty comments.
        self.assertEqual(engine.calls[0], (self.profile['Bio'], 'biografia'))
        summary = result['Resumen_General'].query("Dimension == 'apertura'").set_index('Origen')
        self.assertEqual(summary.loc['audiencia', 'Analizados'], 2)
        self.assertEqual(summary.loc['audiencia', 'Capturados'], 3)
        self.assertEqual(summary.loc['audiencia', 'Proporcion'], .5)
        self.assertEqual(summary.loc['propietario', 'Proporcion'], 1)
        self.assertEqual(summary.loc['sin_identificar', 'Proporcion'], 1)
        self.assertEqual(summary.loc['audiencia', 'Comentarios_Esperados'], 200)
        self.assertEqual(summary.loc['audiencia', 'Comments_Reportados'], 50)
        self.assertTrue((result['Resultados_por_Video']['Comments Status'] == 'parcial').all())
        metadata = result['Metodologia'].set_index('Campo')['Valor']
        self.assertEqual(metadata['Motor'], 'test_v1')
        self.assertIn('sin BFI-2', metadata['Alcance'])
        self.assertIn('no identifica propietario', metadata['Limitaciones'])
        self.assertEqual(len([name for name in metadata.index if name.startswith('Dimension_')]), 5)

    def test_dedup_and_conflicting_comment_ids(self):
        comments = self.comments[:1] * 2
        result = analyze_records(self.profile, self.posts, comments, ContractEngine())
        self.assertEqual(len(result['Comentarios_Analizados']), 1)
        self.assertTrue((result['Resumen_General']['Duplicados_Descartados'] == 1).all())
        posts = self.posts + [{'Video Links': OTHER_URL, 'Comments': 1}]
        conflict = {**comments[0], 'Video Links': OTHER_URL}
        with self.assertRaisesRegex(ValueError, 'distintos videos'):
            analyze_records(self.profile, posts, [comments[0], conflict], ContractEngine())
        with self.assertRaisesRegex(ValueError, 'conflictivo'):
            analyze_records(self.profile, self.posts,
                            [comments[0], {**comments[0], 'Comment Text': 'distinto'}], ContractEngine())

    def test_validation_foreign_profile_video_and_precision(self):
        for comment in [
            {**self.comments[0], 'Video Links': URL.replace('@owner', '@other')},
            {**self.comments[0], 'Video Links': OTHER_URL},
            {**self.comments[0], 'Video Links': URL.replace('www.tiktok.com', 'evil.com')},
            {**self.comments[0], 'Video ID': '99'},
            {**self.comments[0], 'id_perfil': 'other'},
            {**self.comments[0], 'Comment ID': float(9000000000000000001)},
            {**self.comments[0], 'Comment ID': ''},
        ]:
            with self.subTest(comment=comment), self.assertRaises(ValueError):
                analyze_records(self.profile, self.posts, [comment], ContractEngine())

    def test_canonical_video_query_and_case(self):
        comment = {**self.comments[0], 'Video Links': URL.replace('@owner', '@OWNER') + '?lang=es'}
        frame = analyze_records(self.profile, self.posts, [comment], ContractEngine())['Comentarios_Analizados']
        self.assertEqual(frame.iloc[0]['Video Links'], URL)
        self.assertEqual(frame.iloc[0]['Video ID'], '7412345678901234567')

    def test_required_columns_and_legacy_unknown_counts(self):
        with self.assertRaisesRegex(ValueError, 'Bio'):
            analyze_records({'id_perfil': 'owner'}, [], [], ContractEngine())
        with self.assertRaisesRegex(ValueError, 'Comment Text'):
            analyze_records(self.profile, self.posts, [{'Video Links': URL, 'Comment ID': '1'}], ContractEngine())
        result = analyze_records(self.profile, [{'Video Links': URL}], self.comments, ContractEngine())
        self.assertTrue(result['Resultados_por_Video']['Comments_Reportados'].isna().all())
        self.assertTrue(result['Resumen_General']['Comments_Reportados'].isna().all())
        self.assertIn('desconocida', result['Metodologia'].set_index('Campo').loc['Limitaciones', 'Valor'])

    def test_empty_groups_have_null_percentages(self):
        result = analyze_records(self.profile, [], [], ContractEngine())
        self.assertTrue(result['Resumen_General']['Proporcion'].isna().all())
        self.assertEqual(len(result['Resultados_por_Video']), 0)
        self.assertIn('apertura_evidencia', result['Comentarios_Analizados'])

    def test_engine_errors_abstain_and_do_not_enter_denominator(self):
        class Broken(ContractEngine):
            def analyze(self, text, source='comentario'):
                raise RuntimeError('fallo local')
        result = analyze_records(self.profile, self.posts, self.comments, Broken())
        frame = result['Comentarios_Analizados']
        self.assertEqual((frame['Estado_Analisis'] == 'error_motor').sum(), 4)
        self.assertTrue(result['Resumen_General']['Proporcion'].isna().all())
        self.assertTrue(frame.iloc[0]['Error_Motor'].startswith('RuntimeError'))
        self.assertEqual(result['Biografia'].iloc[0]['Estado_Analisis'], 'error_motor')
        self.assertIn('error_motor', frame.iloc[0]['apertura_explicacion'])

    def test_error_attribute_and_fabricated_quotes_abstain(self):
        class ErrorAttribute(ContractEngine):
            error = 'Ollama no disponible'
        class Fabrication(ContractEngine):
            def analyze(self, text, source='comentario'):
                results = super().analyze(text, source)
                results[0]['evidencia'] = ['cita inexistente']
                return results
        for engine in [ErrorAttribute(), Fabrication()]:
            result = analyze_records(self.profile, self.posts, self.comments, engine)
            self.assertTrue(result['Resumen_General']['Proporcion'].isna().all())

    def test_partial_engine_failure_uses_successful_group_denominator(self):
        class SometimesBroken(ContractEngine):
            def analyze(self, text, source='comentario'):
                if text == 'NA':
                    raise RuntimeError('Fallo de un texto, no ausencia de senal.')
                return super().analyze(text, source)
        result = analyze_records(self.profile, self.posts, self.comments, SometimesBroken())
        row = result['Resumen_General'].query("Origen == 'audiencia' and Dimension == 'apertura'").iloc[0]
        self.assertEqual(row['Capturados'], 3)
        self.assertEqual(row['Analizados'], 1)
        self.assertEqual(row['Errores_Motor'], 1)
        self.assertEqual(row['Vacios'], 1)
        self.assertEqual(row['Proporcion'], 1)
        self.assertEqual(row['Cobertura_Analisis'], 1 / 3)

    def test_statuses_and_objectives(self):
        for post, expected in [
            ({'Video Links': URL, 'Comments': 0}, 'sin_comentarios'),
            ({'Video Links': URL, 'Comments': 20, 'Comments Status': 'restringido'}, 'restringido'),
            ({'Video Links': URL, 'Comments': '', 'Comments Status': 'error'}, 'error'),
            ({'Video Links': URL, 'Comments': 1}, 'parcial'),
        ]:
            result = analyze_records(self.profile, [post], [], ContractEngine())
            self.assertTrue((result['Resultados_por_Video']['Comments Status'] == expected).all())
        result = analyze_records(self.profile, self.posts, self.comments[:1], ContractEngine(), target_comments=1)
        self.assertTrue((result['Resultados_por_Video']['Comments Status'] == 'completo').all())
        with self.assertRaises(ValueError):
            analyze_records(self.profile, [], [], ContractEngine(), target_comments=0)

    def test_biography_lengths_absence_and_limitations_per_dimension(self):
        for bio in ['', '  ', None, 'Soy curioso', 'palabra ' * 25]:
            with self.subTest(bio=bio):
                result = analyze_records({**self.profile, 'Bio': bio}, [], [], ContractEngine())
                frame = result['Biografia']
                text = bio or ''
                self.assertTrue((frame['Longitud_Caracteres'] == len(text)).all())
                self.assertTrue((frame['Longitud_Palabras'] == len(text.split())).all())
                self.assertTrue((frame['Bio_Ausente'] == (not bool(text.strip()))).all())
                self.assertTrue(frame['Limitaciones'].str.contains('Autopresentacion no equivale a personalidad').all())
                if not text.strip():
                    self.assertTrue(frame['Limitaciones'].str.contains('Bio ausente').all())
                    self.assertTrue((frame['Estado_Analisis'] == 'sin_texto').all())
                elif len(text.strip()) < 100 or len(text.split()) < 20:
                    self.assertTrue(frame['Limitaciones'].str.contains('Texto corto').all())
                else:
                    self.assertFalse(frame['Limitaciones'].str.contains('Texto corto').any())

    def test_capture_status_preserved_and_legacy_uses_target_not_reported(self):
        comments = [{**self.comments[0], 'Comment ID': str(index)} for index in range(12)]
        for status in ['completo', 'parcial', 'sin_comentarios', 'restringido', 'error', '']:
            post = {'Video Links': URL, 'Comments': 12, 'Comments Status': status}
            result = analyze_records(self.profile, [post], comments, ContractEngine())
            frame = result['Resultados_por_Video']
            self.assertTrue((frame['Comments Status'] == (status or 'parcial')).all())
            self.assertFalse(frame['Objetivo_Alcanzado'].any())
            if status == 'sin_comentarios':
                self.assertTrue(frame['Limitaciones'].str.contains('Contradiccion').all())
            if not status:
                self.assertTrue(frame['Limitaciones'].str.contains('todos los disponibles').all())
        with self.assertRaisesRegex(ValueError, 'Comments Status'):
            analyze_records(self.profile, [{'Video Links': URL, 'Comments Status': 'inventado'}], [], ContractEngine())

    def test_over_goal_ratio_is_not_capped_or_presented_as_probability(self):
        comments = [{**self.comments[0], 'Comment ID': str(index)} for index in range(500)]
        result = analyze_records(self.profile, self.posts, comments, ContractEngine())
        summary = result['Resumen_General']
        self.assertTrue((summary['Cobertura_Captura_Objetivo'] == 2.5).all())
        self.assertTrue((summary['Comentarios_Esperados'] == 200).all())
        self.assertTrue(summary['Limitaciones'].str.contains('Muestra supera el objetivo total').all())
        metadata = result['Metodologia'].set_index('Campo')['Valor']
        self.assertIn('no probabilidad', metadata['Denominador_Cobertura_Captura_Objetivo'])
        self.assertIn('ingles', metadata['Lengua'])
        self.assertIn('RULES', metadata['Reglas_Heuristica'])
        from motor_bigfive import ENGINE_VERSION
        self.assertEqual(metadata['Version_Reglas_Heuristica'], ENGINE_VERSION)
        self.assertIn('Negacion', metadata['Limitaciones'])

    def test_bio_failure_recorded_without_contaminating_owner_denominator(self):
        class BioBroken(ContractEngine):
            def analyze(self, text, source='comentario'):
                if source == 'biografia':
                    raise RuntimeError('bio fallo')
                return super().analyze(text, source)
        result = analyze_records(self.profile, self.posts, self.comments, BioBroken())
        self.assertTrue(result['Biografia']['Error_Motor'].str.contains('bio fallo').all())
        self.assertTrue(result['Biografia']['Limitaciones'].str.contains('bio fallo').all())
        metadata = result['Metodologia'].set_index('Campo')['Valor']
        self.assertEqual(metadata['Error_Motor_Biografia'], '1')
        self.assertIn('bio fallo', metadata['Detalle_Error_Motor_Biografia'])
        row = result['Resumen_General'].query("Origen == 'propietario' and Dimension == 'apertura'").iloc[0]
        self.assertEqual(row['Analizados'], 1)
        self.assertEqual(row['Proporcion'], 1)
        self.assertIn('no atribuye', row['Limitaciones'])

    def test_real_engine_owner_is_author_not_subject_and_english_is_limited(self):
        result = analyze_records({'id_perfil': 'owner', 'Bio': 'I am curious'}, self.posts,
                                 [{**self.comments[0], 'Comment Text': 'Eres creativo'}], create_engine())
        bio = result['Biografia'].set_index('dimension').loc['apertura']
        self.assertTrue(bio['senal'])
        self.assertEqual(bio['referencia'], 'autopresentacion')
        comment = result['Comentarios_Analizados'].iloc[0]
        self.assertEqual(comment['Origen'], 'propietario')
        self.assertEqual(comment['apertura_referencia'], 'percepcion_tercero')
        self.assertIn('no la personalidad', comment['apertura_explicacion'])

    def test_irrelevant_and_video_opinion_signals_are_engine_errors(self):
        for reference in ['irrelevante', 'opinion_video']:
            class Contradictory(ContractEngine):
                def analyze(self, text, source='comentario'):
                    results = super().analyze(text, source)
                    results[0]['referencia'] = reference
                    return results
            result = analyze_records(self.profile, self.posts, self.comments[:1], Contradictory())
            self.assertTrue((result['Biografia']['Estado_Analisis'] == 'error_motor').all())
            self.assertEqual(result['Comentarios_Analizados'].iloc[0]['Estado_Analisis'], 'error_motor')
            self.assertTrue(result['Resumen_General']['Proporcion'].isna().all())

    def test_numeric_excel_id_precision_checked_before_pandas(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            paths = export_raw(self.profile, self.posts, self.comments[:1], directory)
            for column in ['Comment ID', 'Video ID']:
                for value in [2**53, 2**53 + 1, 2**53 + 2, 1.25, 9e18]:
                    with self.subTest(column=column, value=value):
                        book = Workbook()
                        sheet = book.active
                        sheet.append(['Video Links', 'Comment ID', 'Comment Text', 'Video ID'])
                        sheet.append([URL, '1', 'curiosidad', URL.rsplit('/', 1)[1]])
                        sheet.cell(2, 2 if column == 'Comment ID' else 4, value)
                        bad = Path(directory) / 'numeric.xlsx'
                        book.save(bad)
                        book.close()
                        with self.assertRaisesRegex(ValueError, 'precision ya perdida'):
                            analyze_files(paths['perfil'], bad, paths['posts'], directory, ContractEngine())
            # Small numeric legacy IDs are admitted, without fabricating digits.
            book = Workbook()
            sheet = book.active
            sheet.append(['Video Links', 'Comment ID', 'Comment Text', 'Video ID'])
            sheet.append(['https://www.tiktok.com/@owner/video/123', 456, 'NA', 123])
            safe = Path(directory) / 'safe.xlsx'
            book.save(safe)
            book.close()
            posts = Path(directory) / 'posts.csv'
            pd.DataFrame([{'Video Links': 'https://www.tiktok.com/@owner/video/123'}]).to_csv(posts, index=False)
            output = analyze_files(paths['perfil'], safe, posts, directory, ContractEngine())
            frame = pd.read_excel(output, sheet_name='Comentarios_Analizados', dtype=str, keep_default_na=False)
            self.assertEqual(frame.iloc[0]['Comment ID'], '456')
            self.assertEqual(frame.iloc[0]['Video ID'], '123')

    def test_cli_returns_codes_and_clear_errors_without_traceback(self):
        with patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(main(['--help']), 0)
        with patch('sys.stderr', new_callable=io.StringIO) as stderr:
            self.assertEqual(main([]), 2)
            self.assertNotIn('Traceback', stderr.getvalue())
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            paths = export_raw(self.profile, self.posts, [], directory)
            argv = ['--perfil', str(paths['perfil']), '--comentarios', str(paths['comentarios']),
                    '--posts', str(paths['posts']), '--salida', directory]
            for replacement, expected in [('missing.xlsx', 'no encontrado'), ('bad.csv', 'Bio')]:
                bad = Path(directory) / replacement
                if replacement == 'bad.csv':
                    pd.DataFrame([{'id_perfil': 'owner'}]).to_csv(bad, index=False)
                with patch('sys.stderr', new_callable=io.StringIO) as stderr:
                    self.assertEqual(main([*argv[:1], str(bad), *argv[2:]]), 1)
                    self.assertIn(expected, stderr.getvalue())
                    self.assertNotIn('Traceback', stderr.getvalue())
            with patch('sys.stdout', new_callable=io.StringIO) as stdout:
                self.assertEqual(main([*argv, '--videos-objetivo', '3']), 0)
            frame = pd.read_excel(stdout.getvalue().strip(), sheet_name='Resumen_General')
            self.assertTrue((frame['Videos_Objetivo'] == 3).all())
            with patch('sys.stderr', new_callable=io.StringIO) as stderr:
                self.assertEqual(main([*argv, '--videos-objetivo', '0']), 1)
                self.assertIn('positivos', stderr.getvalue())

    def test_all_result_sheets_store_formula_like_text_and_reversible_unicode(self):
        text = '=curiosidad \\ruta\\u0000\x00 Se\u00f1al \U0001f600'
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            output = export_analysis({**self.profile, 'Bio': text}, self.posts,
                                     [{**self.comments[0], 'Comment Text': text}], directory, ContractEngine())
            book = load_workbook(output)
            self.assertEqual(book.properties.description, TEXT_ENCODING)
            for sheet in book:
                self.assertFalse(any(cell.data_type == 'f' for row in sheet for cell in row))
            bio = book['Biografia']
            self.assertEqual(_restore_text(bio['B2'].value), text)
            sheet = book['Comentarios_Analizados']
            headers = {cell.value: cell.column for cell in sheet[1]}
            self.assertEqual(_restore_text(sheet.cell(2, headers['Comment Text']).value), text)
            book.close()

    def test_roundtrip_excel_na_unicode_ids_formula_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            paths = export_raw(self.profile, self.posts, self.comments, directory)
            output = analyze_files(paths['perfil'], paths['comentarios'], paths['posts'],
                                   directory, ContractEngine())
            book = load_workbook(output)
            self.assertEqual(len(book.sheetnames), 5)
            self.assertEqual(book['Biografia']['B2'].value, self.profile['Bio'])
            self.assertEqual(book['Biografia']['B2'].data_type, 's')
            frame = pd.read_excel(output, sheet_name='Comentarios_Analizados', dtype=str, keep_default_na=False)
            self.assertEqual(frame.iloc[0]['Comment ID'], self.comments[0]['Comment ID'])
            self.assertEqual(frame.iloc[2]['Comment Text'], 'NA')
            self.assertEqual(frame.iloc[3]['Comment Text'], 'curiosidad an\u00f3nima')
            sheet = book['Comentarios_Analizados']
            headers = {cell.value: cell.column for cell in sheet[1]}
            self.assertEqual(sheet.cell(3, headers['Comment Text']).data_type, 's')
            with patch('analisis_bigfive._stamp', return_value='fijo'):
                first = export_analysis(self.profile, [], [], directory, ContractEngine())
                second = export_analysis(self.profile, [], [], directory, ContractEngine())
            self.assertNotEqual(first, second)
            self.assertTrue(first.exists() and second.exists())

    def test_empty_file_schema_validated(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            paths = export_raw(self.profile, self.posts, [], directory)
            bad = Path(directory) / 'bad.xlsx'
            write_workbook(bad, {'Datos': pd.DataFrame(columns=['Comment ID'])})
            with self.assertRaisesRegex(ValueError, 'Video Links'):
                analyze_files(paths['perfil'], bad, paths['posts'], directory, ContractEngine())

    def test_raw_control_escape_roundtrip_preserves_engine_input(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            text = 'curiosidad\x00\\u0000\\ruta\nfin'
            profile = {**self.profile, 'Bio': text}
            comments = [{**self.comments[0], 'Comment Text': text}]
            paths = export_raw(profile, self.posts, comments, directory)
            engine = ContractEngine()
            analyze_files(paths['perfil'], paths['comentarios'], paths['posts'], directory, engine)
            self.assertEqual(engine.calls, [(text, 'biografia'), (text, 'comentario')])

    def test_csv_preserves_literal_na_unicode_and_ids(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            directory = Path(directory)
            profile, posts, comments = [directory / name for name in ('perfil.csv', 'posts.csv', 'comments.csv')]
            pd.DataFrame([self.profile]).to_csv(profile, index=False)
            pd.DataFrame(self.posts).to_csv(posts, index=False)
            pd.DataFrame(self.comments[:4]).to_csv(comments, index=False)
            engine = ContractEngine()
            output = analyze_files(profile, comments, posts, directory, engine)
            frame = pd.read_excel(output, sheet_name='Comentarios_Analizados', dtype=str, keep_default_na=False)
            self.assertEqual(frame.iloc[2]['Comment Text'], 'NA')
            self.assertEqual(frame.iloc[0]['Comment ID'], '9000000000000000001')
            self.assertEqual(engine.calls[-1][0], 'curiosidad an\u00f3nima')

    def test_cli_heuristic_offline(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            paths = export_raw(self.profile, self.posts, self.comments, directory)
            script = Path(__file__).resolve().parents[1] / 'analisis_bigfive.py'
            completed = subprocess.run([
                sys.executable, str(script), '--perfil', str(paths['perfil']),
                '--comentarios', str(paths['comentarios']), '--posts', str(paths['posts']),
                '--motor', 'heuristica', '--salida', directory, '--comentarios-objetivo', '2',
            ], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = Path(completed.stdout.strip())
            self.assertTrue(output.exists())
            self.assertEqual(len(load_workbook(output).sheetnames), 5)

    def test_heuristic_has_no_network_and_import_has_no_playwright(self):
        with patch('socket.socket', side_effect=AssertionError('red prohibida')):
            engine = create_engine()
            result = analyze_records({'id_perfil': 'owner', 'Bio': 'Ingeniero'}, [], [], engine)
        self.assertFalse(result['Biografia']['senal'].any())
        code = "import sys, analisis_bigfive; assert not any(x.startswith('playwright') for x in sys.modules)"
        completed = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)


class FactoryTests(unittest.TestCase):
    def test_bad_method_and_missing_model(self):
        with self.assertRaises(ValueError):
            create_engine('otro')
        with self.assertRaisesRegex(ValueError, 'modelo'):
            create_engine('ollama')

    def test_lazy_ollama_factory_forwards_configuration_without_network(self):
        with patch.dict(sys.modules, {'ollama_bigfive': SimpleNamespace(OllamaEngine=unittest.mock.Mock())}):
            factory = sys.modules['ollama_bigfive'].OllamaEngine
            engine = create_engine('ollama', 'modelo-local', 'http://127.0.0.1:1234')
            factory.assert_called_once_with(model='modelo-local', endpoint='http://127.0.0.1:1234')
            self.assertIs(engine, factory.return_value)


if __name__ == '__main__':
    unittest.main()

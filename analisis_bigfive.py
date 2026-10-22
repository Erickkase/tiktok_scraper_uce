"""Offline textual signal analysis, not a personality or psychometric measure."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zipfile import BadZipFile

import pandas as pd

from exportacion import TEXT_ENCODING, _restore_text, _safe_user, _stamp, _write_unique
from configuracion import DEFAULT_CONFIG


ORIGINS = ('propietario', 'audiencia', 'sin_identificar')
DESCRIPTIONS = {
    'apertura': 'Senales textuales de curiosidad, imaginacion y apertura a experiencias.',
    'responsabilidad': 'Senales textuales de organizacion, constancia y cumplimiento.',
    'extraversion': 'Senales textuales de sociabilidad, actividad y expresividad.',
    'amabilidad': 'Senales textuales de cooperacion, empatia y trato interpersonal.',
    'neuroticismo': 'Senales textuales de preocupacion y reactividad emocional.',
}
RESULT_FIELDS = ('senal', 'direccion', 'evidencia', 'explicacion', 'metodo', 'estado', 'referencia')


def create_engine(method='heuristica', model=None, endpoint='http://127.0.0.1:11434'):
    if method == 'heuristica':
        from motor_bigfive import HeuristicEngine
        return HeuristicEngine()
    if method == 'ollama':
        if not model:
            raise ValueError('El motor ollama requiere --modelo.')
        from ollama_bigfive import OllamaEngine
        return OllamaEngine(model=model, endpoint=endpoint)
    raise ValueError(f'Motor no reconocido: {method}')


def _text(value):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return ''
    return str(value)


def _handle(value):
    return _text(value).strip().removeprefix('@').casefold()


def _require(frame, names, label):
    missing = set(names) - set(frame.columns)
    if missing:
        raise ValueError(f'{label}: faltan columnas requeridas: {", ".join(sorted(missing))}')


def _video(value, owner):
    parsed = urlparse(_text(value))
    match = re.fullmatch(r'/@([A-Za-z0-9_.]+)/video/([0-9]+)/?', parsed.path)
    if (parsed.scheme not in ('https', 'http') or parsed.netloc.lower() not in
            ('www.tiktok.com', 'tiktok.com') or not match):
        raise ValueError(f'URL de video TikTok no canonica: {value}')
    if _handle(match[1]) != owner:
        raise ValueError(f'Video de otro perfil: {value}')
    identifier = str(int(match[2]))
    return identifier, f'https://www.tiktok.com/@{owner}/video/{identifier}'


def _identifier(value, label):
    if isinstance(value, float):
        raise ValueError(f'{label}: ID flotante no fiable; leer como texto.')
    value = _text(value)
    if not re.fullmatch(r'[0-9]+', value):
        raise ValueError(f'{label}: ID numerico requerido.')
    return value


def _reported(value):
    text = _text(value).strip()
    if not text:
        return None
    if not re.fullmatch(r'[0-9]+(?:\.0+)?', text):
        raise ValueError(f'Comments debe ser un total entero o vacio: {value}')
    return int(text.split('.')[0])


def _analyze(text, source, engine, dimensions):
    from motor_bigfive import empty_results
    method = getattr(engine, 'method', type(engine).__name__)
    if not text.strip():
        return empty_results(method=method, explanation='Texto vacio; no analizado.'), 'sin_texto', ''
    try:
        results = engine.analyze(text, source=source)
        error = getattr(engine, 'error', None)
        if error:
            raise ValueError(str(error))
        if not isinstance(results, list) or len(results) != 5:
            raise ValueError('El motor no devolvio cinco dimensiones.')
        by_dimension = {}
        for result in results:
            if not isinstance(result, dict) or set(('dimension', *RESULT_FIELDS)) - result.keys():
                raise ValueError('Respuesta del motor incompleta.')
            dimension = result['dimension']
            if dimension not in dimensions or dimension in by_dimension:
                raise ValueError('Dimensiones del motor invalidas o repetidas.')
            if type(result['senal']) is not bool or result['direccion'] not in {
                'positiva', 'negativa', 'mixta', 'no_interpretable',
            } or result['estado'] not in {'senal_identificada', 'sin evidencia suficiente'}:
                raise ValueError('Estado o direccion invalido del motor.')
            if result['referencia'] not in {
                'autorreferencia', 'percepcion_tercero', 'autopresentacion', 'opinion_video', 'irrelevante',
            }:
                raise ValueError('Referencia invalida del motor.')
            if any(not isinstance(result[field], str) or not result[field]
                   for field in ('explicacion', 'metodo')):
                raise ValueError('Explicacion o metodo invalido del motor.')
            evidence = result['evidencia']
            if (not isinstance(evidence, list) or any(
                not isinstance(quote, str) or not quote or quote not in text for quote in evidence
            )):
                raise ValueError('La evidencia no es una cita literal del original.')
            if result['senal'] != (result['estado'] == 'senal_identificada') or (
                result['senal'] and (not evidence or result['direccion'] == 'no_interpretable'
                                     or result['referencia'] in {'irrelevante', 'opinion_video'})
            ) or (not result['senal'] and (evidence or result['direccion'] != 'no_interpretable')):
                raise ValueError('Respuesta contradictoria del motor.')
            by_dimension[dimension] = result
        return [by_dimension[dimension] for dimension in dimensions], 'analizado', ''
    except Exception as error:
        message = f'{type(error).__name__}: {error}'
        return empty_results(method=method, explanation=f'error_motor: {message}'), 'error_motor', message


def analyze_records(profile, posts, comments, engine=None,
                    target_comments=DEFAULT_CONFIG.comments, target_videos=DEFAULT_CONFIG.videos):
    """Return five DataFrames with distinct source groups and actual denominators."""
    from motor_bigfive import DIMENSIONS, ENGINE_VERSION
    if any(type(value) is not int or value <= 0 for value in (target_comments, target_videos)):
        raise ValueError('Los objetivos deben ser enteros positivos.')
    _require(pd.DataFrame([profile]), ['id_perfil', 'Bio'], 'perfil')
    owner = _handle(profile['id_perfil'])
    if not re.fullmatch(r'[a-z0-9_][a-z0-9_.]{0,23}', owner) or owner.endswith('.'):
        raise ValueError('id_perfil debe ser un identificador de usuario TikTok.')
    # Empty lists are valid captures; file schemas are validated separately.
    if posts:
        _require(pd.DataFrame(posts), ['Video Links'], 'posts')
    if comments:
        _require(pd.DataFrame(comments), ['Video Links', 'Comment ID', 'Comment Text'], 'comentarios')
    limitations = [
        'Muestra de conveniencia sesgada; no representa a todos los usuarios ni comentarios.',
        'Negacion, ironia, sujetos y contexto pueden interpretarse incorrectamente; revisar las citas.',
        'Origen propietario identifica al autor por handle, no atribuye las senales a su personalidad; '
        'percepcion_tercero puede describir a otra persona.',
    ]
    videos = {}
    for post in posts:
        _require(pd.DataFrame([post]), ['Video Links'], 'post')
        if _text(post.get('id_perfil')) and _handle(post['id_perfil']) != owner:
            raise ValueError('Post de otro perfil.')
        vid, url = _video(post['Video Links'], owner)
        if vid in videos:
            raise ValueError(f'Video repetido en posts: {vid}')
        if _text(post.get('Video ID')) and _identifier(post['Video ID'], 'Video ID') != vid:
            raise ValueError('Video ID no corresponde a Video Links.')
        videos[vid] = {**post, 'Video ID': vid, 'Video Links': url,
                       'Reportados': _reported(post.get('Comments'))}
    if any(post['Reportados'] is None for post in videos.values()):
        limitations.append('Totales Comments ausentes: disponibilidad TikTok desconocida, no cero.')
    normalized, seen, dedup = [], {}, 0
    dedup_by_video = dict.fromkeys(videos, 0)
    for comment in comments:
        _require(pd.DataFrame([comment]), ['Video Links', 'Comment ID', 'Comment Text'], 'comentario')
        vid, url = _video(comment['Video Links'], owner)
        if vid not in videos:
            raise ValueError('Comentario asociado a un video ausente de posts.')
        if _text(comment.get('id_perfil')) and _handle(comment['id_perfil']) != owner:
            raise ValueError('Comentario de otro perfil.')
        if _text(comment.get('Video ID')) and _identifier(comment['Video ID'], 'Video ID') != vid:
            raise ValueError('Video ID del comentario no corresponde a su URL.')
        cid = _identifier(comment['Comment ID'], 'Comment ID')
        text = _text(comment['Comment Text'])
        if cid in seen:
            previous = seen[cid]
            if previous['Video ID'] != vid:
                raise ValueError('Mismo Comment ID asociado a distintos videos.')
            if previous['Comment Text'] != text or _handle(previous.get('Author Handle')) != _handle(comment.get('Author Handle')):
                raise ValueError('Mismo Comment ID con contenido o identificador de autor conflictivo.')
            dedup += 1
            dedup_by_video[vid] += 1
            continue
        handle = _handle(comment.get('Author Handle'))
        if handle and (not re.fullmatch(r'[a-z0-9_][a-z0-9_.]{0,23}', handle) or handle.endswith('.')):
            handle = ''
        origin = 'sin_identificar' if not handle else ('propietario' if handle == owner else 'audiencia')
        row = {**comment, 'Comment ID': cid, 'Comment Text': text, 'Video ID': vid,
               'Video Links': url, 'Origen': origin}
        normalized.append(row)
        seen[cid] = row
    if any(row['Origen'] == 'sin_identificar' for row in normalized):
        limitations.append('Sin Author Handle fiable: Author/nickname no identifica propietario; grupo sin_identificar separado.')
    limitations.append(f'Deduplicacion por Comment ID: {dedup} filas descartadas; no son comentarios independientes.')
    engine = engine if engine is not None else create_engine()
    bio = _text(profile['Bio'])
    bio_results, bio_status, bio_error = _analyze(bio, 'biografia', engine, DIMENSIONS)
    bio_limits = ['Autopresentacion no equivale a personalidad ni a medicion psicometrica.']
    if _text(profile.get('Profile Error')):
        bio_limits.append('Limitacion de captura del perfil: ' + _text(profile['Profile Error']))
    if not bio.strip():
        bio_limits.append('Bio ausente: no hay texto para analizar, no ausencia de rasgos.')
    elif len(bio.strip()) < 100 or len(bio.split()) < 20:
        bio_limits.append('Texto corto (<100 caracteres o <20 palabras); contexto insuficiente para generalizar.')
    if bio_error:
        bio_limits.append(f'Error de motor en biografia: {bio_error}')
    bio_limits.append(limitations[1])
    biography = pd.DataFrame([
        {'id_perfil': _text(profile['id_perfil']), 'Bio': bio, 'Estado_Analisis': bio_status,
         'Longitud_Caracteres': len(bio), 'Longitud_Palabras': len(bio.split()),
         'Bio_Ausente': not bool(bio.strip()), 'Limitaciones': ' | '.join(bio_limits),
         'Error_Motor': bio_error, **result,
         'evidencia': json.dumps(result['evidencia'], ensure_ascii=False)} for result in bio_results
    ])
    analyzed = []
    for row in normalized:
        results, status, error = _analyze(row['Comment Text'], 'comentario', engine, DIMENSIONS)
        record = {**row, 'Estado_Analisis': status, 'Error_Motor': error}
        for result in results:
            for field in RESULT_FIELDS:
                value = result[field]
                record[f'{result["dimension"]}_{field}'] = (
                    json.dumps(value, ensure_ascii=False) if field == 'evidencia' else value
                )
        analyzed.append(record)
    comment_columns = list(dict.fromkeys([
        'Video Links', 'Video ID', 'Comment ID', 'Author Handle', 'Author', 'Comment Text',
        'Comment Likes', 'Origen', 'Estado_Analisis', 'Error_Motor',
        *(key for row in analyzed for key in row),
        *(f'{dimension}_{field}' for dimension in DIMENSIONS for field in RESULT_FIELDS),
    ]))
    analyzed_frame = pd.DataFrame(analyzed, columns=comment_columns)

    def summarize(rows, dimension):
        valid = [row for row in rows if row['Estado_Analisis'] == 'analizado']
        signals = [row for row in valid if row[f'{dimension}_senal']]
        return {
            'Capturados': len(rows), 'Analizados': len(valid),
            'Vacios': sum(row['Estado_Analisis'] == 'sin_texto' for row in rows),
            'Errores_Motor': sum(row['Estado_Analisis'] == 'error_motor' for row in rows),
            'Con_Senales': len(signals),
            'Proporcion': len(signals) / len(valid) if valid else None,
            'Porcentaje': 100 * len(signals) / len(valid) if valid else None,
            'Cobertura_Analisis': len(valid) / len(rows) if rows else None,
            'Ejemplos_Literales': json.dumps([
                {'Comment ID': row['Comment ID'], 'citas': json.loads(row[f'{dimension}_evidencia'])}
                for row in signals[:3]
            ], ensure_ascii=False),
        }

    video_rows = []
    for vid, post in videos.items():
        rows = [row for row in analyzed if row['Video ID'] == vid]
        reported = post['Reportados']
        raw_status = _text(post.get('Comments Status')).strip().casefold()
        if raw_status and raw_status not in {'completo', 'parcial', 'sin_comentarios', 'restringido', 'error'}:
            raise ValueError(f'Comments Status desconocido: {raw_status}')
        status = raw_status or (
            'sin_comentarios' if reported == 0 and not rows else
            'completo' if len(rows) >= target_comments else 'parcial'
        )
        local_limits = list(limitations)
        if not raw_status:
            local_limits.append('Estado legacy inferido segun objetivo, no segun min(Comments, objetivo); '
                                '12 capturados pueden ser todos los disponibles sin completar el objetivo de 20.')
        if status == 'sin_comentarios' and (rows or reported not in (None, 0)):
            local_limits.append('Contradiccion: sin_comentarios con captura o total reportado positivo; estado original preservado.')
        if status == 'completo' and len(rows) < target_comments:
            local_limits.append('Completo segun scraper, pero objetivo no alcanzado; puede haber agotado los disponibles.')
        if len(rows) > target_comments:
            local_limits.append('Muestra supera el objetivo de comentarios por video; no es una probabilidad.')
        if status != 'completo':
            local_limits.append(f'Captura {status}; no implica ausencia de senales en comentarios no capturados.')
        if reported is not None and len(rows) > reported:
            local_limits.append('Capturados superiores al total reportado; contadores de momentos distintos o inconsistentes.')
        for origin in ORIGINS:
            group = [row for row in rows if row['Origen'] == origin]
            for dimension in DIMENSIONS:
                video_rows.append({
                    'Video ID': vid, 'Video Links': post['Video Links'], 'Origen': origin,
                    'Dimension': dimension, 'Etiqueta': DIMENSIONS[dimension],
                    'Comments_Reportados': reported,
                    'Disponibilidad': 'desconocida' if reported is None else 'reportada',
                    'Capturados_Video': len(rows), 'Comentarios_Objetivo': target_comments,
                    'Objetivo_Alcanzado': len(rows) >= target_comments,
                    'Comments Status': status, 'Comments Status Original': post.get('Comments Status', ''),
                    'Comments Error': post.get('Comments Error', ''),
                    'Duplicados_Descartados': dedup_by_video[vid],
                    **summarize(group, dimension), 'Limitaciones': ' | '.join(local_limits),
                })
    known_totals = [post['Reportados'] for post in videos.values() if post['Reportados'] is not None]
    if len(analyzed) > target_videos * target_comments:
        limitations.append('Muestra supera el objetivo total: Cobertura_Captura_Objetivo > 1 es una razon de conteos, '
                            'no probabilidad estadistica; no se limita artificialmente a 1.')
    summary_rows = []
    for origin in ORIGINS:
        group = [row for row in analyzed if row['Origen'] == origin]
        for dimension in DIMENSIONS:
            summary_rows.append({
                'Origen': origin, 'Dimension': dimension, 'Etiqueta': DIMENSIONS[dimension],
                'Total_Videos': len(videos), 'Videos_Objetivo': target_videos,
                'Comentarios_Objetivo_Por_Video': target_comments,
                'Comentarios_Esperados': target_videos * target_comments,
                'Comments_Reportados': sum(known_totals) if len(known_totals) == len(videos) and videos else None,
                'Subtotal_Reportado_Conocido': sum(known_totals) if known_totals else None,
                'Videos_Total_Desconocido': len(videos) - len(known_totals),
                'Capturados_Total': len(analyzed),
                'Cobertura_Captura_Objetivo': len(analyzed) / (target_videos * target_comments),
                'Duplicados_Descartados': dedup,
                **summarize(group, dimension),
                'Interpretacion': 'Porcentaje de comentarios analizados con senales textuales en este grupo; no personalidad ni confianza.',
                'Limitaciones': ' | '.join(limitations),
            })
    metadata = [
        ('Motor', str(getattr(engine, 'method', type(engine).__name__))),
        ('Modelo', str(getattr(engine, 'model', '') or 'no aplica')),
        ('Endpoint', str(getattr(engine, 'endpoint', '') or 'sin red')),
        ('Fecha_UTC', datetime.now(timezone.utc).isoformat()),
        ('Configuracion', json.dumps({'target_comments': target_comments, 'target_videos': target_videos})),
        ('Lengua', 'Heuristica: frases admitidas en espanol y un subconjunto limitado en ingles; '
         'no soporta todas las frases ni todas las lenguas. Ollama depende del modelo; no se presume cobertura multilingue.'),
        ('Reglas_Heuristica', 'motor_bigfive.py: RULES, _ADJECTIVES, _make_rules; coincidencias textuales, no inventario psicometrico.'),
        ('Version_Reglas_Heuristica', ENGINE_VERSION),
        ('Alcance', 'Senales textuales exploratorias; no psicometria, no medicion de personalidad, sin BFI-2.'),
        ('Validacion', 'Heuristica no validada; tampoco se presume validez psicometrica de Ollama.'),
        ('Fuentes', 'Biografia separada; autopresentacion no equivale a audiencia ni a propietario en comentarios.'),
        ('Denominador', 'Solo comentarios no vacios y sin error de motor por origen. Sin denominador: celda vacia, no cero.'),
        ('Denominador_Cobertura_Captura_Objetivo', 'Capturados_Total / (Videos_Objetivo * Comentarios_Objetivo_Por_Video). '
         'Razon global de conteos repetida por grupo, puede superar 1; no probabilidad ni cobertura de todos los disponibles.'),
        ('Denominador_Cobertura_Analisis', 'Analizados / Capturados del grupo; Proporcion = Con_Senales / Analizados del grupo.'),
        ('Likes', 'Comment Likes se conserva como metadato; nunca se envia al motor ni pondera porcentajes.'),
        ('Errores_Motor_Comentarios', str(sum(row['Estado_Analisis'] == 'error_motor' for row in analyzed))),
        ('Error_Motor_Biografia', str(int(bio_status == 'error_motor'))),
        ('Detalle_Error_Motor_Biografia', bio_error),
        ('Limitaciones_Biografia', ' | '.join(bio_limits)),
        ('Umbral_Texto_Corto_Biografia', '<100 caracteres sin espacios exteriores o <20 palabras separadas por espacios; '
         'advertencia descriptiva, no umbral validado de suficiencia psicometrica. Longitud_Caracteres conserva espacios originales.'),
        ('Abstenciones', 'Texto vacio, profesion sola o evidencia insuficiente no justifican inferir rasgos; error_motor no es ausencia cierta de senal.'),
        ('Deduplicacion', str(dedup)),
        ('Muestreo', 'Textos cortos y muestra sesgada. Objetivo de captura no es totalidad; no generalizar prevalencias.'),
        ('Excel', TEXT_ENCODING + r': todos los textos, incluidas cabeceras, usan tipo s. Backslash se duplica; '
         r'controles XML se escapan como \uXXXX; _restore_text decodifica una vez de izquierda a derecha. '
         'Solo decodificar libros marcados; vacios y Unicode se conservan, formulas son texto, sin truncar.'),
        ('Limitaciones', ' | '.join(limitations)),
        *((f'Dimension_{dimension}', description) for dimension, description in DESCRIPTIONS.items()),
    ]
    video_columns = ['Video ID', 'Video Links', 'Origen', 'Dimension', 'Etiqueta',
                     'Comments_Reportados', 'Disponibilidad', 'Capturados_Video',
                     'Comentarios_Objetivo', 'Objetivo_Alcanzado', 'Comments Status',
                     'Comments Status Original', 'Comments Error', 'Duplicados_Descartados',
                     'Capturados', 'Analizados', 'Vacios', 'Errores_Motor', 'Con_Senales',
                     'Proporcion', 'Porcentaje', 'Cobertura_Analisis', 'Ejemplos_Literales', 'Limitaciones']
    return {
        'Biografia': biography,
        'Comentarios_Analizados': analyzed_frame,
        'Resultados_por_Video': pd.DataFrame(video_rows, columns=video_columns),
        'Resumen_General': pd.DataFrame(summary_rows),
        'Metodologia': pd.DataFrame(metadata, columns=['Campo', 'Valor']),
    }


def export_analysis(profile, posts, comments, output_dir, engine=None,
                    target_comments=DEFAULT_CONFIG.comments, target_videos=DEFAULT_CONFIG.videos):
    sheets = analyze_records(profile, posts, comments, engine, target_comments, target_videos)
    return _write_unique(output_dir, f'{_safe_user(profile)}_bigfive_{_stamp()}', sheets)


def analyze_files(perfil_path, comentarios_path, posts_path, output_dir=None, engine=None,
                  target_comments=DEFAULT_CONFIG.comments, target_videos=DEFAULT_CONFIG.videos):
    def read(path):
        path = Path(path)
        if path.suffix.casefold() == '.csv':
            return pd.read_csv(path, dtype=str, keep_default_na=False)
        with pd.ExcelFile(path, engine='openpyxl') as source:
            sheet = source.book.worksheets[0]
            headers = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
            id_columns = [index for index, name in enumerate(headers) if name in {'Comment ID', 'Video ID'}]
            for row in sheet.iter_rows(min_row=2):
                for index in id_columns:
                    cell = row[index]
                    if cell.data_type == 'n' and cell.value is not None and (
                        # The boundary itself may be a rounded 2**53 + 1.
                        isinstance(cell.value, float) or abs(cell.value) >= 2**53
                    ):
                        raise ValueError(f'{path.name}: {headers[index]} en {cell.coordinate}: ID numerico Excel '
                                         'no fiable; precision ya perdida o no garantizada. Use el ID original como texto.')
            frame = pd.read_excel(source, dtype=str, keep_default_na=False)
            if source.book.properties.description == TEXT_ENCODING:
                for column in frame.columns:
                    frame[column] = frame[column].map(_restore_text)
                frame.columns = [_restore_text(column) for column in frame.columns]
            return frame
    profile, comments, posts = read(perfil_path), read(comentarios_path), read(posts_path)
    _require(profile, ['id_perfil', 'Bio'], 'perfil')
    _require(comments, ['Video Links', 'Comment ID', 'Comment Text'], 'comentarios')
    _require(posts, ['Video Links'], 'posts')
    if len(profile) != 1:
        raise ValueError('El archivo perfil debe contener exactamente una fila.')
    return export_analysis(profile.iloc[0].to_dict(), posts.to_dict('records'),
                           comments.to_dict('records'),
                           output_dir if output_dir is not None else Path(perfil_path).parent,
                           engine, target_comments, target_videos)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--perfil', required=True)
    parser.add_argument('--comentarios', required=True)
    parser.add_argument('--posts', required=True)
    parser.add_argument('--motor', choices=['heuristica', 'ollama'], default='heuristica')
    parser.add_argument('--modelo')
    parser.add_argument('--ollama-url', default='http://127.0.0.1:11434')
    parser.add_argument('--salida')
    parser.add_argument('--comentarios-objetivo', type=int, default=DEFAULT_CONFIG.comments)
    parser.add_argument('--videos-objetivo', type=int, default=DEFAULT_CONFIG.videos)
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        return error.code
    try:
        engine = create_engine(args.motor, args.modelo, args.ollama_url)
        output = analyze_files(args.perfil, args.comentarios, args.posts, args.salida, engine,
                               target_comments=args.comentarios_objetivo, target_videos=args.videos_objetivo)
    except FileNotFoundError as error:
        print(f'Error: archivo o directorio no encontrado: {error.filename or error}', file=sys.stderr)
        return 1
    except (OSError, ValueError, ImportError, EOFError, BadZipFile) as error:
        print(f'Error de analisis/exportacion: {error}', file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == '__main__':
    sys.exit(main())

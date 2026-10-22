"""Descarga limitada de videos; no realiza analisis ni transcripcion.

Uso recomendado: py -3.12 descargar_videos.py "usuario/usuario_post_fecha.xlsx"
Requiere Python >= 3.10 para descargar; el modulo es importable en Python 3.9.
"""

import argparse
import re
import shutil
import struct
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit


MAX_BYTES = 200 * 1024 * 1024
MIN_BYTES = 1024
INSTALL_COMMAND = (
    'py -3.12 -m pip install --only-binary=:all: -r requirements_videos.txt'
)
COLUMNS = ['Video Links', 'Video ID', 'Video File',
           'Download Status', 'Download Error']


class DownloadLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def validate_url(value):
    """Devuelve URL canonica e ID textual, sin parametros ni fragmentos."""
    if not isinstance(value, str):
        raise ValueError('URL de TikTok invalida.')
    try:
        url = urlsplit(value.strip())
        match = re.fullmatch(r'/@[A-Za-z0-9_.]+/video/([0-9]+)', url.path)
        if (url.scheme != 'https' or url.netloc != 'www.tiktok.com'
                or not match):
            raise ValueError('URL de TikTok invalida.')
    except ValueError:
        raise ValueError('URL de TikTok invalida.') from None
    return 'https://www.tiktok.com' + url.path, match.group(1)


def validate_file(path):
    """Comprueba limite y cabecera ISO BMFF; no es una validacion del codec."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return False
    size = path.stat().st_size
    if not MIN_BYTES <= size <= MAX_BYTES:
        return False
    with path.open('rb') as stream:
        header = stream.read(16)
    box_size = struct.unpack('>I', header[:4])[0]
    return (header[4:8] == b'ftyp' and 16 <= box_size <= size
            and box_size % 4 == 0)


def load_backend():
    if sys.version_info < (3, 10):
        raise RuntimeError('Descarga requiere Python >= 3.10; use py -3.12.')
    try:
        from yt_dlp import YoutubeDL
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError('Faltan dependencias de videos. Instale con: ' + INSTALL_COMMAND) from None
    return YoutubeDL


def read_video_metadata(url):
    from playwright.sync_api import sync_playwright

    canonical, video_id = validate_url(url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            page = browser.new_page(locale='en-US')
            response = page.goto(canonical, wait_until='domcontentloaded', timeout=30000)
            if response and response.status >= 400:
                raise ValueError('HTTP ' + str(response.status))
            challenge = page.locator(
                '#captcha_container, #verify-center, iframe[src*="captcha"], [data-e2e="captcha"]'
            ).first
            if '/login' in page.url or challenge.is_visible():
                raise ValueError('Login o CAPTCHA requerido.')
            if validate_url(page.url)[1] != video_id:
                raise ValueError('ID obtenido no coincide o respuesta no es video.')
            # Wait for complete JSON: the script can be attached while its text is still arriving.
            handle = page.wait_for_function('''() => {
                const element = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                try {
                    const data = JSON.parse(element.textContent);
                    return data.__DEFAULT_SCOPE__['webapp.video-detail'] || false;
                } catch { return false; }
            }''', timeout=15000)
            detail = handle.json_value()
            if '/login' in page.url or challenge.is_visible():
                raise ValueError('Login o CAPTCHA requerido.')
            item = detail.get('itemInfo', {}).get('itemStruct', {})
            if str(item.get('id')) != video_id:
                raise ValueError('ID obtenido no coincide o respuesta no es video.')
            if (item.get('itemControl') or {}).get('canDownload') is False:
                raise ValueError('El video no permite descarga.')
            video = item.get('video') or {}
            media_url = video.get('playAddr')
            if not isinstance(media_url, str) or urlsplit(media_url).scheme != 'https':
                raise ValueError('No hay formato MP4 combinado disponible.')
            if video.get('format', 'mp4').lower() != 'mp4':
                raise ValueError('No hay formato MP4 combinado disponible.')
            return {
                'id': video_id, 'title': video_id,
                'formats': [{
                    'format_id': 'public-mp4', 'url': media_url, 'protocol': 'https',
                    'ext': 'mp4', 'vcodec': video.get('codecType') or 'unknown', 'acodec': 'unknown',
                    'http_headers': {'User-Agent': page.evaluate('navigator.userAgent'), 'Referer': canonical},
                }],
            }
        finally:
            browser.close()


def download_video(url, video_id, directory, backend=None):
    """Retorna (estado, error, restriccion). Nunca conserva URLs multimedia."""
    canonical, expected_id = validate_url(url)
    if not isinstance(video_id, str) or video_id != expected_id:
        raise ValueError('Video ID no coincide con la URL.')
    directory = Path(directory)
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        return 'error', 'Carpeta videos insegura o invalida.', False
    directory.mkdir(parents=False, exist_ok=True)
    target = directory / (video_id + '.mp4')
    if target.exists() or target.is_symlink():
        if validate_file(target):
            return 'existing', '', False
        return 'error', 'Destino existente invalido; no se modifica.', False
    backend = backend or load_backend()

    def check_size(progress):
        sizes = [progress.get(key) or 0 for key in
                 ('downloaded_bytes', 'total_bytes', 'total_bytes_estimate')]
        filename = progress.get('tmpfilename') or progress.get('filename')
        if filename:
            candidate = Path(filename)
            if candidate.is_file():
                sizes.append(candidate.stat().st_size)
        if max(sizes) > MAX_BYTES:
            raise ValueError('Limite de 200 MiB excedido.')

    try:
        # Solo este directorio pertenece al intento; nunca limpiar por glob de ID.
        with tempfile.TemporaryDirectory(prefix='download-', dir=str(directory)) as work:
            staged = Path(work) / (video_id + '.mp4')
            options = {
                'format': 'best[ext=mp4][vcodec!=none][acodec!=none]',
                'outtmpl': str(staged), 'noplaylist': True,
                'retries': 0, 'fragment_retries': 0, 'extractor_retries': 0,
                'file_access_retries': 0, 'skip_unavailable_fragments': False,
                'socket_timeout': 30, 'sleep_interval_requests': 2,
                'sleep_interval': 2, 'no_warnings': True, 'quiet': True,
                'max_filesize': MAX_BYTES, 'progress_hooks': [check_size],
                'overwrites': False, 'continuedl': False,
                'fixup': 'never', 'postprocessors': [],
                'logger': DownloadLogger(),
            }
            with backend(options) as downloader:
                info = read_video_metadata(canonical)
                if (not isinstance(info, dict) or info.get('_type', 'video') != 'video'
                        or str(info.get('id')) != video_id):
                    raise ValueError('ID obtenido no coincide o respuesta no es video.')
                formats = info.get('formats') or [info]
                candidates = [fmt for fmt in formats
                              if fmt.get('ext') == 'mp4'
                              and fmt.get('vcodec') not in (None, 'none')
                              and fmt.get('acodec') not in (None, 'none')
                              and not fmt.get('has_drm')
                              and fmt.get('url')
                              and fmt.get('protocol') in ('http', 'https')]
                if not candidates:
                    raise ValueError('No hay formato MP4 combinado disponible.')
                selected = candidates[-1]
                if (selected.get('filesize') or 0) > MAX_BYTES:
                    raise ValueError('Limite de 200 MiB excedido.')
                prepared = dict(info)
                for key in ('requested_formats', 'requested_downloads', 'formats'):
                    prepared.pop(key, None)
                prepared.update(selected)
                if str(prepared.get('id')) != video_id:
                    raise ValueError('ID de formato no coincide.')
                downloader.process_info(prepared)
            if not validate_file(staged):
                raise ValueError('Archivo final invalido: tamano o cabecera ftyp.')
            # Creacion exclusiva: incluso un destino aparecido durante la red se respeta.
            created = False
            try:
                with target.open('xb') as output:
                    created = True
                    with staged.open('rb') as source:
                        shutil.copyfileobj(source, output)
                if not validate_file(target):
                    raise ValueError('Archivo final invalido: tamano o cabecera ftyp.')
            except BaseException:
                if created:
                    target.unlink()
                raise
        return 'downloaded', '', False
    except Exception as error:
        text = str(error).lower()
        code = getattr(error, 'status', None) or getattr(error, 'code', None)
        restricted = (code in (403, 429) or re.search(r'\b(403|429)\b', text)
                      or any(word in text for word in
                             ('captcha', 'login', 'log in', 'log-in', 'logged in',
                              'sign in', 'sign-in', 'authentication required',
                              'registered users', 'not a bot', 'too many requests',
                              'forbidden', 'inicia sesion', 'iniciar sesion')))
        if restricted:
            return 'error', 'Acceso restringido (403/429/captcha/login); consultas detenidas.', True
        # Los errores del extractor pueden incluir URLs firmadas o credenciales.
        safe_errors = (
            'ID obtenido no coincide o respuesta no es video.',
            'ID de formato no coincide.', 'No hay formato MP4 combinado disponible.',
            'El video no permite descarga.',
            'Limite de 200 MiB excedido.',
            'Archivo final invalido: tamano o cabecera ftyp.',
        )
        message = str(error) if str(error) in safe_errors else 'Fallo de descarga; no se reintenta.'
        return 'error', message, False


def run(input_path, backend=None):
    """Lee Excel, descarga hasta 10 IDs unicos y devuelve la ruta del informe."""
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError('Falta pandas/openpyxl. Instale con: ' + INSTALL_COMMAND) from None
    source = Path(input_path)
    if not source.is_file() or source.suffix.lower() != '.xlsx':
        raise ValueError('La entrada debe ser un archivo .xlsx existente.')
    frame = pd.read_excel(source, engine='openpyxl', dtype=str, keep_default_na=False)
    if 'Video Links' not in frame.columns:
        raise ValueError('El Excel no contiene la columna Video Links.')
    report = source.with_name(source.stem + '_descargas.xlsx')
    rows = []
    seen = set()
    for value in frame['Video Links']:
        row = dict(zip(COLUMNS, ['', '', '', 'pending', '']))
        try:
            url, video_id = validate_url(value)
            row.update({'Video Links': url, 'Video ID': video_id})
            if video_id in seen:
                row['Download Status'] = 'duplicate'
            elif len(seen) >= 10:
                row['Download Status'] = 'limit'
            else:
                seen.add(video_id)
        except ValueError as error:
            row.update({'Download Status': 'invalid', 'Download Error': str(error)})
        rows.append(row)

    def save():
        # Reemplazo atomico del informe; IDs y rutas se escriben como texto.
        with tempfile.TemporaryDirectory(prefix='report-', dir=str(source.parent)) as work:
            temporary = Path(work) / 'report.xlsx'
            pd.DataFrame(rows, columns=COLUMNS).to_excel(
                temporary, index=False, engine='openpyxl')
            temporary.replace(report)

    save()
    stopped = False
    queried = False
    try:
        for row in rows:
            if row['Download Status'] != 'pending':
                continue
            if stopped:
                row.update({'Download Status': 'not_queried',
                            'Download Error': 'Consultas detenidas por restriccion de acceso.'})
                save()
                continue
            target = source.parent / 'videos' / (row['Video ID'] + '.mp4')
            # No hay pausa ni carga del backend cuando el destino ya existe.
            local = target.exists() or target.is_symlink()
            if not local and queried:
                time.sleep(2)
            if not local:
                queried = True
            print('Video ' + row['Video ID'] + ': comprobando archivo y descarga...')
            status, error, stopped = download_video(
                row['Video Links'], row['Video ID'], source.parent / 'videos', backend)
            row.update({'Download Status': status, 'Download Error': error})
            if status in ('downloaded', 'existing'):
                row['Video File'] = 'videos/' + row['Video ID'] + '.mp4'
            save()
            if error:
                print('Aviso: ' + error)
            else:
                print('Archivo disponible: ' + row['Video File'])
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt) and row['Download Status'] == 'pending':
            row.update({'Download Status': 'cancelled',
                        'Download Error': 'Descarga cancelada; sin reintento.'})
        for row in rows:
            if row['Download Status'] == 'pending':
                row.update({'Download Status': 'not_queried',
                            'Download Error': 'Ejecucion interrumpida.'})
        save()
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description='Descarga hasta 10 MP4 de un Excel de TikTok.')
    parser.add_argument('excel', help='Archivo .xlsx con columna Video Links')
    args = parser.parse_args()
    try:
        if sys.version_info < (3, 10):
            raise RuntimeError('Se requiere Python >= 3.10; se recomienda py -3.12.')
        report = run(args.excel)
        import pandas as pd
        statuses = pd.read_excel(report, usecols=['Download Status'])['Download Status']
        available = int(statuses.isin(['downloaded', 'existing']).sum())
        failed = statuses.isin(['error', 'not_queried', 'invalid', 'cancelled', 'pending']).any()
    except KeyboardInterrupt:
        print('Cancelado. Se conservo el progreso del manifiesto.', file=sys.stderr)
        return 130
    except Exception as error:
        # No mostrar mensajes arbitrarios del backend con URLs multimedia.
        if isinstance(error, (ValueError, RuntimeError)):
            message = str(error)
        else:
            message = 'No se pudo leer/escribir el Excel o acceder a los archivos.'
        print('Error: ' + message, file=sys.stderr)
        return 1
    print('Manifiesto: ' + str(report))
    print('Videos disponibles: ' + str(available))
    return 1 if failed or not available else 0


if __name__ == '__main__':
    sys.exit(main())

"""CLI: collect public text, export raw data, then analyze linguistic signals."""

import argparse
import asyncio
import sys
from pathlib import Path

from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, async_playwright

from analisis_bigfive import create_engine, export_analysis
from configuracion import DEFAULT_CONFIG, ScraperConfig
from exportacion import _safe_user, export_raw
from scraper import normalize_username, run


async def collect(username, config):
    async with async_playwright() as playwright:
        return await run(playwright, username, config)


def execute(username, config, output_dir=None, engine=None):
    """Both automatic and offline analysis use the same export_analysis engine."""
    username = normalize_username(username)
    destination = Path(output_dir) if output_dir is not None else Path(_safe_user({'id_perfil': username}))
    profile, posts, comments = asyncio.run(collect(username, config))
    # Persist raw text first, even if subsequent analysis fails.
    paths = export_raw(profile, posts, comments, destination)
    for kind, path in paths.items():
        print(f'{kind}: {path}')
    analysis = export_analysis(profile, posts, comments, destination, engine,
                               target_comments=config.comments, target_videos=config.videos)
    print(f'Analisis linguistico (no psicometrico): {analysis}')
    return {**paths, 'bigfive': analysis}


def main(argv=None):
    parser = argparse.ArgumentParser(description='TikTok: datos publicos y senales linguisticas Big Five, no personalidad.')
    parser.add_argument('--usuario', help='Nombre de TikTok, con o sin @; si falta se solicita en consola.')
    parser.add_argument('--videos', type=int, default=DEFAULT_CONFIG.videos)
    parser.add_argument('--comentarios', type=int, default=DEFAULT_CONFIG.comments)
    parser.add_argument('--pausa', type=float, default=DEFAULT_CONFIG.video_delay, help='Segundos entre videos, minimo 2.')
    parser.add_argument('--espera-comentarios', type=float, default=DEFAULT_CONFIG.comment_wait, help='Segundos entre cargas del panel, minimo 2.')
    parser.add_argument('--enlaces', choices=['auto', 'playwright', 'beautifulsoup'], default=DEFAULT_CONFIG.link_method)
    parser.add_argument('--sin-ventana', action='store_true')
    parser.add_argument('--salida', help='Directorio de resultados; por defecto usa el nombre del usuario.')
    parser.add_argument('--motor', choices=['heuristica', 'ollama'], default='heuristica')
    parser.add_argument('--modelo', help='Modelo ya instalado en Ollama, solo con --motor ollama.')
    parser.add_argument('--ollama-url', default='http://127.0.0.1:11434')
    args = parser.parse_args(argv)
    try:
        config = ScraperConfig(videos=args.videos, comments=args.comentarios,
                               video_delay=args.pausa, comment_wait=args.espera_comentarios,
                               headless=args.sin_ventana, link_method=args.enlaces)
        engine = create_engine(args.motor, args.modelo, args.ollama_url)
        if args.usuario is not None:
            username = normalize_username(args.usuario)
        else:
            while True:
                try:
                    username = normalize_username(input('Usuario de TikTok (con o sin @): '))
                    break
                except ValueError as error:
                    print(error)
        execute(username, config, args.salida, engine)
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\nEjecucion cancelada. Los archivos completos ya guardados se conservan.', file=sys.stderr)
        return 130
    except PermissionError:
        print('No se pudo guardar. Cierra los Excel abiertos y revisa los permisos de la carpeta.', file=sys.stderr)
        return 1
    except PlaywrightTimeoutError:
        print('TikTok no respondio a tiempo. No se inventaran datos; comprueba tu conexion y prueba mas tarde.', file=sys.stderr)
        return 1
    except (ValueError, RuntimeError, PlaywrightError, OSError) as error:
        print(f'No se pudo completar el proceso: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

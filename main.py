import asyncio
import json
import re
import sys
from playwright.async_api import async_playwright, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
import os
import aiohttp
import aiofiles
import pandas as pd
from datetime import datetime

VIDEO_DELAY_SECONDS = 2
INTERACTION_FIELDS = {
    'Likes': ('diggCount', 'like-count'),
    'Comments': ('commentCount', 'comment-count'),
    'Shares': ('shareCount', 'share-count'),
    'Saves': ('collectCount', 'favorite-count'),
}


class ScrapingRestrictedError(RuntimeError):
    pass


async def check_page_access(page, response=None):
    if response and response.status in (403, 429):
        raise ScrapingRestrictedError(
            f'TikTok restringio el acceso (HTTP {response.status}). Deten la ejecucion y prueba mas tarde.'
        )
    if response and response.status >= 400:
        raise ValueError(f'Pagina no disponible (HTTP {response.status}).')
    challenge = page.locator(
        '#captcha_container, #verify-center, iframe[src*="captcha"], [data-e2e="captcha"]'
    ).first
    if await challenge.is_visible():
        raise ScrapingRestrictedError('TikTok solicita una verificacion. No se haran mas consultas.')
    if '/login' in page.url:
        raise ScrapingRestrictedError('TikTok solicita iniciar sesion. No se haran mas consultas.')
    private = page.get_by_text(
        re.compile(r'This account is (?:currently )?private|Esta cuenta es privada', re.I)
    ).first
    if await private.is_visible():
        raise ValueError('El perfil es privado; sus publicaciones no son accesibles.')
    missing = page.get_by_text(
        re.compile(r"Couldn't find this account|Account not found|No se pudo encontrar esta cuenta", re.I)
    ).first
    if await missing.is_visible():
        raise ValueError('No se encontro la cuenta. Comprueba el nombre de usuario.')

def normalize_username(value):
    username = value.strip().removeprefix('@')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.]{0,23}', username) or username.endswith('.'):
        raise ValueError(
            'Ingresa un usuario de 1 a 24 caracteres: letras, numeros, puntos o guiones bajos; '
            'sin enlaces ni punto al inicio o al final.'
        )
    return username

def convert_views(views_str):
    value = str(views_str).strip().upper().replace(',', '')
    match = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)([KMB]?)', value)
    if not match or ('.' in match.group(1) and not match.group(2)):
        raise ValueError(f'Contador no reconocido: {views_str}')
    number, suffix = match.groups()
    return int(float(number) * {'K': 1000, 'M': 1000000, 'B': 1000000000}[suffix]) if suffix else int(number)

async def download_image(url, folder, filename):
    if not url.startswith('http'):
        print(f"Invalid image URL: {url}")
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    async with aiofiles.open(os.path.join(folder, filename), 'wb') as f:
                        await f.write(image_data)
                    return filename
                else:
                    print(f"Error downloading image: {response.status}")
                    return None
    except Exception as e:
        print(f"Exception occurred while downloading image: {e}")
        return None

async def collect_recent_videos(page, username):
    try:
        await page.wait_for_selector('a[href*="/video/"]', timeout=60000)
    except PlaywrightTimeoutError:
        await check_page_access(page)
        print('No se cargaron videos publicos. El perfil puede estar vacio o el contenido no disponible.')
        return []
    videos = {}
    unchanged = 0
    pattern = re.compile(
        rf'https://www\.tiktok\.com/@{re.escape(username)}/video/([0-9]+)(?:[/?#].*)?',
        re.IGNORECASE,
    )
    for _ in range(30):
        await check_page_access(page)
        candidates = await page.eval_on_selector_all('a[href*="/video/"]', '''links =>
            links.map(link => {
                const card = link.closest('[data-e2e="user-post-item"]')
                    || link.closest('div[class*="DivContainer"]') || link;
                const views = card.querySelector('[data-e2e="video-views"]');
                const image = card.querySelector('img');
                return {
                    url: link.href,
                    views: views ? views.textContent.trim() : null,
                    image_url: image ? image.currentSrc || image.src : null
                };
            })''')
        previous_count = len(videos)
        for video in candidates:
            match = pattern.fullmatch(video['url'])
            if match:
                video_id = int(match.group(1))
                video['url'] = f'https://www.tiktok.com/@{username}/video/{video_id}'
                videos[video_id] = video
        unchanged = unchanged + 1 if len(videos) == previous_count else 0
        # Load extra candidates so older pinned posts do not displace recent videos.
        if len(videos) >= 20 or unchanged >= 3:
            break
        await page.mouse.wheel(0, 2000)
        await page.wait_for_timeout(2000)

    # TikTok video IDs encode creation time; grid position can reflect pinning.
    return [videos[video_id] for video_id in sorted(videos, reverse=True)[:10]]

async def get_video_interactions(page, url):
    result = dict.fromkeys(INTERACTION_FIELDS)
    result['Metrics Error'] = ''
    try:
        response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await check_page_access(page, response)
        await page.wait_for_selector(
            '#__UNIVERSAL_DATA_FOR_REHYDRATION__, [data-e2e="like-count"]',
            state='attached', timeout=15000,
        )
        await check_page_access(page)
        expected_id = url.rstrip('/').rsplit('/', 1)[-1]
        actual_id = re.search(r'/video/([0-9]+)', page.url)
        if not actual_id or actual_id.group(1) != expected_id:
            raise ValueError('TikTok redirigio a otra pagina; no se usaran sus contadores.')

        stats = {}
        element = await page.query_selector('#__UNIVERSAL_DATA_FOR_REHYDRATION__')
        if element:
            try:
                data = json.loads(await element.text_content())
                item = data.get('__DEFAULT_SCOPE__', {}).get('webapp.video-detail', {}).get('itemInfo', {}).get('itemStruct', {})
                if str(item.get('id')) == expected_id:
                    stats = {**(item.get('stats') or {}), **(item.get('statsV2') or {})}
            except (ValueError, TypeError, AttributeError):
                pass

        missing = []
        for name, (key, selector) in INTERACTION_FIELDS.items():
            value = stats.get(key)
            if value is None:
                counter = page.locator(f'[data-e2e="{selector}"]').first
                try:
                    value = await counter.inner_text(timeout=3000)
                except Exception:
                    value = None
            try:
                result[name] = convert_views(value)
            except ValueError:
                missing.append(name)
        if missing:
            result['Metrics Error'] = 'Contadores no disponibles: ' + ', '.join(missing)
    except ScrapingRestrictedError:
        raise
    except Exception as error:
        try:
            await check_page_access(page)
        except ValueError:
            pass
        result['Metrics Error'] = f'{type(error).__name__}: {error}'
    return result

async def collect_video_interactions(page, videos):
    results = []
    for index, video in enumerate(videos):
        if index:
            print(f'Esperando {VIDEO_DELAY_SECONDS} segundos antes del siguiente video...')
            await asyncio.sleep(VIDEO_DELAY_SECONDS)
        print(f'Obteniendo interacciones del video {index + 1}/{len(videos)}...')
        try:
            result = await get_video_interactions(page, video['url'])
        except ScrapingRestrictedError as error:
            print(f'Consultas detenidas: {error}')
            results.extend({
                **dict.fromkeys(INTERACTION_FIELDS),
                'Metrics Error': f'Consulta detenida por restriccion: {error}',
            } for _ in videos[index:])
            break
        if result['Metrics Error']:
            print(f"Aviso: {result['Metrics Error']}")
        results.append(result)
    return results

async def scrape_profile(browser, username):
    page = await browser.new_page(locale='en-US')
    response = await page.goto(
        f'https://www.tiktok.com/@{username}', wait_until='domcontentloaded', timeout=30000
    )
    await check_page_access(page, response)

    print(f"Página de {username} cargada correctamente. Obteniendo contenido...")

    recent_videos = await collect_recent_videos(page, username)
    await check_page_access(page)
    if len(recent_videos) < 10:
        print(f'Solo se pudieron obtener {len(recent_videos)} videos; no se completaran con duplicados.')

    today = datetime.today().strftime('%Y-%m-%d')
    folder_name = username
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    video_data = []
    metrics_page = await browser.new_page(locale='en-US')
    interactions_data = await collect_video_interactions(metrics_page, recent_videos)
    for image_counter, video in enumerate(recent_videos, start=1):
        try:
            views_number = convert_views(video['views']) if video['views'] else None
        except ValueError:
            views_number = None
        image_filename = f"{today}_{image_counter}.jpg"
        image_id = None
        if video['image_url']:
            image_id = await download_image(video['image_url'], folder_name, image_filename)
        interactions = interactions_data[image_counter - 1]
        video_data.append({
            'Video Links': video['url'], 'Views': views_number,
            'image_id': image_id or 'Sin id', 'id_post': f"{today}_{image_counter}",
            **interactions,
        })
    await metrics_page.close()

    print(f"Se encontraron {len(video_data)} videos únicos para {username}:")
    for video in video_data:
        print(f"{video['Video Links']} - Likes: {video['Likes']} - Comments: {video['Comments']} - Shares: {video['Shares']} - Saves: {video['Saves']}")

    video_filename = os.path.join(folder_name, f'{username}_post_{today}.xlsx')
    df_videos = pd.DataFrame(video_data, columns=[
        'Video Links', 'Views', 'image_id', 'id_post',
        'Likes', 'Comments', 'Shares', 'Saves', 'Metrics Error',
    ])
    df_videos['id_perfil'] = username
    df_videos.to_excel(video_filename, index=False)
    print(f'Los enlaces de video, sus vistas y los nombres de las imágenes se han guardado en el archivo {video_filename}.')

    followers_element = await page.query_selector('strong[data-e2e="followers-count"]')
    following_element = await page.query_selector('strong[data-e2e="following-count"]')
    likes_element = await page.query_selector('strong[data-e2e="likes-count"]')
    bio_element = await page.query_selector('h2[data-e2e="user-bio"]')
    profile_image_element = await page.query_selector('img[class*="ImgAvatar"]')

    counts = []
    for element in (followers_element, following_element, likes_element):
        try:
            counts.append(convert_views(await element.inner_text()) if element else None)
        except ValueError:
            counts.append(None)
    followers, following, likes = counts
    bio = await bio_element.inner_text() if bio_element else 'N/A'
    profile_image_url = await profile_image_element.get_attribute('src') if profile_image_element else None

    profile_image_filename = None
    if profile_image_url:
        profile_image_filename = await download_image(profile_image_url, folder_name, 'imagen_cover.jpg')

    profile_filename = os.path.join(folder_name, f'{username}_perfil_{today}.xlsx')
    df_profile = pd.DataFrame([{
        'Followers': followers, 
        'Following': following, 
        'Likes': likes, 
        'Bio': bio, 
        'Profile Image': profile_image_filename,
        'id_perfil': username
    }])
    df_profile.to_excel(profile_filename, index=False)
    print(f'La información del perfil se ha guardado en el archivo {profile_filename}.')

async def run(playwright, username):
    browser = await playwright.chromium.launch(headless=False)
    try:
        await scrape_profile(browser, username)
    finally:
        await browser.close()

async def main(username):
    async with async_playwright() as playwright:
        await run(playwright, username)

if __name__ == '__main__':
    try:
        while True:
            try:
                username = normalize_username(input('Usuario de TikTok (con o sin @): '))
                break
            except ValueError as error:
                print(error)
        asyncio.run(main(username))
    except (KeyboardInterrupt, EOFError):
        print('\nEjecucion cancelada.')
    except PlaywrightTimeoutError:
        print('TikTok no respondio a tiempo. Comprueba tu conexion e intenta mas tarde.')
        sys.exit(1)
    except PermissionError:
        print('No se pudo guardar el archivo. Cierra los Excel abiertos y revisa los permisos de la carpeta.')
        sys.exit(1)
    except (ValueError, RuntimeError, PlaywrightError, OSError) as error:
        print(f'No se pudo completar la descarga: {error}')
        sys.exit(1)

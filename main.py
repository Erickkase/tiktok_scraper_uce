import asyncio
import re
from playwright.async_api import async_playwright
import os
import aiohttp
import aiofiles
import pandas as pd
from datetime import datetime

def normalize_username(value):
    username = value.strip().removeprefix('@')
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.]{0,23}', username) or username.endswith('.'):
        raise ValueError(
            'Ingresa un usuario de 1 a 24 caracteres: letras, numeros, puntos o guiones bajos; '
            'sin enlaces ni punto al inicio o al final.'
        )
    return username

def convert_views(views_str):
    if 'K' in views_str:
        return int(float(views_str.replace('K', '')) * 1000)
    elif 'M' in views_str:
        return int(float(views_str.replace('M', '')) * 1000000)
    else:
        return int(views_str)

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
    await page.wait_for_selector('a[href*="/video/"]', timeout=60000)
    videos = {}
    unchanged = 0
    pattern = re.compile(
        rf'https://www\.tiktok\.com/@{re.escape(username)}/video/([0-9]+)(?:[/?#].*)?',
        re.IGNORECASE,
    )
    for _ in range(30):
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

async def run(playwright, username):
    browser = await playwright.chromium.launch(headless=False)
    page = await browser.new_page()
    await page.goto(f'https://www.tiktok.com/@{username}')

    print(f"Página de {username} cargada correctamente. Obteniendo contenido...")

    recent_videos = await collect_recent_videos(page, username)
    if len(recent_videos) < 10:
        print(f'Solo se pudieron obtener {len(recent_videos)} videos; no se completaran con duplicados.')

    today = datetime.today().strftime('%Y-%m-%d')
    folder_name = username
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    video_data = []
    for image_counter, video in enumerate(recent_videos, start=1):
        views_number = convert_views(video['views']) if video['views'] else None
        image_filename = f"{today}_{image_counter}.jpg"
        image_id = None
        if video['image_url']:
            image_id = await download_image(video['image_url'], folder_name, image_filename)
        video_data.append((
            video['url'], views_number, image_id or 'Sin id', f"{today}_{image_counter}"
        ))

    print(f"Se encontraron {len(video_data)} videos únicos para {username}:")
    for link, views, image_id, id_post in video_data:
        print(f"{link} - {views} - {image_id} - {id_post}")

    video_filename = os.path.join(folder_name, f'{username}_post_{today}.xlsx')
    df_videos = pd.DataFrame(video_data, columns=['Video Links', 'Views', 'image_id', 'id_post'])
    df_videos['id_perfil'] = username
    df_videos.to_excel(video_filename, index=False)
    print(f'Los enlaces de video, sus vistas y los nombres de las imágenes se han guardado en el archivo {video_filename}.')

    followers_element = await page.query_selector('strong[data-e2e="followers-count"]')
    following_element = await page.query_selector('strong[data-e2e="following-count"]')
    likes_element = await page.query_selector('strong[data-e2e="likes-count"]')
    bio_element = await page.query_selector('h2[data-e2e="user-bio"]')
    profile_image_element = await page.query_selector('img[class*="ImgAvatar"]')

    followers = convert_views(await followers_element.inner_text()) if followers_element else 'N/A'
    following = convert_views(await following_element.inner_text()) if following_element else 'N/A'
    likes = convert_views(await likes_element.inner_text()) if likes_element else 'N/A'
    bio = await bio_element.inner_text() if bio_element else 'N/A'
    profile_image_url = await profile_image_element.get_attribute('src') if profile_image_element else None

    profile_image_filename = f"imagen_cover.jpg"
    if profile_image_url:
        await download_image(profile_image_url, folder_name, profile_image_filename)

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

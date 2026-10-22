"""Read public TikTok pages without downloading media or issuing API requests."""

import asyncio
import json
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from configuracion import DEFAULT_CONFIG


INTERACTION_FIELDS = {
    'Likes': ('diggCount', 'like-count'),
    'Comments': ('commentCount', 'comment-count'),
    'Shares': ('shareCount', 'share-count'),
    'Saves': ('collectCount', 'favorite-count'),
}


class ScrapingRestrictedError(RuntimeError):
    pass


def normalize_username(value):
    if not isinstance(value, str):
        raise ValueError('El usuario debe ser texto.')
    username = value.strip().removeprefix('@')
    if (not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.]{0,23}', username)
            or username.endswith('.')):
        raise ValueError('Usuario no valido: usa 1 a 24 letras, numeros, puntos o guiones bajos; '
                         'sin punto inicial ni final.')
    return username


def convert_views(value):
    text = str(value).strip().upper().replace(',', '')
    match = re.fullmatch(r'([0-9]+(?:\.[0-9]+)?)([KMB]?)', text)
    if not match or ('.' in match[1] and not match[2]):
        raise ValueError(f'Contador no reconocido: {value}')
    return int(float(match[1]) * {'K': 1000, 'M': 1000000, 'B': 1000000000}[match[2]]) if match[2] else int(match[1])


async def check_page_access(page, response=None):
    if response is not None and response.status in (403, 429):
        raise ScrapingRestrictedError(f'TikTok restringio el acceso (HTTP {response.status}).')
    if response is not None and response.status >= 400:
        raise ValueError(f'Pagina no disponible (HTTP {response.status}).')
    if await page.locator(
        '#captcha_container, #verify-center, iframe[src*="captcha"], [data-e2e="captcha"]'
    ).first.is_visible():
        raise ScrapingRestrictedError('TikTok solicita una verificacion. No se haran mas consultas.')
    if ('/login' in urlsplit(page.url).path or await page.locator(
        '[data-e2e="login-modal"], [role="dialog"] [data-e2e="login-button"]'
    ).first.is_visible()):
        raise ScrapingRestrictedError('TikTok solicita iniciar sesion. No se haran mas consultas.')
    if await page.get_by_text(re.compile(
        r'This account is (?:currently )?private|Esta cuenta es privada', re.I
    )).first.is_visible():
        raise ValueError('El perfil es privado; sus publicaciones no son accesibles.')
    if await page.get_by_text(re.compile(
        r"Couldn't find this account|Account not found|No se pudo encontrar esta cuenta", re.I
    )).first.is_visible():
        raise ValueError('No se encontro la cuenta. Comprueba el nombre de usuario.')


def _canonical_video(url, username):
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(urljoin('https://www.tiktok.com/', url))
        if (parsed.scheme != 'https' or parsed.hostname != 'www.tiktok.com'
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            return None
        match = re.fullmatch(r'/@([^/]+)/video/([0-9]+)/?', parsed.path)
        if match and match[1].lower() == username.lower():
            return f'https://www.tiktok.com/@{username}/video/{int(match[2])}'
    except ValueError:
        pass
    return None


def extract_links_html(html, username):
    """Extract validated public links, including links without a view counter."""
    if not isinstance(html, str):
        return []
    from bs4 import BeautifulSoup

    username = normalize_username(username)
    soup = BeautifulSoup(html, 'html.parser')
    videos = {}
    for link in soup.select('a[href]'):
        url = _canonical_video(link.get('href'), username)
        if not url:
            continue
        card = link.find_parent(attrs={'data-e2e': 'user-post-item'}) or link
        views = card.select_one('[data-e2e="video-views"]')
        videos.setdefault(url, {'url': url, 'views': views.get_text(strip=True) if views else None})
    return list(videos.values())


async def collect_recent_videos(page, username, config=DEFAULT_CONFIG):
    username = normalize_username(username)
    try:
        await page.wait_for_selector('a[href*="/video/"]', timeout=config.selector_timeout)
    except Exception:
        await check_page_access(page)
    videos = {}
    idle = 0
    for turn in range(config.max_scrolls + 1):
        await check_page_access(page)
        previous = len(videos)
        candidates = []
        if config.link_method != 'beautifulsoup':
            try:
                candidates = await page.eval_on_selector_all('a[href*="/video/"]', '''links =>
                    links.map(link => {
                        const card = link.closest('[data-e2e="user-post-item"]') || link;
                        const views = card.querySelector('[data-e2e="video-views"]');
                        return {url: link.getAttribute('href'), views: views ? views.textContent.trim() : null};
                    })''')
            except Exception:
                await check_page_access(page)
                candidates = []
        for candidate in candidates:
            url = _canonical_video(candidate.get('url'), username)
            if url:
                old = videos.get(url)
                views = candidate.get('views')
                videos[url] = {'url': url, 'views': views if isinstance(views, str) else (old or {}).get('views')}
        if (config.link_method == 'beautifulsoup' or
                config.link_method == 'auto' and (len(videos) == previous)):
            await check_page_access(page)
            for candidate in extract_links_html(await page.content(), username):
                if candidate['url'] not in videos or candidate['views'] is not None:
                    videos[candidate['url']] = candidate
        idle = idle + 1 if len(videos) == previous else 0
        if len(videos) >= config.videos * 2 or idle >= config.profile_idle_rounds or turn == config.max_scrolls:
            break
        last = page.locator('a[href*="/video/"]').last
        if await last.is_visible():
            await last.scroll_into_view_if_needed(timeout=config.selector_timeout)
        await page.mouse.wheel(0, 2000)
        await page.wait_for_timeout(config.profile_scroll_wait * 1000)
    result = sorted(videos.values(), key=lambda item: int(item['url'].rsplit('/', 1)[1]), reverse=True)[:config.videos]
    print(f'Se obtuvieron {len(result)} de {config.videos} videos solicitados; la carga puede ser parcial.')
    return result


def _video_id(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname != 'www.tiktok.com'
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            return None
        match = re.fullmatch(r'/@[^/]+/video/([0-9]+)/?', parsed.path)
        return match[1] if match else None
    except (TypeError, ValueError):
        return None


async def get_video_interactions(page, url, config=DEFAULT_CONFIG):
    result = {**dict.fromkeys(INTERACTION_FIELDS), 'Metrics Error': ''}
    navigation_ready = False
    try:
        response = await page.goto(url, wait_until='domcontentloaded', timeout=config.navigation_timeout)
        await check_page_access(page, response)
        expected = _video_id(url)
        if not expected or _video_id(page.url) != expected:
            raise ValueError('TikTok redirigio a otra pagina; no se usaran sus contadores.')
        navigation_ready = True
        try:
            await page.wait_for_function('''expected => {
                try {
                    const data = JSON.parse(document.querySelector('#__UNIVERSAL_DATA_FOR_REHYDRATION__').textContent);
                    const item = data.__DEFAULT_SCOPE__['webapp.video-detail'].itemInfo.itemStruct;
                    const stats = {...item.stats, ...item.statsV2};
                    return String(item.id) === expected &&
                        ['diggCount', 'commentCount', 'shareCount', 'collectCount'].every(key => stats[key] != null);
                } catch (_) { return false; }
            }''', arg=expected, timeout=min(config.selector_timeout, 3000))
        except Exception:
            pass
        await check_page_access(page)
        if _video_id(page.url) != expected:
            navigation_ready = False
            raise ValueError('TikTok redirigio a otra pagina; no se usaran sus contadores.')
        stats = {}
        element = await page.query_selector('#__UNIVERSAL_DATA_FOR_REHYDRATION__')
        if element:
            try:
                data = json.loads(await element.text_content())
                item = data.get('__DEFAULT_SCOPE__', {}).get('webapp.video-detail', {}).get('itemInfo', {}).get('itemStruct', {})
                if str(item.get('id')) == expected:
                    stats = {**(item.get('stats') or {}), **(item.get('statsV2') or {})}
            except (ValueError, TypeError, AttributeError):
                pass
        missing = []
        for name, (key, selector) in INTERACTION_FIELDS.items():
            value = stats.get(key)
            if value is None:
                try:
                    value = await page.locator(f'[data-e2e="{selector}"]').first.inner_text(timeout=min(config.selector_timeout, 3000))
                except Exception:
                    value = None
            try:
                result[name] = convert_views(value)
            except ValueError:
                missing.append(name)
        if missing:
            result['Metrics Error'] = 'Contadores no disponibles: ' + ', '.join(missing)
    except ScrapingRestrictedError as error:
        error.metrics = result
        raise
    except Exception as error:
        try:
            await check_page_access(page)
        except ScrapingRestrictedError as restricted:
            restricted.metrics = result
            raise
        except ValueError:
            pass
        result['Metrics Error'] = f'{type(error).__name__}: {error}'
        if not navigation_ready:
            result['_navigation_failed'] = True
    return result


class CommentCollector:
    """Observe native public responses; never initiate comment API requests."""

    def __init__(self, page, url, config=DEFAULT_CONFIG):
        self.page, self.url, self.config = page, url, config
        self.expected_id = _video_id(url)
        self.rows = {}
        self.batches = []
        self.observed = {}
        self.tasks = []
        self.next_sequence = 0
        self.processed = 0
        self.error = ''
        self.warning = ''
        self.restricted = False
        self.navigation_status = None
        self.has_more = None
        self.cursor = -1
        self.empty_evidence = False
        self.deadline = None

    async def __aenter__(self):
        self.deadline = asyncio.get_running_loop().time() + self.config.comment_deadline
        self.page.on('response', self.on_response)
        return self

    def remaining(self):
        return max(0, self.deadline - asyncio.get_running_loop().time())

    def on_response(self, response):
        try:
            parsed = urlsplit(response.url)
            query = parse_qs(parsed.query)
            if (parsed.scheme != 'https' or parsed.hostname != 'www.tiktok.com'
                    or parsed.port not in (None, 443)
                    or parsed.username is not None or parsed.password is not None):
                return
            # Chromium can emit the HTTP response, then raise from goto without returning it.
            if (response.request.resource_type == 'document'
                    and response.frame == self.page.main_frame
                    and _video_id(response.url) == self.expected_id):
                self.navigation_status = response.status
                if response.status in (403, 429):
                    self.restricted = True
                    self.error = f'TikTok rechazo la pagina del video (HTTP {response.status}); consultas detenidas.'
                return
            if (parsed.path not in ('/api/comment/list', '/api/comment/list/')
                    or query.get('aweme_id') != [self.expected_id]):
                return
        except ValueError:
            return
        # Sequence is allocated synchronously, before JSON readers can finish out of order.
        sequence = self.next_sequence
        self.next_sequence += 1
        if response.status in (403, 429):
            self.restricted = True
            self.error = f'TikTok restringio los comentarios (HTTP {response.status}).'
        self.tasks.append(asyncio.create_task(self._read(response, query, sequence)))

    async def _read(self, response, query, sequence):
        try:
            if response.status >= 400:
                return sequence, query, None, f'No se cargaron los comentarios (HTTP {response.status}).'
            data = await asyncio.wait_for(response.json(), timeout=min(self.config.response_timeout, self.remaining()))
            if not isinstance(data, dict) or not isinstance(data.get('comments'), list):
                if isinstance(data, dict) and data.get('status_code', 0):
                    raise ValueError(f"TikTok no entrego comentarios (codigo {data['status_code']}).")
                raise ValueError('Respuesta de comentarios vacia o no valida.')
            if data.get('status_code', 0):
                raise ValueError(f"TikTok no entrego comentarios (codigo {data['status_code']}).")
            return sequence, query, data, ''
        except Exception as error:
            return sequence, query, None, f'Una respuesta de comentarios no se pudo leer: {type(error).__name__}: {error}'

    def _process_ready(self):
        while self.processed < len(self.tasks) and self.tasks[self.processed].done():
            task = self.tasks[self.processed]
            self.processed += 1
            if task.cancelled():
                continue
            sequence, query, data, warning = task.result()
            if warning:
                self.warning = warning
                continue
            self.warning = ''
            items = data['comments']
            ids = []
            for item in items:
                if not isinstance(item, dict) or str(item.get('aweme_id')) != self.expected_id:
                    continue
                if any(item.get(key) not in (None, 0, '0') for key in ('reply_id', 'reply_to_reply_id')):
                    continue
                cid, text = item.get('cid'), item.get('text')
                if (type(cid) not in (str, int) or not re.fullmatch(r'[0-9]+', str(cid))
                        or not isinstance(text, str) or not text.strip()):
                    continue
                cid = str(cid)
                ids.append(cid)
                if cid in self.observed:
                    continue
                author = item.get('user') or {}
                if not isinstance(author, dict):
                    author = {}
                handle = author.get('unique_id') or author.get('uniqueId') or None
                if not isinstance(handle, str):
                    handle = None
                nickname = author.get('nickname')
                if not isinstance(nickname, str):
                    nickname = None
                try:
                    likes = convert_views(item.get('digg_count'))
                except ValueError:
                    likes = None
                self.observed[cid] = {
                    'Comment ID': cid, 'Author': nickname or handle,
                    'Author Handle': handle, 'Comment Text': text, 'Comment Likes': likes,
                }
            try:
                cursor = int(query.get('cursor', [data.get('cursor', 0)])[0])
            except (ValueError, TypeError):
                cursor = 0
            self.batches.append((cursor, sequence, ids))
            if cursor >= self.cursor:
                self.cursor = cursor
                self.has_more = data.get('has_more') not in (0, False) if 'has_more' in data else None
                self.empty_evidence = not items and self.has_more is False
        # Headers and JSON can both arrive out of page order. Rebuild the prefix
        # by request cursor, keeping the first observed version of each real ID.
        rows = {}
        for _, _, ids in sorted(self.batches):
            for cid in ids:
                if cid not in rows and len(rows) < self.config.comments:
                    rows[cid] = self.observed[cid]
        self.rows = rows

    async def settle(self):
        pending = [task for task in self.tasks if not task.done()]
        if pending and self.remaining() > 0:
            await asyncio.wait(pending, timeout=min(self.config.response_timeout, self.remaining()))
        self._process_ready()

    async def __aexit__(self, exc_type, exc, traceback):
        self.page.remove_listener('response', self.on_response)
        # Keep already-read responses, then stop every remaining reader before another video.
        try:
            if exc_type is None:
                await self.settle()
        finally:
            for task in self.tasks:
                if not task.done():
                    task.cancel()
            if self.tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self.tasks, return_exceptions=True),
                        timeout=max(0.001, self.remaining()),
                    )
                except asyncio.TimeoutError:
                    pass
            self._process_ready()

    def result(self, reported_count=None):
        rows = list(self.rows.values())
        error = self.error or (self.warning if len(rows) < self.config.comments else '')
        if self.restricted:
            status = 'restringido'
        elif len(rows) >= self.config.comments and not self.error:
            status = 'completo'
        elif not rows and not error and (reported_count == 0 or self.empty_evidence and not reported_count):
            status = 'sin_comentarios'
        elif rows:
            status = 'parcial'
        else:
            status = 'error'
        if status in ('parcial', 'error'):
            reason = ('TikTok indico que no hay mas comentarios principales disponibles; '
                      'el contador total puede incluir respuestas.') if self.has_more is False and rows else 'Carga publica incompleta.'
            error = f'Se obtuvieron {len(rows)} de {self.config.comments} comentarios. ' + (error or reason)
        return {'rows': rows, 'error': error, 'restricted': self.restricted, 'status': status}


async def get_video_comments(page, url, config=DEFAULT_CONFIG, collector=None, reported_count=None):
    if collector is None:
        async with CommentCollector(page, url, config) as owned:
            await get_video_comments(page, url, config, owned, reported_count)
        return owned.result(reported_count)

    async def collect():
        if not collector.expected_id or _video_id(page.url) != collector.expected_id:
            raise ValueError('No se leeran comentarios de una pagina distinta al video solicitado.')
        await check_page_access(page)
        await collector.settle()
        if collector.restricted or len(collector.rows) >= config.comments:
            return
        if reported_count == 0 and not collector.rows:
            return
        if collector.empty_evidence and not collector.rows and reported_count is None:
            return
        panel = page.locator('[data-e2e="comment-list"], [data-e2e="comment-level-1"], [class*="DivCommentMain"]').first
        if not await panel.is_visible():
            try:
                await page.locator('[data-e2e="comment-icon"]').first.click(timeout=min(config.selector_timeout, 10000))
            except Exception as error:
                collector.warning = f'No se pudo abrir el panel: {type(error).__name__}: {error}'
        idle = 0
        for _ in range(config.comment_rounds):
            previous = len(collector.rows)
            await page.wait_for_timeout(config.comment_wait * 1000)
            await collector.settle()
            await check_page_access(page)
            if collector.restricted or len(collector.rows) >= config.comments:
                break
            if collector.has_more is False and collector.rows:
                break
            if collector.empty_evidence and not collector.rows and reported_count in (None, 0):
                break
            # Before the first real comment, allow the site's delayed native retry.
            idle = idle + 1 if collector.rows and len(collector.rows) == previous else 0
            if idle >= config.comment_idle_rounds:
                break
            await page.evaluate('''() => {
                let node = document.querySelector('[data-e2e="comment-level-1"], [class*="DivCommentMain"]');
                while (node && node !== document.body) {
                    if (node.scrollHeight > node.clientHeight && /auto|scroll/.test(getComputedStyle(node).overflowY)) {
                        node.scrollTop = node.scrollHeight; return;
                    }
                    node = node.parentElement;
                }
            }''')

    try:
        remaining = collector.remaining()
        if remaining <= 0:
            raise asyncio.TimeoutError()
        await asyncio.wait_for(collect(), timeout=remaining)
    except ScrapingRestrictedError as error:
        collector.restricted, collector.error = True, str(error)
    except Exception as error:
        collector.error = f'No se pudieron cargar comentarios: {type(error).__name__}: {error}'
    return collector.result(reported_count)


async def collect_video_interactions(page, videos, config=DEFAULT_CONFIG):
    results = []
    restriction = ''
    navigation_abort = ''
    for index, video in enumerate(videos):
        if restriction or navigation_abort:
            reason = (f'Consulta detenida por restriccion: {restriction}' if restriction else
                      f'No consultado tras rechazo de navegacion sin codigo HTTP confirmado: {navigation_abort}')
            results.append({
                **dict.fromkeys(INTERACTION_FIELDS), 'Metrics Error': reason,
                'Comments Collected': None, 'Comments Status': 'restringido' if restriction else 'error',
                'Comments Error': reason, '_comment_rows': [],
            })
            continue
        if index:
            await asyncio.sleep(max(2, config.video_delay))
        print(f'Video {index + 1}/{len(videos)}: obteniendo metricas y comentarios...')
        metrics = {**dict.fromkeys(INTERACTION_FIELDS), 'Metrics Error': ''}
        async with CommentCollector(page, video['url'], config) as collector:
            try:
                metrics = await get_video_interactions(page, video['url'], config)
                if metrics.get('_navigation_failed') or collector.restricted:
                    original = metrics.get('Metrics Error') or 'La pagina del video no se pudo abrir.'
                    if collector.navigation_status is not None:
                        original = f'HTTP {collector.navigation_status} al abrir el video. {original}'
                    metrics['Metrics Error'] = original
                    if not collector.restricted:
                        collector.error = f'Comentarios no consultados porque fallo la navegacion: {original}'
                        if (collector.navigation_status is None
                                and 'net::ERR_HTTP_RESPONSE_CODE_FAILURE' in original):
                            navigation_abort = original
                else:
                    await get_video_comments(page, video['url'], config, collector, metrics.get('Comments'))
            except ScrapingRestrictedError as error:
                metrics.update(getattr(error, 'metrics', {}))
                metrics['Metrics Error'] = f'Consulta detenida por restriccion: {error}'
                collector.restricted, collector.error = True, str(error)
            except Exception as error:
                metrics['Metrics Error'] = f'{type(error).__name__}: {error}'
                collector.error = metrics['Metrics Error']
        comments = collector.result(metrics.get('Comments'))
        if comments['restricted']:
            restriction = comments['error']
        metrics.update({
            'Comments Collected': len(comments['rows']), 'Comments Status': comments['status'],
            'Comments Error': comments['error'], '_comment_rows': comments['rows'],
        })
        results.append(metrics)
        print(f"Comentarios: {len(comments['rows'])}/{config.comments}; estado: {comments['status']}.")
        if comments['error']:
            print(f"Aviso: {comments['error']}")
        if restriction:
            print('No se consultaran los videos restantes debido a la restriccion.')
        elif navigation_abort:
            print('No se repetiran las consultas tras el rechazo de navegacion; no se confirmo un codigo HTTP.')
    return results


async def scrape_profile(browser, username, config=DEFAULT_CONFIG):
    username = normalize_username(username)
    page = await browser.new_page(locale='en-US')
    try:
        response = await page.goto(f'https://www.tiktok.com/@{username}', wait_until='domcontentloaded', timeout=config.navigation_timeout)
        await check_page_access(page, response)
        profile = {'id_perfil': username, 'Profile Error': ''}
        try:
            await page.wait_for_selector(
                '[data-e2e="followers-count"], [data-e2e="user-bio"]',
                state='attached', timeout=config.selector_timeout,
            )
        except Exception as error:
            profile['Profile Error'] = f'Perfil parcial: no se cargaron los datos del perfil: {type(error).__name__}: {error}'
        await check_page_access(page)
        for name, selector in (('Followers', 'followers-count'), ('Following', 'following-count'), ('Likes', 'likes-count')):
            element = await page.query_selector(f'[data-e2e="{selector}"]')
            try:
                profile[name] = convert_views(await element.inner_text()) if element else None
            except ValueError:
                profile[name] = None
        bio = await page.query_selector('[data-e2e="user-bio"]')
        profile['Bio'] = await bio.inner_text() if bio else None
        videos = await collect_recent_videos(page, username, config)
        interactions = await collect_video_interactions(page, videos, config)
        posts, comments = [], []
        for video, interaction in zip(videos, interactions):
            video_id = _video_id(video['url'])
            try:
                views = convert_views(video['views'])
            except ValueError:
                views = None
            comments.extend({**row, 'Video Links': video['url'], 'Video ID': video_id, 'id_perfil': username}
                            for row in interaction['_comment_rows'])
            posts.append({
                'Video Links': video['url'], 'Video ID': video_id, 'Views': views,
                'id_post': video_id, 'id_perfil': username,
                **{key: value for key, value in interaction.items() if not key.startswith('_')},
            })
        return profile, posts, comments
    finally:
        await page.close()


async def run(playwright, username, config=DEFAULT_CONFIG):
    username = normalize_username(username)
    browser = await playwright.chromium.launch(headless=config.headless)
    try:
        return await scrape_profile(browser, username, config)
    finally:
        await browser.close()

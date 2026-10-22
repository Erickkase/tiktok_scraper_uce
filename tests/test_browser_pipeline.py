"""Real Chromium against intercepted fixtures; never contacts TikTok."""

import asyncio
import html
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from openpyxl import load_workbook
from playwright.async_api import async_playwright

from configuracion import ScraperConfig
from exportacion import _restore_text
from main import execute
from scraper import scrape_profile


class BrowserPipelineTests(unittest.TestCase):
    def test_video_http_403_stops_before_next_video_and_exports_restriction(self):
        visits = []

        async def collect_fixture(user, config):
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(locale='en-US')

                async def respond(route):
                    from urllib.parse import urlsplit
                    path = urlsplit(route.request.url).path
                    if '/video/' in path:
                        visits.append(path)
                        await route.fulfill(status=403, content_type='text/html', body='Acceso rechazado')
                        return
                    if path == '/@demo':
                        body = '<strong data-e2e=followers-count>10</strong><h2 data-e2e=user-bio>Soy creativa</h2>'
                        for number in range(1, 5):
                            body += '<a href=/@demo/video/' + str(number) + '>video</a>'
                        await route.fulfill(content_type='text/html', body=body)
                        return
                    await route.fulfill(status=404)

                await context.route('**/*', respond)

                async def new_page(**kwargs):
                    return await context.new_page()

                try:
                    return await scrape_profile(SimpleNamespace(new_page=new_page), user, config)
                finally:
                    await browser.close()

        config = ScraperConfig(videos=2, comments=20, headless=True,
                               selector_timeout=3000, navigation_timeout=5000)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch('main.collect', side_effect=collect_fixture):
                paths = execute('demo', config, directory)
            posts = pd.read_excel(paths['posts'], keep_default_na=False)
            self.assertEqual(posts['Comments Status'].tolist(), ['restringido', 'restringido'])
            self.assertEqual(posts['Comments Collected'].tolist(), [0, ''])
            self.assertIn('HTTP 403', posts['Metrics Error'].iloc[0])
            self.assertNotIn('pagina distinta', posts['Comments Error'].iloc[0])
            self.assertNotIn('_navigation_failed', posts.columns)
            comments = pd.read_excel(paths['comentarios'])
            self.assertEqual(len(comments), 0)
        self.assertEqual(visits, ['/@demo/video/4'])

    def test_intercepted_profile_comments_and_automatic_analysis(self):
        visits = []
        ids = ['7694797676306615583', '7693184538704416031']
        username = 'demo'
        bio = 'Soy creativa y me encanta aprender cosas nuevas'

        async def collect_fixture(user, config):
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context(locale='en-US')

                async def respond(route):
                    from urllib.parse import parse_qs, urlsplit
                    parsed = urlsplit(route.request.url)
                    if parsed.path == '/api/comment/list/':
                        video_id = parse_qs(parsed.query)['aweme_id'][0]
                        count = 20 if video_id == ids[0] else 12
                        comments = [{
                            'cid': str(int(video_id) + index), 'aweme_id': video_id,
                            'reply_id': '0', 'digg_count': index,
                            'text': ('Soy sociable' if index else '=1+1') if video_id == ids[0] else 'Buen video',
                            'user': {'unique_id': 'demo' if index == 1 else 'audiencia', 'nickname': 'Nombre publico'},
                        } for index in range(count)]
                        await route.fulfill(content_type='application/json', body=json.dumps({
                            'status_code': 0, 'comments': comments, 'has_more': 0,
                        }))
                        return
                    if '/video/' in parsed.path:
                        video_id = parsed.path.rsplit('/', 1)[-1]
                        visits.append((video_id, time.monotonic()))
                        item = {'id': video_id, 'stats': {
                            'diggCount': 12, 'commentCount': 100 if video_id == ids[0] else 12,
                            'shareCount': 1, 'collectCount': 2,
                        }}
                        data = {'__DEFAULT_SCOPE__': {'webapp.video-detail': {'itemInfo': {'itemStruct': item}}}}
                        # Starts before DOMContentLoaded, earlier than the comments-panel function.
                        body = '<script id=__UNIVERSAL_DATA_FOR_REHYDRATION__ type=application/json>' + json.dumps(data) + '</script>'
                        body += '<div data-e2e=comment-list>Comentarios</div><script>fetch("/api/comment/list/?aweme_id=' + video_id + '&cursor=0")</script>'
                        await route.fulfill(content_type='text/html', body=body)
                        return
                    if parsed.path == '/@demo':
                        body = '<strong data-e2e=followers-count>100</strong><strong data-e2e=following-count>7</strong>'
                        body += '<strong data-e2e=likes-count>200</strong><h2 data-e2e=user-bio>' + html.escape(bio) + '</h2>'
                        for video_id in ['1', *ids, '7000000000000000000']:
                            body += '<div data-e2e=user-post-item><a href=/@demo/video/' + video_id + '>video</a><strong data-e2e=video-views>123</strong></div>'
                        await route.fulfill(content_type='text/html', body=body)
                        return
                    await route.fulfill(status=404, body='Fixture desconocida')

                await context.route('**/*', respond)

                async def new_page(**kwargs):
                    return await context.new_page()

                try:
                    return await scrape_profile(SimpleNamespace(new_page=new_page), user, config)
                finally:
                    await browser.close()

        config = ScraperConfig(videos=2, comments=20, headless=True,
                               selector_timeout=3000, navigation_timeout=5000, comment_deadline=15)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            with patch('main.collect', side_effect=collect_fixture):
                paths = execute(username, config, directory)
            posts = pd.read_excel(paths['posts'], dtype={'Video ID': str}, keep_default_na=False)
            self.assertEqual(posts['Video ID'].tolist(), ids)
            self.assertEqual(posts['Comments Collected'].tolist(), [20, 12])
            self.assertEqual(posts['Comments Status'].tolist(), ['completo', 'parcial'])
            comments = pd.read_excel(paths['comentarios'], dtype=str, keep_default_na=False)
            self.assertEqual(len(comments), 32)
            self.assertEqual(comments['Comment ID'].nunique(), 32)
            book = load_workbook(paths['bigfive'])
            self.assertEqual(book.sheetnames, ['Biografia', 'Comentarios_Analizados',
                                             'Resultados_por_Video', 'Resumen_General', 'Metodologia'])
            analyzed = book['Comentarios_Analizados']
            header = {cell.value: cell.column for cell in analyzed[1]}
            first_text = analyzed.cell(2, header['Comment Text'])
            self.assertEqual(first_text.value, '=1+1')
            self.assertEqual(first_text.data_type, 's')
            self.assertEqual(analyzed.max_row - 1, 32)
            self.assertEqual(book['Biografia']['B2'].value, bio)
            book.close()
        self.assertEqual([video_id for video_id, _ in visits], ids)
        self.assertGreaterEqual(visits[1][1] - visits[0][1], 2)


if __name__ == '__main__':
    unittest.main()

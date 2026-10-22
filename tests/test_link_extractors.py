import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

from configuracion import DEFAULT_CONFIG
from scraper import ScrapingRestrictedError, collect_recent_videos, extract_links_html


class LinkTests(unittest.TestCase):
    def test_non_html_mock_content_is_ignored(self):
        for html in (None, MagicMock(), b'<a href="/@demo/video/1">x</a>'):
            self.assertEqual(extract_links_html(html, 'demo'), [])

    def test_html_relative_aliases_hosts_credentials_and_missing_views(self):
        html = '''<div data-e2e="user-post-item"><a href="/@demo/video/001?track=yes">x</a>
        <strong data-e2e="video-views">0</strong></div>
        <a href="https://www.tiktok.com/@DEMO/video/1#alias">same</a>
        <a href="/@demo/video/2">no views</a>
        <a href="https://evil.test/@demo/video/3">bad</a>
        <a href="https://www.tiktok.com.evil.test/@demo/video/4">bad</a>
        <a href="https://user@www.tiktok.com/@demo/video/5">bad</a>
        <a href="/@other/video/6">bad</a><a href="/@demo/video/not-id">bad</a>'''
        self.assertEqual(extract_links_html(html, 'demo'), [
            {'url': 'https://www.tiktok.com/@demo/video/1', 'views': '0'},
            {'url': 'https://www.tiktok.com/@demo/video/2', 'views': None},
        ])


class LinkFallbackTests(unittest.IsolatedAsyncioTestCase):
    def page(self):
        page = AsyncMock()
        last = AsyncMock()
        last.is_visible.return_value = False
        page.locator = MagicMock(return_value=MagicMock(last=last))
        page.content.return_value = '<a href="/@demo/video/9">valid</a>'
        return page

    async def test_auto_bs_rescues_playwright_error(self):
        page = self.page()
        page.eval_on_selector_all.side_effect = RuntimeError('JS failed')
        with patch('scraper.check_page_access', new_callable=AsyncMock):
            result = await collect_recent_videos(page, 'demo')
        self.assertEqual(result, [{'url': 'https://www.tiktok.com/@demo/video/9', 'views': None}])
        self.assertGreater(page.content.await_count, 0)

    async def test_auto_bs_rescues_invalid_candidates_and_stagnation(self):
        for candidates in ([{'url': 'https://evil.test/@demo/video/100'}],
                           [{'url': '/@demo/video/1', 'views': None}]):
            page = self.page()
            page.eval_on_selector_all.return_value = candidates
            with patch('scraper.check_page_access', new_callable=AsyncMock):
                result = await collect_recent_videos(page, 'demo')
            self.assertEqual(result[0]['url'], 'https://www.tiktok.com/@demo/video/9')

    async def test_explicit_methods_and_configured_pinned_buffer(self):
        for method in ('playwright', 'beautifulsoup'):
            page = self.page()
            ids = (1, 2, 30, 29, 28, 27)
            page.eval_on_selector_all.return_value = [{'url': f'/@demo/video/{n}?q=x'} for n in ids]
            page.content.return_value = ''.join(f'<a href="/@demo/video/{n}">x</a>' for n in ids)
            config = replace(DEFAULT_CONFIG, videos=3, link_method=method)
            with patch('scraper.check_page_access', new_callable=AsyncMock):
                result = await collect_recent_videos(page, 'demo', config)
            self.assertEqual([row['url'].rsplit('/', 1)[1] for row in result], ['30', '29', '28'])
            page.mouse.wheel.assert_not_awaited()
            if method == 'playwright':
                page.content.assert_not_awaited()
            else:
                page.eval_on_selector_all.assert_not_awaited()

    async def test_max_scrolls_is_hard_limit(self):
        page = self.page()
        page.eval_on_selector_all.side_effect = [[{'url': f'/@demo/video/{n}'}] for n in range(1, 4)]
        config = replace(DEFAULT_CONFIG, max_scrolls=2, link_method='playwright')
        with patch('scraper.check_page_access', new_callable=AsyncMock):
            result = await collect_recent_videos(page, 'demo', config)
        self.assertEqual(len(result), 3)
        self.assertEqual(page.mouse.wheel.await_count, 2)
        self.assertTrue(all(call.args == (3000,) for call in page.wait_for_timeout.await_args_list))

    async def test_playwright_error_rechecks_access_before_html_fallback(self):
        page = self.page()
        page.eval_on_selector_all.side_effect = RuntimeError('Page changed')
        with patch('scraper.check_page_access', new=AsyncMock(side_effect=[
            None, ScrapingRestrictedError('CAPTCHA visible'),
        ])), patch('scraper.extract_links_html') as extract:
            with self.assertRaisesRegex(ScrapingRestrictedError, 'CAPTCHA'):
                await collect_recent_videos(page, 'demo')
        page.content.assert_not_awaited()
        extract.assert_not_called()

    async def test_invalid_page_content_does_not_reach_beautifulsoup(self):
        page = self.page()
        page.eval_on_selector_all.return_value = []
        page.content.return_value = MagicMock()
        with patch('scraper.check_page_access', new_callable=AsyncMock):
            self.assertEqual(await collect_recent_videos(page, 'demo'), [])
        self.assertEqual(page.content.await_count, DEFAULT_CONFIG.profile_idle_rounds)

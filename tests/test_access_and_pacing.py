import asyncio
import time
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from configuracion import DEFAULT_CONFIG
from scraper import (
    ScrapingRestrictedError, check_page_access,
    collect_recent_videos, collect_video_interactions, run,
)


def accessible_page():
    page = AsyncMock()
    page.url = 'https://www.tiktok.com/@demo'
    hidden = AsyncMock()
    hidden.is_visible.return_value = False
    page.locator = MagicMock(return_value=MagicMock(first=hidden, last=hidden))
    page.get_by_text = MagicMock(return_value=MagicMock(first=hidden))
    page.on = MagicMock()
    page.remove_listener = MagicMock()
    return page


class AccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_restrictions_stop_scraping(self):
        for status in (403, 429):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ScrapingRestrictedError, str(status)):
                    await check_page_access(accessible_page(), MagicMock(status=status))

    async def test_visible_captcha_stops_scraping(self):
        page = accessible_page()
        page.locator.return_value.first.is_visible.return_value = True
        with self.assertRaisesRegex(ScrapingRestrictedError, 'verificacion'):
            await check_page_access(page)

    async def test_private_profile_has_clear_message(self):
        page = accessible_page()
        private = AsyncMock()
        private.is_visible.return_value = True
        page.get_by_text.return_value = MagicMock(first=private)
        with self.assertRaisesRegex(ValueError, 'privado'):
            await check_page_access(page)

    async def test_missing_account_has_clear_message(self):
        page = accessible_page()
        hidden = AsyncMock()
        hidden.is_visible.return_value = False
        visible = AsyncMock()
        visible.is_visible.return_value = True
        page.get_by_text.side_effect = [MagicMock(first=hidden), MagicMock(first=visible)]
        with self.assertRaisesRegex(ValueError, 'No se encontro'):
            await check_page_access(page)

    async def test_no_loaded_videos_returns_empty_not_invented_data(self):
        page = accessible_page()
        page.wait_for_selector.side_effect = PlaywrightTimeoutError('No videos')
        page.eval_on_selector_all.return_value = []
        page.content.return_value = ''
        self.assertEqual(await collect_recent_videos(page, 'demo', replace(DEFAULT_CONFIG, link_method='playwright')), [])

    async def test_browser_closes_on_error_or_cancellation(self):
        for error in (ValueError('Fallo'), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                playwright = AsyncMock()
                browser = playwright.chromium.launch.return_value
                with patch('scraper.scrape_profile', new=AsyncMock(side_effect=error)):
                    with self.assertRaises(type(error)):
                        await run(playwright, 'demo')
                browser.close.assert_awaited_once()


class PacingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        comments = patch('scraper.get_video_comments', new_callable=AsyncMock)
        comments.start().return_value = {'rows': [], 'error': '', 'restricted': False}
        self.addCleanup(comments.stop)

    async def test_wait_occurs_between_videos_not_before_first_or_after_last(self):
        events = []

        async def metrics(page, url, config):
            events.append(url)
            return {'Likes': 1, 'Metrics Error': ''}

        async def sleep(seconds):
            self.assertGreaterEqual(seconds, 2)
            events.append('wait')

        videos = [{'url': f'https://www.tiktok.com/@demo/video/{n}'} for n in (1, 2, 3)]
        with patch('scraper.get_video_interactions', side_effect=metrics):
            with patch('scraper.asyncio.sleep', side_effect=sleep):
                self.assertEqual(len(await collect_video_interactions(accessible_page(), videos)), 3)
        self.assertEqual(events, [videos[0]['url'], 'wait', videos[1]['url'], 'wait', videos[2]['url']])

    async def test_real_minimum_delay_between_two_queries(self):
        times = []

        async def metrics(page, url, config):
            times.append(time.monotonic())
            return {'Metrics Error': ''}

        with patch('scraper.get_video_interactions', side_effect=metrics):
            await collect_video_interactions(accessible_page(), [{'url': 'one'}, {'url': 'two'}])
        self.assertGreaterEqual(DEFAULT_CONFIG.video_delay, 2)
        self.assertGreaterEqual(times[1] - times[0], 2)

    async def test_wait_still_applies_after_recoverable_video_error(self):
        with patch('scraper.get_video_interactions', new_callable=AsyncMock) as metrics:
            metrics.side_effect = [{'Metrics Error': 'No disponible'}, {'Metrics Error': ''}]
            with patch('scraper.asyncio.sleep', new_callable=AsyncMock) as sleep:
                await collect_video_interactions(accessible_page(), [{'url': 'one'}, {'url': 'two'}])
            sleep.assert_awaited_once_with(DEFAULT_CONFIG.video_delay)

    async def test_restriction_preserves_results_and_skips_remaining_queries(self):
        with patch('scraper.get_video_interactions', new_callable=AsyncMock) as metrics:
            metrics.side_effect = [
                {'Likes': 42, 'Metrics Error': ''}, ScrapingRestrictedError('HTTP 429'),
            ]
            with patch('scraper.asyncio.sleep', new_callable=AsyncMock):
                results = await collect_video_interactions(
                    accessible_page(), [{'url': 'one'}, {'url': 'two'}, {'url': 'three'}]
                )
            self.assertEqual(metrics.await_count, 2)
            self.assertEqual(results[0]['Likes'], 42)
            self.assertEqual(len(results), 3)
            self.assertIsNone(results[2]['Likes'])
            self.assertIn('restriccion', results[2]['Metrics Error'])


if __name__ == '__main__':
    unittest.main()

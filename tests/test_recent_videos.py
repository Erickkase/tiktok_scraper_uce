import unittest
from unittest.mock import AsyncMock, patch

from main import collect_recent_videos


def video(video_id, username='demo', suffix=''):
    return {
        'url': f'https://www.tiktok.com/@{username}/video/{video_id}{suffix}',
        'views': None,
        'image_url': None,
    }


class RecentVideosTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        access_check = patch('main.check_page_access', new_callable=AsyncMock)
        access_check.start()
        self.addCleanup(access_check.stop)

    async def test_returns_ten_newest_not_old_pinned_posts(self):
        page = AsyncMock()
        page.eval_on_selector_all.return_value = [video(1), video(2)] + [
            video(number) for number in range(30, 10, -1)
        ]
        result = await collect_recent_videos(page, 'demo')
        self.assertEqual(result, [video(number) for number in range(30, 20, -1)])
        page.mouse.wheel.assert_not_awaited()

    async def test_accumulates_scrolls_and_deduplicates_tracking_urls(self):
        page = AsyncMock()
        first = [video(number) for number in range(10, 0, -1)]
        second = [video(10, suffix='?source=profile')] + [
            video(number) for number in range(20, 10, -1)
        ]
        page.eval_on_selector_all.side_effect = [first, second]
        result = await collect_recent_videos(page, 'demo')
        self.assertEqual(result, [video(number) for number in range(20, 10, -1)])
        page.mouse.wheel.assert_awaited_once()

    async def test_fewer_than_ten_keeps_missing_views_and_images(self):
        page = AsyncMock()
        page.eval_on_selector_all.return_value = [video(9), video(10), video(9)]
        result = await collect_recent_videos(page, 'demo')
        self.assertEqual(result, [video(10), video(9)])
        self.assertEqual(page.eval_on_selector_all.await_count, 4)

    async def test_ignores_other_profiles_hosts_and_invalid_ids(self):
        page = AsyncMock()
        page.eval_on_selector_all.return_value = [
            video(5), video(99, username='other'), video('invalid'),
            {'url': 'https://example.com/@demo/video/100'},
            video(100, username='demo.extra'),
        ]
        self.assertEqual(await collect_recent_videos(page, 'demo'), [video(5)])

    async def test_empty_results_stop_after_three_reads(self):
        page = AsyncMock()
        page.eval_on_selector_all.return_value = []
        self.assertEqual(await collect_recent_videos(page, 'demo'), [])
        self.assertEqual(page.eval_on_selector_all.await_count, 3)

    async def test_numeric_sort_not_lexicographic(self):
        page = AsyncMock()
        page.eval_on_selector_all.return_value = [video(9), video(100), video(10)]
        self.assertEqual(
            await collect_recent_videos(page, 'demo'), [video(100), video(10), video(9)]
        )


if __name__ == '__main__':
    unittest.main()

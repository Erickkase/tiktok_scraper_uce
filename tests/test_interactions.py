import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from main import ScrapingRestrictedError, convert_views, get_video_interactions


URL = 'https://www.tiktok.com/@demo/video/123'


def make_page(stats=None, item_id='123', dom=None):
    page = AsyncMock()
    page.url = URL
    page.goto.return_value = MagicMock(status=200)
    page.query_selector.return_value = None
    notice = AsyncMock()
    notice.is_visible.return_value = False
    page.get_by_text = MagicMock(return_value=MagicMock(first=notice))
    if stats is not None:
        element = AsyncMock()
        element.text_content.return_value = json.dumps({
            '__DEFAULT_SCOPE__': {'webapp.video-detail': {'itemInfo': {
                'itemStruct': {'id': item_id, 'statsV2': stats}
            }}}
        })
        page.query_selector.return_value = element

    def locator(selector):
        counter = AsyncMock()
        counter.is_visible.return_value = False
        if dom and selector in dom:
            counter.inner_text.return_value = dom[selector]
        else:
            counter.inner_text.side_effect = TimeoutError('No disponible')
        return MagicMock(first=counter)

    page.locator = MagicMock(side_effect=locator)
    return page


class CounterTests(unittest.TestCase):
    def test_numeric_formats(self):
        for value, expected in [('0', 0), ('1,234', 1234), ('1.5K', 1500),
                                ('2m', 2000000), ('1.2B', 1200000000), (' 42 ', 42)]:
            with self.subTest(value=value):
                self.assertEqual(convert_views(value), expected)

    def test_missing_invalid_and_negative_are_not_zero(self):
        for value in [None, '', 'N/A', '-1', '1.5', 'Me gusta']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                convert_views(value)


class InteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_counts_include_real_zero(self):
        page = make_page({'diggCount': '12345', 'commentCount': 0,
                          'shareCount': '12', 'collectCount': '34'})
        self.assertEqual(await get_video_interactions(page, URL), {
            'Likes': 12345, 'Comments': 0, 'Shares': 12, 'Saves': 34,
            'Metrics Error': '',
        })
        self.assertTrue(all('-count' not in call.args[0] for call in page.locator.call_args_list))

    async def test_dom_fallback_uses_favorite_count(self):
        page = make_page(dom={
            '[data-e2e="like-count"]': '1.2K',
            '[data-e2e="comment-count"]': '5',
            '[data-e2e="share-count"]': '6',
            '[data-e2e="favorite-count"]': '7',
        })
        result = await get_video_interactions(page, URL)
        self.assertEqual([result[k] for k in ['Likes', 'Comments', 'Shares', 'Saves']],
                         [1200, 5, 6, 7])
        self.assertEqual(result['Metrics Error'], '')

    async def test_partial_data_preserves_available_counts(self):
        result = await get_video_interactions(make_page({'diggCount': 9}), URL)
        self.assertEqual(result['Likes'], 9)
        self.assertIsNone(result['Saves'])
        self.assertIn('Comments, Shares, Saves', result['Metrics Error'])

    async def test_does_not_use_json_for_another_video(self):
        result = await get_video_interactions(make_page({'diggCount': 999}, item_id='456'), URL)
        self.assertIsNone(result['Likes'])
        self.assertTrue(result['Metrics Error'])

    async def test_navigation_failure_returns_error_without_raising(self):
        page = make_page()
        page.goto.side_effect = TimeoutError('No cargo')
        result = await get_video_interactions(page, URL)
        self.assertIsNone(result['Likes'])
        self.assertIn('TimeoutError', result['Metrics Error'])

    async def test_rejects_http_error(self):
        page = make_page()
        page.goto.return_value.status = 403
        with self.assertRaisesRegex(ScrapingRestrictedError, 'HTTP 403'):
            await get_video_interactions(page, URL)

    async def test_rejects_redirect(self):
        page = make_page({'diggCount': 999})
        page.url = 'https://www.tiktok.com/login'
        with self.assertRaisesRegex(ScrapingRestrictedError, 'iniciar sesion'):
            await get_video_interactions(page, URL)

    async def test_malformed_json_falls_back_to_dom(self):
        page = make_page({'diggCount': 999}, dom={'[data-e2e="like-count"]': '15'})
        page.query_selector.return_value.text_content.return_value = '{invalid'
        result = await get_video_interactions(page, URL)
        self.assertEqual(result['Likes'], 15)


if __name__ == '__main__':
    unittest.main()

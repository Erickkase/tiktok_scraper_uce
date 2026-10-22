import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from configuracion import DEFAULT_CONFIG
from scraper import ScrapingRestrictedError, get_video_comments, scrape_profile


URL = 'https://www.tiktok.com/@demo/video/123'


def comment(number, video_id='123', text=None):
    return {
        'cid': str(number), 'aweme_id': video_id, 'reply_id': '0',
        'text': text if text is not None else f'Comentario {number}',
        'digg_count': number, 'user': {'unique_id': f'autor{number}'},
    }


def response(payload, status=200, request_video='123', cursor=0):
    result = MagicMock()
    result.url = f'https://www.tiktok.com/api/comment/list/?aweme_id={request_video}&cursor={cursor}'
    result.status = status
    result.json = AsyncMock(return_value=payload)
    if isinstance(payload, Exception):
        result.json.side_effect = payload
    return result


def comment_page(payloads, status=200, request_video='123'):
    page = MagicMock()
    page.url = URL
    page.locator.return_value.first.click = AsyncMock()
    page.locator.return_value.first.is_visible = AsyncMock(return_value=False)
    page.evaluate = AsyncMock()
    responses = iter(payloads)

    async def tick(milliseconds):
        try:
            payload = next(responses)
        except StopIteration:
            return
        page.on.call_args.args[1](response(payload, status, request_video))

    page.wait_for_timeout = AsyncMock(side_effect=tick)
    return page


class CommentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        access = patch('scraper.check_page_access', new_callable=AsyncMock)
        self.access = access.start()
        self.addCleanup(access.stop)

    async def test_collects_twenty_and_removes_listener(self):
        page = comment_page([{'comments': [comment(n) for n in range(25)], 'has_more': 1}])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), DEFAULT_CONFIG.comments)
        self.assertEqual(result['rows'][0]['Author'], 'autor0')
        self.assertEqual(result['rows'][0]['Author Handle'], 'autor0')
        self.assertEqual(result['rows'][0]['Comment Likes'], 0)
        self.assertEqual(result['rows'][0]['Comment Text'], 'Comentario 0')
        self.assertEqual(result['error'], '')
        self.assertEqual(result['status'], 'completo')
        self.assertFalse(result['restricted'])
        page.remove_listener.assert_called_once_with('response', page.on.call_args.args[1])

    async def test_loads_more_deduplicates_ids_and_keeps_same_text_with_different_ids(self):
        page = comment_page([
            {'comments': [comment(n, text='Mismo texto') for n in range(10)], 'has_more': 1},
            {'comments': [comment(n, text='Mismo texto') for n in range(8, 20)], 'has_more': 0},
        ])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), 20)
        self.assertEqual(len({row['Comment ID'] for row in result['rows']}), 20)
        page.evaluate.assert_awaited_once()
        self.assertEqual(page.wait_for_timeout.await_count, 2)
        self.assertTrue(all(call.args == (2000,) for call in page.wait_for_timeout.await_args_list))

    async def test_does_not_treat_loading_placeholders_as_comments(self):
        page = comment_page([
            {'comments': [], 'has_more': 1},
            {'comments': [comment(n) for n in range(20)], 'has_more': 0},
        ])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), 20)
        self.assertEqual(page.wait_for_timeout.await_count, 2)

    async def test_waits_for_native_page_retry_after_empty_response(self):
        for first in (ValueError('Respuesta aun no disponible'), {'comments': [], 'has_more': 0},
                      {'status_code': 123, 'comments': None}):
            page = comment_page([first, {'comments': [comment(n) for n in range(20)], 'has_more': 0}])
            result = await get_video_comments(page, URL, reported_count=20)
            self.assertEqual(len(result['rows']), 20)
            self.assertEqual(result['error'], '')

    async def test_waits_for_native_retry_at_twenty_seconds_without_initial_comments(self):
        for initial in (ValueError('JSON aun no disponible'), {'comments': [], 'has_more': 1},
                        {'comments': [], 'has_more': 0}):
            with self.subTest(initial=initial):
                page = comment_page([])
                elapsed = 0

                async def tick(milliseconds):
                    nonlocal elapsed
                    elapsed += milliseconds
                    if elapsed == 2000:
                        page.on.call_args.args[1](response(initial))
                    elif elapsed == 20000:
                        page.on.call_args.args[1](response({
                            'comments': [comment(n) for n in range(20)], 'has_more': 0,
                        }))

                page.wait_for_timeout.side_effect = tick
                result = await get_video_comments(page, URL, reported_count=20)
                self.assertEqual(elapsed, 20000)
                self.assertEqual(result['status'], 'completo')
                self.assertEqual(result['error'], '')
                self.assertEqual(len(result['rows']), 20)

    async def test_fewer_available_comments_reports_shortfall(self):
        result = await get_video_comments(comment_page([{'comments': [comment(1), comment(2)], 'has_more': 0}]), URL)
        self.assertEqual(len(result['rows']), 2)
        self.assertIn('2 de 20', result['error'])
        self.assertIn('no hay mas comentarios principales', result['error'])
        self.assertEqual(result['status'], 'parcial')

    async def test_filters_replies_other_videos_empty_text_and_missing_ids(self):
        items = [comment(1), comment(2, video_id='456'), comment(3, text=' '),
                 {**comment(4), 'reply_id': '789'}, {**comment(5), 'reply_to_reply_id': '8'},
                 {**comment(6), 'cid': None}, {**comment(7), 'cid': 7.0}, None]
        result = await get_video_comments(comment_page([{'comments': items, 'has_more': 0}]), URL)
        self.assertEqual([row['Comment ID'] for row in result['rows']], ['1'])

    async def test_preserves_text_and_distinguishes_handle_from_nickname(self):
        items = [{**comment(1, text='  texto\n '), 'user': {'nickname': 'Nombre'}},
                 {**comment(2), 'user': {'nickname': 'Nombre', 'uniqueId': 'handle'}},
                 {**comment(3), 'user': {'nickname': False, 'unique_id': 123}}]
        result = await get_video_comments(comment_page([{'comments': items, 'has_more': 0}]), URL)
        self.assertEqual(result['rows'][0]['Comment Text'], '  texto\n ')
        self.assertEqual(result['rows'][0]['Author'], 'Nombre')
        self.assertIsNone(result['rows'][0]['Author Handle'])
        self.assertEqual(result['rows'][1]['Author Handle'], 'handle')
        self.assertIsNone(result['rows'][2]['Author Handle'])
        self.assertIsNone(result['rows'][2]['Author'])

    async def test_ignores_responses_for_another_video(self):
        result = await get_video_comments(comment_page([{'comments': [comment(1)], 'has_more': 0}], request_video='456'), URL)
        self.assertEqual(result['rows'], [])
        self.assertIn('0 de 20', result['error'])

    async def test_does_not_read_comments_after_redirect(self):
        page = comment_page([])
        page.url = 'https://www.tiktok.com/@other/video/456'
        result = await get_video_comments(page, URL)
        self.assertEqual(result['rows'], [])
        self.assertIn('pagina distinta', result['error'])
        page.locator.return_value.first.click.assert_not_awaited()

    async def test_same_video_id_on_foreign_domain_is_not_accepted(self):
        page = comment_page([])
        page.url = 'https://example.com/@demo/video/123'
        result = await get_video_comments(page, URL)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['rows'], [])
        page.locator.return_value.first.click.assert_not_awaited()

    async def test_comment_http_restriction_is_reported(self):
        for status in (403, 429):
            result = await get_video_comments(comment_page([{}], status=status), URL)
            self.assertTrue(result['restricted'])
            self.assertEqual(result['status'], 'restringido')
            self.assertIn(str(status), result['error'])

    async def test_partial_comments_survive_later_restriction(self):
        self.access.side_effect = [None, None, ScrapingRestrictedError('Verificacion requerida')]
        page = comment_page([{'comments': [comment(1)], 'has_more': 1}, {'comments': [], 'has_more': 1}])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), 1)
        self.assertTrue(result['restricted'])

    async def test_missing_responses_have_bounded_wait(self):
        page = comment_page([])
        result = await get_video_comments(page, URL)
        self.assertEqual(result['rows'], [])
        self.assertEqual(page.wait_for_timeout.await_count, DEFAULT_CONFIG.comment_rounds)
        self.assertEqual(result['status'], 'error')

    async def test_stops_when_loaded_comments_do_not_increase(self):
        page = comment_page([{'comments': [comment(1)], 'has_more': 1}])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(page.wait_for_timeout.await_count, 9)

    async def test_invalid_public_response_reports_error(self):
        result = await get_video_comments(comment_page([{'status_code': 123, 'comments': None}]), URL)
        self.assertEqual(result['rows'], [])
        self.assertIn('codigo 123', result['error'])

    async def test_zero_requires_evidence_and_no_contrary_total(self):
        for total, status in ((None, 'sin_comentarios'), (0, 'sin_comentarios'), (10, 'error')):
            page = comment_page([{'comments': [], 'has_more': 0}])
            result = await get_video_comments(page, URL, reported_count=total)
            self.assertEqual(result['status'], status)
            self.assertEqual(page.wait_for_timeout.await_count,
                             0 if total == 0 else 1 if total is None else DEFAULT_CONFIG.comment_rounds)


class ProfileDataTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_returns_joined_data_without_export_or_images(self):
        browser = AsyncMock()
        page = browser.new_page.return_value
        page.query_selector.return_value = None
        urls = [URL, URL.replace('123', '456')]
        videos = [{'url': url, 'views': '100'} for url in urls]
        interactions = [{
            'Likes': 10, 'Comments': 50, 'Shares': 2, 'Saves': 3,
            'Metrics Error': '', 'Comments Collected': 1, 'Comments Status': 'parcial',
            'Comments Error': 'Solo un comentario disponible',
            '_comment_rows': [{'Comment ID': str(index), 'Author': 'Nombre', 'Author Handle': 'autor',
                               'Comment Text': f'Texto {index}', 'Comment Likes': 0}],
        } for index in range(2)]

        async def collect(*args):
            self.assertTrue(page.query_selector.await_count >= 4)
            return interactions

        with patch('scraper.check_page_access', new_callable=AsyncMock), patch(
            'scraper.collect_recent_videos', new=AsyncMock(return_value=videos)
        ), patch('scraper.collect_video_interactions', side_effect=collect):
            profile, posts, rows = await scrape_profile(browser, 'demo')
        self.assertIsNone(profile['Bio'])
        self.assertEqual(len(posts), 2)
        self.assertEqual([post['Comments'] for post in posts], [50, 50])
        self.assertEqual([post['Video ID'] for post in posts], ['123', '456'])
        self.assertNotIn('_comment_rows', posts[0])
        self.assertNotIn('image_id', posts[0])
        self.assertEqual([row['Video Links'] for row in rows], urls)
        self.assertEqual([row['id_perfil'] for row in rows], ['demo', 'demo'])
        page.close.assert_awaited_once()

    async def test_profile_waits_for_hydration_before_reading_bio_and_counts(self):
        browser = AsyncMock()
        page = browser.new_page.return_value
        ready = False
        bio = AsyncMock()
        bio.inner_text.return_value = 'Bio real'
        count = AsyncMock()
        count.inner_text.return_value = '12'
        events = []

        async def hydrate(selector, **kwargs):
            nonlocal ready
            self.assertIn('followers-count', selector)
            self.assertIn('user-bio', selector)
            self.assertEqual(kwargs['timeout'], DEFAULT_CONFIG.selector_timeout)
            ready = True
            events.append('hydrated')

        async def query(selector):
            self.assertTrue(ready)
            events.append(selector)
            return bio if 'user-bio' in selector else count

        async def videos(*args):
            self.assertEqual(events[-1], '[data-e2e="user-bio"]')
            return []

        page.wait_for_selector.side_effect = hydrate
        page.query_selector.side_effect = query
        with patch('scraper.check_page_access', new_callable=AsyncMock) as access, patch(
            'scraper.collect_recent_videos', side_effect=videos
        ), patch('scraper.collect_video_interactions', new=AsyncMock(return_value=[])):
            profile, _, _ = await scrape_profile(browser, 'demo')
        self.assertEqual(profile['Bio'], 'Bio real')
        self.assertEqual(profile['Followers'], 12)
        self.assertEqual(profile['Profile Error'], '')
        self.assertEqual(access.await_count, 2)
        page.goto.assert_awaited_once()
        page.close.assert_awaited_once()

    async def test_profile_timeout_returns_partial_data_and_limitation(self):
        browser = AsyncMock()
        page = browser.new_page.return_value
        page.wait_for_selector.side_effect = TimeoutError('Sin datos de perfil')
        page.query_selector.return_value = None
        with patch('scraper.check_page_access', new_callable=AsyncMock), patch(
            'scraper.collect_recent_videos', new=AsyncMock(return_value=[])
        ), patch('scraper.collect_video_interactions', new=AsyncMock(return_value=[])):
            profile, posts, comments = await scrape_profile(browser, 'demo')
        self.assertIsNone(profile['Bio'])
        self.assertIsNone(profile['Followers'])
        self.assertIn('Perfil parcial', profile['Profile Error'])
        self.assertIn('Sin datos de perfil', profile['Profile Error'])
        self.assertEqual((posts, comments), ([], []))
        page.close.assert_awaited_once()

    async def test_profile_access_rechecked_after_wait_and_page_closed_on_restriction(self):
        browser = AsyncMock()
        page = browser.new_page.return_value
        page.wait_for_selector.side_effect = TimeoutError('CAPTCHA')
        with patch('scraper.check_page_access', new=AsyncMock(side_effect=[
            None, ScrapingRestrictedError('Verificacion requerida'),
        ])), patch('scraper.collect_recent_videos', new_callable=AsyncMock) as videos:
            with self.assertRaises(ScrapingRestrictedError):
                await scrape_profile(browser, 'demo')
        videos.assert_not_awaited()
        page.query_selector.assert_not_awaited()
        page.close.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()

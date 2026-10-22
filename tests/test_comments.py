import io
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from openpyxl import load_workbook

from main import (
    COMMENTS_PER_VIDEO, ScrapingRestrictedError, collect_video_interactions,
    get_video_comments, save_comments, scrape_profile,
)


URL = 'https://www.tiktok.com/@demo/video/123'


def comment(number, video_id='123', text=None):
    return {
        'cid': str(number), 'aweme_id': video_id, 'reply_id': '0',
        'text': text if text is not None else f'Comentario {number}',
        'digg_count': number, 'user': {'unique_id': f'autor{number}'},
    }


def comment_page(payloads, status=200, request_video='123'):
    page = MagicMock()
    page.url = URL
    page.locator.return_value.first.click = AsyncMock()
    page.evaluate = AsyncMock()
    responses = iter(payloads)

    async def tick(milliseconds):
        try:
            payload = next(responses)
        except StopIteration:
            return
        response = MagicMock()
        response.url = f'https://www.tiktok.com/api/comment/list/?aweme_id={request_video}'
        response.status = status
        response.json = AsyncMock(return_value=payload)
        if isinstance(payload, Exception):
            response.json.side_effect = payload
        page.on.call_args.args[1](response)

    page.wait_for_timeout = AsyncMock(side_effect=tick)
    return page


class CommentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        access = patch('main.check_page_access', new_callable=AsyncMock)
        self.access = access.start()
        self.addCleanup(access.stop)

    async def test_collects_twenty_and_removes_listener(self):
        page = comment_page([{'comments': [comment(n) for n in range(25)], 'has_more': 1}])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), COMMENTS_PER_VIDEO)
        self.assertEqual(result['rows'][0]['Author'], 'autor0')
        self.assertEqual(result['rows'][0]['Comment Likes'], 0)
        self.assertEqual(result['rows'][0]['Comment Text'], 'Comentario 0')
        self.assertEqual(result['error'], '')
        self.assertFalse(result['restricted'])
        page.remove_listener.assert_called_once_with('response', page.on.call_args.args[1])

    async def test_loads_more_deduplicates_ids_and_keeps_same_text_with_different_ids(self):
        first = [comment(n, text='Mismo texto') for n in range(10)]
        second = [comment(n, text='Mismo texto') for n in range(8, 20)]
        page = comment_page([
            {'comments': first, 'has_more': 1},
            {'comments': second, 'has_more': 0},
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
        page = comment_page([
            ValueError('Respuesta aun no disponible'),
            {'comments': [comment(n) for n in range(20)], 'has_more': 0},
        ])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), 20)
        self.assertEqual(result['error'], '')
        self.assertEqual(page.wait_for_timeout.await_count, 2)

    async def test_fewer_available_comments_reports_shortfall(self):
        page = comment_page([{'comments': [comment(1), comment(2)], 'has_more': 0}])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), 2)
        self.assertIn('2 de 20', result['error'])

    async def test_filters_replies_other_videos_empty_text_and_missing_ids(self):
        reply = {**comment(5), 'reply_id': '789'}
        no_id = {**comment(6), 'cid': None}
        page = comment_page([{'comments': [
            comment(1), comment(2, video_id='456'), comment(3, text=' '),
            reply, no_id, None,
        ], 'has_more': 0}])
        result = await get_video_comments(page, URL)
        self.assertEqual([row['Comment ID'] for row in result['rows']], ['1'])

    async def test_ignores_responses_for_another_video(self):
        page = comment_page([{'comments': [comment(1)], 'has_more': 0}], request_video='456')
        result = await get_video_comments(page, URL)
        self.assertEqual(result['rows'], [])
        self.assertIn('0 de 20', result['error'])

    async def test_does_not_read_comments_after_redirect(self):
        page = comment_page([])
        page.url = 'https://www.tiktok.com/@other/video/456'
        result = await get_video_comments(page, URL)
        self.assertEqual(result['rows'], [])
        self.assertIn('pagina distinta', result['error'])
        page.locator.return_value.first.click.assert_not_awaited()

    async def test_comment_http_restriction_is_reported(self):
        for status in (403, 429):
            with self.subTest(status=status):
                result = await get_video_comments(comment_page([{}], status=status), URL)
                self.assertTrue(result['restricted'])
                self.assertIn(str(status), result['error'])

    async def test_partial_comments_survive_later_restriction(self):
        self.access.side_effect = [None, None, ScrapingRestrictedError('Verificacion requerida')]
        page = comment_page([
            {'comments': [comment(1)], 'has_more': 1},
            {'comments': [], 'has_more': 1},
        ])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), 1)
        self.assertTrue(result['restricted'])
        self.assertIn('Verificacion requerida', result['error'])

    async def test_missing_responses_have_bounded_wait(self):
        page = comment_page([])
        result = await get_video_comments(page, URL)
        self.assertEqual(result['rows'], [])
        self.assertEqual(page.wait_for_timeout.await_count, 30)
        self.assertIn('0 de 20', result['error'])

    async def test_stops_when_loaded_comments_do_not_increase(self):
        page = comment_page([{'comments': [comment(1)], 'has_more': 1}])
        result = await get_video_comments(page, URL)
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(page.wait_for_timeout.await_count, 9)

    async def test_invalid_public_response_reports_error(self):
        page = comment_page([{'status_code': 123, 'comments': None}])
        result = await get_video_comments(page, URL)
        self.assertEqual(result['rows'], [])
        self.assertIn('codigo 123', result['error'])


class CommentBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_comments_restriction_keeps_metrics_and_skips_next_video(self):
        metrics = {'Likes': 42, 'Comments': 100, 'Metrics Error': ''}
        partial = {'rows': [{'Comment ID': '1', 'Comment Text': 'Hola'}],
                   'error': 'HTTP 429', 'restricted': True}
        with patch('main.get_video_interactions', new=AsyncMock(return_value=metrics)) as get_metrics:
            with patch('main.get_video_comments', new=AsyncMock(return_value=partial)) as get_comments:
                result = await collect_video_interactions(
                    AsyncMock(), [{'url': URL}, {'url': URL.replace('123', '456')}]
                )
        get_metrics.assert_awaited_once()
        get_comments.assert_awaited_once()
        self.assertEqual(result[0]['Likes'], 42)
        self.assertEqual(result[0]['Comments'], 100)
        self.assertEqual(result[0]['Comments Collected'], 1)
        self.assertEqual(len(result[0]['_comment_rows']), 1)
        self.assertIsNone(result[1]['Comments Collected'])
        self.assertIn('restriccion', result[1]['Metrics Error'])

    async def test_zero_total_skips_comment_panel(self):
        metrics = {'Likes': 1, 'Comments': 0, 'Metrics Error': ''}
        with patch('main.get_video_interactions', new=AsyncMock(return_value=metrics)):
            with patch('main.get_video_comments', new_callable=AsyncMock) as get_comments:
                result = await collect_video_interactions(AsyncMock(), [{'url': URL}])
        get_comments.assert_not_awaited()
        self.assertEqual(result[0]['Comments Collected'], 0)
        self.assertEqual(result[0]['_comment_rows'], [])


class CommentExportTests(unittest.TestCase):
    def test_exports_unicode_literal_formulas_and_long_ids(self):
        stream = io.BytesIO()
        rows = [{
            'Video Links': URL, 'Comment ID': '7694797676306615583',
            'Author': '=1+1', 'Comment Text': '=HYPERLINK("https://example.com")\x00',
            'Comment Likes': 0, 'id_perfil': 'demo',
        }, {
            'Video Links': URL, 'Comment ID': '2', 'Author': 'autor',
            'Comment Text': 'Hola \U0001f600, caf\u00e9', 'Comment Likes': 3, 'id_perfil': 'demo',
        }]
        save_comments(rows, stream)
        stream.seek(0)
        book = load_workbook(stream, data_only=False)
        sheet = book.active
        self.assertEqual(sheet.max_row, 3)
        self.assertEqual(sheet['B2'].value, '7694797676306615583')
        self.assertEqual(sheet['B2'].data_type, 's')
        self.assertEqual(sheet['C2'].value, '=1+1')
        self.assertEqual(sheet['C2'].data_type, 's')
        self.assertEqual(sheet['D2'].value, '=HYPERLINK("https://example.com")')
        self.assertEqual(sheet['D2'].data_type, 's')
        self.assertEqual(sheet['D3'].value, 'Hola \U0001f600, caf\u00e9')
        self.assertEqual(sheet['E2'].value, 0)
        book.close()

    def test_empty_comments_still_export_headers(self):
        stream = io.BytesIO()
        save_comments([], stream)
        stream.seek(0)
        book = load_workbook(stream)
        self.assertEqual(book.active.max_row, 1)
        self.assertEqual(book.active['D1'].value, 'Comment Text')
        book.close()


class ProfileCommentExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_profile_keeps_one_post_row_per_video_and_links_comment_rows(self):
        browser = AsyncMock()
        profile = AsyncMock()
        profile.query_selector.return_value = None
        metrics_page = AsyncMock()
        browser.new_page.side_effect = [profile, metrics_page]
        urls = [URL, URL.replace('123', '456')]
        videos = [{'url': url, 'views': '100', 'image_url': None} for url in urls]
        interactions = [{
            'Likes': 10, 'Comments': 50, 'Shares': 2, 'Saves': 3,
            'Metrics Error': '', 'Comments Collected': 1,
            'Comments Error': 'Solo un comentario disponible',
            '_comment_rows': [{'Comment ID': str(index), 'Author': 'autor',
                               'Comment Text': f'Texto {index}', 'Comment Likes': 0}],
        } for index in range(2)]
        tables = []

        def capture_table(frame, filename, index=False):
            tables.append((str(filename), frame.copy()))

        with patch('main.check_page_access', new_callable=AsyncMock):
            with patch('main.collect_recent_videos', new=AsyncMock(return_value=videos)):
                with patch('main.collect_video_interactions', new=AsyncMock(return_value=interactions)):
                    with patch('main.os.path.exists', return_value=True):
                        with patch('main.pd.DataFrame.to_excel', new=capture_table):
                            with patch('main.save_comments') as export_comments:
                                await scrape_profile(browser, 'demo')
        posts = tables[0][1]
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts['Comments'].tolist(), [50, 50])
        self.assertEqual(posts['Comments Collected'].tolist(), [1, 1])
        self.assertNotIn('_comment_rows', posts.columns)
        rows, filename = export_comments.call_args.args
        self.assertEqual([row['Video Links'] for row in rows], urls)
        self.assertEqual([row['id_perfil'] for row in rows], ['demo', 'demo'])
        self.assertIn('demo_comentarios_', filename)
        metrics_page.close.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()

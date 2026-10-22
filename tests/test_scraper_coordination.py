import asyncio
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import Error as PlaywrightError

from configuracion import DEFAULT_CONFIG
from scraper import CommentCollector, collect_video_interactions, get_video_comments, normalize_username, run
from test_comments import URL, comment, comment_page, response


class CoordinationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        access = patch('scraper.check_page_access', new_callable=AsyncMock)
        access.start()
        self.addCleanup(access.stop)

    async def test_navigation_response_captured_before_metrics_and_no_panel_click(self):
        page = comment_page([])

        async def goto(url, **kwargs):
            page.on.call_args.args[1](response({'comments': [comment(n) for n in range(20)], 'has_more': 0}))
            return MagicMock(status=200)

        page.goto = AsyncMock(side_effect=goto)
        page.wait_for_function = AsyncMock()
        page.query_selector = AsyncMock(return_value=None)
        page.locator.return_value.first.inner_text = AsyncMock(return_value='0')
        result = await collect_video_interactions(page, [{'url': URL}])
        self.assertEqual(result[0]['Comments'], 0)
        self.assertEqual(result[0]['Comments Collected'], 20)
        self.assertEqual(result[0]['Comments Status'], 'completo')
        page.goto.assert_awaited_once()
        page.locator.return_value.first.click.assert_not_awaited()
        page.remove_listener.assert_called_once()

    async def test_document_rejection_captured_even_when_goto_raises(self):
        for status in (403, 429):
            with self.subTest(status=status):
                page = comment_page([])
                page.url = 'https://www.tiktok.com/@demo'

                async def fail_navigation(url, **kwargs):
                    document = MagicMock()
                    document.url, document.status = url, status
                    document.request.resource_type = 'document'
                    document.frame = page.main_frame
                    page.on.call_args.args[1](document)
                    raise PlaywrightError('Page.goto: net::ERR_HTTP_RESPONSE_CODE_FAILURE')

                page.goto = AsyncMock(side_effect=fail_navigation)
                with patch('scraper.get_video_comments', new_callable=AsyncMock) as comments:
                    output = await collect_video_interactions(page, [
                        {'url': URL}, {'url': URL.replace('123', '456')},
                    ])
                page.goto.assert_awaited_once()
                comments.assert_not_awaited()
                self.assertEqual([row['Comments Status'] for row in output], ['restringido', 'restringido'])
                self.assertIn(f'HTTP {status}', output[0]['Metrics Error'])
                self.assertIn(f'HTTP {status}', output[0]['Comments Error'])
                self.assertNotIn('pagina distinta', output[0]['Comments Error'])
                self.assertIsNone(output[1]['Comments Collected'])
                page.remove_listener.assert_called_once()

    async def test_unobserved_http_navigation_failure_stops_without_inventing_a_status(self):
        page = comment_page([])
        page.url = 'https://www.tiktok.com/@demo'
        page.goto = AsyncMock(side_effect=PlaywrightError('net::ERR_HTTP_RESPONSE_CODE_FAILURE'))
        with patch('scraper.get_video_comments', new_callable=AsyncMock) as comments:
            output = await collect_video_interactions(page, [
                {'url': URL}, {'url': URL.replace('123', '456')},
            ])
        page.goto.assert_awaited_once()
        comments.assert_not_awaited()
        self.assertEqual([row['Comments Status'] for row in output], ['error', 'error'])
        self.assertIn('ERR_HTTP_RESPONSE_CODE_FAILURE', output[0]['Comments Error'])
        self.assertNotIn('pagina distinta', output[0]['Comments Error'])
        self.assertIsNone(output[1]['Comments Collected'])
        self.assertNotIn('403', output[1]['Comments Error'])

    async def test_unrelated_document_or_asset_rejection_is_not_video_restriction(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            for resource, frame, url in (
                ('image', page.main_frame, URL),
                ('document', MagicMock(), URL),
                ('document', page.main_frame, URL.replace('123', '456')),
                ('document', page.main_frame, 'https://example.com/@demo/video/123'),
            ):
                document = MagicMock()
                document.url, document.status = url, 403
                document.request.resource_type, document.frame = resource, frame
                collector.on_response(document)
        self.assertFalse(collector.restricted)
        self.assertIsNone(collector.navigation_status)

    async def test_recoverable_navigation_timeout_skips_comments_but_allows_next_video(self):
        page = comment_page([])
        failure = {'Metrics Error': 'TimeoutError: No cargo', '_navigation_failed': True}
        success = {'Metrics Error': '', 'Comments': 1}
        with patch('scraper.get_video_interactions', new=AsyncMock(side_effect=[failure, success])):
            with patch('scraper.get_video_comments', new_callable=AsyncMock) as comments:
                with patch('scraper.asyncio.sleep', new_callable=AsyncMock) as delay:
                    output = await collect_video_interactions(page, [
                        {'url': URL}, {'url': URL.replace('123', '456')},
                    ])
        self.assertEqual(output[0]['Comments Status'], 'error')
        self.assertIn('TimeoutError', output[0]['Comments Error'])
        comments.assert_awaited_once()
        self.assertEqual(comments.await_args.args[1], URL.replace('123', '456'))
        delay.assert_awaited_once_with(2)

    async def test_sequence_is_response_order_not_json_completion_order(self):
        page = comment_page([])
        release = asyncio.Event()

        async def slow_json():
            await release.wait()
            return {'comments': [comment(n) for n in range(15)], 'has_more': 1}

        first = response({})
        first.json.side_effect = slow_json
        async with CommentCollector(page, URL) as collector:
            collector.on_response(first)
            collector.on_response(response({'comments': [comment(n) for n in range(15, 30)], 'has_more': 0}, cursor=15))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            release.set()
            await collector.settle()
            self.assertEqual(list(collector.rows), [str(n) for n in range(20)])
        self.assertTrue(all(task.done() for task in collector.tasks))

    async def test_old_terminal_cursor_does_not_override_later_page(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            collector.on_response(response({'comments': [comment(2)], 'has_more': 1}, cursor=20))
            collector.on_response(response({'comments': [], 'has_more': 0}, cursor=0))
            await collector.settle()
            self.assertTrue(collector.has_more)
            self.assertFalse(collector.empty_evidence)

    async def test_cursor_zero_precedes_cursor_twenty_even_when_headers_arrive_late(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            collector.on_response(response({
                'comments': [comment(n) for n in range(20, 40)], 'has_more': 1,
            }, cursor=20))
            collector.on_response(response({
                'comments': [comment(n) for n in range(20)], 'has_more': 0,
            }, cursor=0))
            await collector.settle()
            self.assertEqual(list(collector.rows), [str(n) for n in range(20)])
            self.assertTrue(collector.has_more)
        self.assertEqual([row['Comment ID'] for row in collector.result()['rows']], [str(n) for n in range(20)])

    async def test_cursor_order_preserves_first_observed_version_of_duplicate_id(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            collector.on_response(response({'comments': [comment(1, text='Original')], 'has_more': 1}, cursor=20))
            collector.on_response(response({
                'comments': [comment(0), comment(1, text='Nueva version')], 'has_more': 0,
            }, cursor=0))
            await collector.settle()
            self.assertEqual(list(collector.rows), ['0', '1'])
            self.assertEqual(collector.rows['1']['Comment Text'], 'Original')
            self.assertTrue(collector.has_more)

    async def test_exact_public_endpoint_and_video_id_required(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            for url in (
                'https://evil.test/api/comment/list/?aweme_id=123',
                'https://www.tiktok.com.evil.test/api/comment/list/?aweme_id=123',
                'https://www.tiktok.com/api/comment/list/reply/?aweme_id=123',
                'https://www.tiktok.com/api/comment/list/extra?aweme_id=123',
                'https://www.tiktok.com/api/comment/list/?aweme_id=1234',
                'https://www.tiktok.com/api/comment/list/?aweme_id=123&aweme_id=456',
                'https://user@www.tiktok.com/api/comment/list/?aweme_id=123',
                'http://www.tiktok.com/api/comment/list/?aweme_id=123',
                'https://www.tiktok.com:444/api/comment/list/?aweme_id=123',
                'https://www.tiktok.com:invalid/api/comment/list/?aweme_id=123',
            ):
                item = response({'comments': [comment(1)], 'has_more': 0})
                item.url = url
                collector.on_response(item)
                item.json.assert_not_awaited()
            self.assertEqual(collector.tasks, [])

    async def test_https_default_and_explicit_tls_port_are_accepted(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            for number, host in enumerate(('www.tiktok.com', 'www.tiktok.com:443')):
                item = response({'comments': [comment(number)], 'has_more': 0})
                item.url = f'https://{host}/api/comment/list/?aweme_id=123'
                collector.on_response(item)
            await collector.settle()
            self.assertEqual(list(collector.rows), ['0', '1'])

    async def test_complete_result_ignores_later_nonrestriction_http_warning(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            collector.on_response(response({'comments': [comment(n) for n in range(20)], 'has_more': 1}))
            collector.on_response(response({}, status=500, cursor=20))
            await collector.settle()
        self.assertEqual(collector.result()['status'], 'completo')
        self.assertEqual(collector.result()['error'], '')

    async def test_partial_result_preserves_nonrestriction_http_warning(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            collector.on_response(response({'comments': [comment(1)], 'has_more': 1}))
            collector.on_response(response({}, status=500, cursor=20))
        self.assertEqual(collector.result()['status'], 'parcial')
        self.assertIn('HTTP 500', collector.result()['error'])

    async def test_complete_rows_do_not_hide_a_fatal_error_or_restriction(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            collector.on_response(response({'comments': [comment(n) for n in range(20)], 'has_more': 0}))
        collector.error = 'Pagina distinta'
        self.assertEqual(collector.result()['status'], 'parcial')
        self.assertIn('Pagina distinta', collector.result()['error'])
        collector.restricted = True
        collector.error = 'HTTP 429'
        self.assertEqual(collector.result()['status'], 'restringido')
        self.assertEqual(collector.result()['error'], 'HTTP 429')

    async def test_preloaded_partial_survives_missing_button(self):
        page = comment_page([])
        page.locator.return_value.first.click.side_effect = RuntimeError('missing')
        async with CommentCollector(page, URL) as collector:
            collector.on_response(response({'comments': [comment(1)], 'has_more': 0}))
            await get_video_comments(page, URL, collector=collector)
        result = collector.result()
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['status'], 'parcial')
        self.assertIn('missing', result['error'])

    async def test_open_panel_not_toggled(self):
        page = comment_page([{'comments': [comment(n) for n in range(20)], 'has_more': 0}])
        page.locator.return_value.first.is_visible.return_value = True
        result = await get_video_comments(page, URL)
        page.locator.return_value.first.click.assert_not_awaited()
        self.assertEqual(result['status'], 'completo')

    async def test_deadline_cancels_pending_json_without_losing_ready_data(self):
        page = comment_page([])
        config = replace(DEFAULT_CONFIG, comment_deadline=0.05, response_timeout=10)
        blocked = response({})
        blocked.json.side_effect = lambda: None

        async def never():
            await asyncio.Event().wait()

        blocked.json.side_effect = never
        async with CommentCollector(page, URL, config) as collector:
            collector.on_response(blocked)
            collector.on_response(response({'comments': [comment(2)], 'has_more': 1}, cursor=1))
            await get_video_comments(page, URL, config, collector)
        self.assertEqual(list(collector.rows), ['2'])
        self.assertTrue(all(task.done() for task in collector.tasks))
        page.remove_listener.assert_called_once()

    async def test_first_reader_timeout_does_not_discard_later_ready_batch(self):
        page = comment_page([])
        config = replace(DEFAULT_CONFIG, response_timeout=0.01, comment_deadline=1)

        async def never():
            await asyncio.Event().wait()

        first = response({})
        first.json.side_effect = never
        async with CommentCollector(page, URL, config) as collector:
            collector.on_response(first)
            collector.on_response(response({
                'comments': [comment(n) for n in range(20)], 'has_more': 0,
            }, cursor=20))
            await collector.settle()
        self.assertTrue(all(task.done() for task in collector.tasks))
        self.assertEqual(list(collector.rows), [str(n) for n in range(20)])
        self.assertEqual(collector.result()['status'], 'completo')
        self.assertEqual(collector.result()['error'], '')

    async def test_external_cancellation_removes_listener_and_readers(self):
        page = comment_page([])
        started = asyncio.Event()
        saved = []

        async def never():
            started.set()
            await asyncio.Event().wait()

        async def work():
            async with CommentCollector(page, URL) as collector:
                saved.append(collector)
                item = response({})
                item.json.side_effect = never
                collector.on_response(item)
                await asyncio.Event().wait()

        task = asyncio.create_task(work())
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(all(reader.done() for reader in saved[0].tasks))
        page.remove_listener.assert_called_once()

    async def test_restriction_keeps_partial_metrics_and_comments_stops_batch(self):
        page = comment_page([])

        async def metrics(*args):
            listener = page.on.call_args.args[1]
            listener(response({'comments': [comment(1)], 'has_more': 1}))
            listener(response({}, status=429))
            return {'Likes': 42, 'Comments': 100, 'Metrics Error': ''}

        with patch('scraper.get_video_interactions', side_effect=metrics) as get_metrics:
            result = await collect_video_interactions(page, [{'url': URL}, {'url': URL.replace('123', '456')}])
        get_metrics.assert_awaited_once()
        self.assertEqual(result[0]['Likes'], 42)
        self.assertEqual(result[0]['Comments Collected'], 1)
        self.assertEqual(result[0]['Comments Status'], 'restringido')
        self.assertIsNone(result[1]['Comments Collected'])
        self.assertEqual(result[1]['Comments Status'], 'restringido')

    async def test_zero_skips_panel_only_without_real_preloaded_comments(self):
        page = comment_page([])
        with patch('scraper.get_video_interactions', new=AsyncMock(return_value={'Comments': 0, 'Metrics Error': ''})):
            result = await collect_video_interactions(page, [{'url': URL}])
        self.assertEqual(result[0]['Comments Status'], 'sin_comentarios')
        page.locator.return_value.first.click.assert_not_awaited()

    async def test_zero_does_not_discard_preloaded_partial_comments(self):
        page = comment_page([])
        async with CommentCollector(page, URL) as collector:
            collector.on_response(response({'comments': [comment(1)], 'has_more': 0}))
            await get_video_comments(page, URL, collector=collector, reported_count=0)
        self.assertEqual(collector.result(0)['status'], 'parcial')
        self.assertEqual(len(collector.rows), 1)

    async def test_delay_is_after_comments_and_before_next_navigation(self):
        page = comment_page([])
        events = []

        async def metrics(page, url, config):
            events.append(('navigate', url))
            return {'Comments': 1, 'Metrics Error': ''}

        async def comments(page, url, config, collector, reported_count):
            events.append(('comments_end', url))

        async def delay(seconds):
            self.assertGreaterEqual(seconds, 2)
            events.append(('wait', seconds))

        second = URL.replace('123', '456')
        with patch('scraper.get_video_interactions', side_effect=metrics), patch(
            'scraper.get_video_comments', side_effect=comments
        ), patch('scraper.asyncio.sleep', side_effect=delay):
            await collect_video_interactions(page, [{'url': URL}, {'url': second}])
        self.assertEqual(events, [('navigate', URL), ('comments_end', URL),
                                  ('wait', 2), ('navigate', second), ('comments_end', second)])

    async def test_run_returns_data_and_closes_browser(self):
        playwright = AsyncMock()
        data = ({'Bio': ''}, [], [])
        with patch('scraper.scrape_profile', new=AsyncMock(return_value=data)):
            self.assertEqual(await run(playwright, '@demo'), data)
        playwright.chromium.launch.return_value.close.assert_awaited_once()


class UsernameTests(unittest.TestCase):
    def test_safe_names(self):
        self.assertEqual(normalize_username(' @demo.name '), 'demo.name')
        self.assertEqual(normalize_username('CON'), 'CON')
        for value in ('../demo', 'https://www.tiktok.com/@demo', '.demo', 'demo.', '', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_username(value)

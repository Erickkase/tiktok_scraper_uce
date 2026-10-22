import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

import descargar_videos as videos


MP4 = struct.pack('>I', 24) + b'ftypisom' + b'\0' * 2036


def url(video_id):
    return 'https://www.tiktok.com/@demo/video/' + str(video_id)


class VideoDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / 'videos'
        self.source = self.root / 'posts.xlsx'
        self.backend = MagicMock()
        self.downloader = self.backend.return_value.__enter__.return_value
        self.downloader.extract_info.side_effect = lambda link, download: {
            'id': link.rsplit('/', 1)[1], 'formats': [{
                'ext': 'mp4', 'vcodec': 'h264', 'acodec': 'aac',
                'url': 'https://media.invalid/secret?signature=private',
                'protocol': 'https', 'format_id': 'combined'}]}
        metadata = patch('descargar_videos.read_video_metadata',
                         side_effect=lambda link: self.downloader.extract_info(link, download=False))
        metadata.start()
        self.addCleanup(metadata.stop)

        def process(info):
            Path(self.backend.call_args[0][0]['outtmpl']).write_bytes(MP4)

        self.downloader.process_info.side_effect = process

    def write_input(self, links):
        pd.DataFrame({'Video Links': links}).to_excel(self.source, index=False)

    def read_report(self):
        return pd.read_excel(self.source.with_name('posts_descargas.xlsx'),
                             dtype=str, keep_default_na=False)

    def download(self, video_id='123'):
        return videos.download_video(url(video_id), video_id, self.directory, self.backend)

    def test_url_validation_and_cleaning(self):
        self.assertEqual(videos.validate_url(url('001') + '?x=1#fragment'), (url('001'), '001'))
        for value in (None, '', 'http://www.tiktok.com/@a/video/1',
                      'https://evil.com/@a/video/1', url('../x'), url('abc'),
                      'https://www.tiktok.com:443/@a/video/1',
                      'https://u@www.tiktok.com/@a/video/1', url('1') + '/extra'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                videos.validate_url(value)

    def test_file_header_size_and_directory(self):
        path = self.root / 'test.mp4'
        for data, expected in ((MP4, True), (b'X' * 2048, False),
                               (MP4[:100], False),
                               (struct.pack('>I', 99999) + MP4[4:], False)):
            path.write_bytes(data)
            self.assertEqual(videos.validate_file(path), expected)
        self.assertFalse(videos.validate_file(self.root))
        self.assertFalse(videos.validate_file(self.root / 'missing'))

    def test_success_context_options_and_single_extraction(self):
        self.assertEqual(self.download(), ('downloaded', '', False))
        self.assertTrue(videos.validate_file(self.directory / '123.mp4'))
        self.downloader.extract_info.assert_called_once_with(url('123'), download=False)
        self.downloader.process_info.assert_called_once()
        self.backend.return_value.__exit__.assert_called_once()
        options = self.backend.call_args[0][0]
        for key in ('retries', 'fragment_retries', 'extractor_retries', 'file_access_retries'):
            self.assertEqual(options[key], 0)
        self.assertEqual(options['max_filesize'], 200 * 1024 * 1024)
        self.assertEqual(options['socket_timeout'], 30)
        self.assertEqual(options['sleep_interval_requests'], 2)
        self.assertEqual(options['sleep_interval'], 2)
        self.assertEqual(options['postprocessors'], [])
        self.assertEqual(options['fixup'], 'never')
        self.assertIsInstance(hash(options['logger']), int)

    def test_existing_file_reused_and_invalid_untouched(self):
        self.directory.mkdir()
        target = self.directory / '123.mp4'
        for data, status in ((MP4, 'existing'), (b'invalid', 'error')):
            target.write_bytes(data)
            self.assertEqual(self.download()[0], status)
            self.assertEqual(target.read_bytes(), data)
        target.unlink()
        target.mkdir()
        self.assertEqual(self.download()[0], 'error')
        self.assertTrue(target.is_dir())
        self.backend.assert_not_called()

    def test_wrong_id_playlist_audio_only_and_missing_format(self):
        for info in ({'id': '999'}, {'id': '123', '_type': 'playlist'},
                     {'id': '123', 'ext': 'mp4', 'vcodec': 'none', 'acodec': 'aac'},
                     {'id': '123', 'formats': []}):
            with self.subTest(info=info):
                self.downloader.extract_info.side_effect = None
                self.downloader.extract_info.return_value = info
                self.assertEqual(self.download()[0], 'error')
                self.downloader.process_info.assert_not_called()

    def test_fragmented_format_and_extractor_format_error_do_not_download(self):
        original = self.downloader.extract_info.side_effect
        info = original(url('123'), False)
        info['formats'][0]['protocol'] = 'm3u8_native'
        self.downloader.extract_info.side_effect = None
        self.downloader.extract_info.return_value = info
        self.assertEqual(self.download()[0], 'error')
        self.downloader.extract_info.side_effect = RuntimeError('Requested format is not available')
        self.assertEqual(self.download()[0], 'error')
        self.downloader.process_info.assert_not_called()

    def test_known_and_unknown_size_and_final_validation(self):
        original = self.downloader.extract_info.side_effect
        info = original(url('123'), False)
        info['formats'][0]['filesize'] = videos.MAX_BYTES + 1
        self.downloader.extract_info.side_effect = None
        self.downloader.extract_info.return_value = info
        self.assertIn('200 MiB', self.download()[1])
        self.downloader.process_info.assert_not_called()
        self.downloader.extract_info.side_effect = original

        def oversized(info):
            hook = self.backend.call_args[0][0]['progress_hooks'][0]
            hook({'downloaded_bytes': videos.MAX_BYTES + 1})

        self.downloader.process_info.side_effect = oversized
        self.assertIn('200 MiB', self.download()[1])
        self.downloader.process_info.side_effect = lambda info: Path(
            self.backend.call_args[0][0]['outtmpl']).write_bytes(b'X' * 2048)
        self.assertIn('ftyp', self.download()[1])
        self.assertFalse((self.directory / '123.mp4').exists())

    def test_actual_final_bytes_enforce_limit_without_hook(self):
        with patch('descargar_videos.MAX_BYTES', 1500):
            self.assertEqual(self.download()[0], 'error')
        self.assertFalse((self.directory / '123.mp4').exists())
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_hook_checks_reported_totals_and_actual_partial_size(self):
        def process(info):
            options = self.backend.call_args[0][0]
            hook = options['progress_hooks'][0]
            for key in ('total_bytes', 'total_bytes_estimate'):
                with self.assertRaises(ValueError):
                    hook({key: videos.MAX_BYTES + 1})
            partial = Path(options['outtmpl'] + '.part')
            partial.write_bytes(MP4)
            with patch('descargar_videos.MAX_BYTES', 1500):
                hook({'tmpfilename': str(partial)})

        self.downloader.process_info.side_effect = process
        self.assertIn('200 MiB', self.download()[1])
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_cleanup_only_own_partial_and_no_retry_after_403(self):
        self.directory.mkdir()
        prior = self.directory / '123.mp4.part'
        prior.write_bytes(b'keep')

        def fail(info):
            Path(self.backend.call_args[0][0]['outtmpl'] + '.part').write_bytes(b'new')
            raise RuntimeError('HTTP Error 403 https://media.invalid/?token=secret')

        self.downloader.process_info.side_effect = fail
        status, error, restricted = self.download()
        self.assertEqual(status, 'error')
        self.assertTrue(restricted)
        self.assertNotIn('secret', error)
        self.assertEqual(prior.read_bytes(), b'keep')
        self.assertEqual(list(self.directory.iterdir()), [prior])
        self.downloader.process_info.assert_called_once()

    def test_ten_unique_ids_text_and_invalid_rows(self):
        ids = ['0001234567890123456789'] + [str(i) for i in range(1, 12)]
        self.write_input([url(ids[0]) + '?share=1', url(ids[0]), 'invalid']
                         + [url(item) for item in ids[1:]])
        with patch('descargar_videos.time.sleep') as sleep:
            videos.run(self.source, self.backend)
        report = self.read_report()
        self.assertEqual(self.downloader.extract_info.call_count, 10)
        self.assertEqual(sleep.call_count, 9)
        self.assertEqual(report.iloc[0]['Video ID'], ids[0])
        self.assertEqual(report.iloc[0]['Video File'], 'videos/' + ids[0] + '.mp4')
        self.assertEqual(report.iloc[1]['Download Status'], 'duplicate')
        self.assertEqual(report.iloc[2]['Download Status'], 'invalid')
        self.assertEqual(list(report['Download Status']).count('limit'), 2)
        self.assertNotIn('signature', report.to_string())
        from openpyxl import load_workbook
        workbook = load_workbook(self.source.with_name('posts_descargas.xlsx'))
        try:
            self.assertEqual(workbook.active['B2'].data_type, 's')
        finally:
            workbook.close()

    def test_restrictions_stop_queries_and_persist(self):
        for message in ('HTTP Error 403', 'HTTP Error 429', 'CAPTCHA required',
                        'Login required', 'You must be logged in',
                        'Only available for registered users'):
            with self.subTest(message=message):
                self.write_input([url('1'), url('2'), url('3')])
                self.downloader.extract_info.reset_mock()
                self.downloader.extract_info.side_effect = RuntimeError(message)
                with patch('descargar_videos.time.sleep') as sleep:
                    videos.run(self.source, self.backend)
                self.downloader.extract_info.assert_called_once()
                sleep.assert_not_called()
                self.assertEqual(list(self.read_report()['Download Status']),
                                 ['error', 'not_queried', 'not_queried'])

    def test_progress_saved_before_each_next_query_and_pause_after_error(self):
        self.write_input([url('1'), url('2'), url('3')])
        events = []
        original = self.downloader.extract_info.side_effect

        def extract(link, download):
            report = self.read_report()
            if link == url('1'):
                self.assertEqual(report.iloc[0]['Download Status'], 'pending')
                events.append('first')
                raise RuntimeError('Network error https://secret.invalid/token')
            if link == url('2'):
                self.assertEqual(report.iloc[0]['Download Status'], 'error')
            else:
                self.assertEqual(report.iloc[1]['Download Status'], 'downloaded')
            events.append(link)
            return original(link, download)

        self.downloader.extract_info.side_effect = extract
        with patch('descargar_videos.time.sleep', side_effect=lambda n: events.append(n)):
            videos.run(self.source, self.backend)
        self.assertEqual(events, ['first', 2, url('2'), 2, url('3')])
        self.assertNotIn('secret', self.read_report().to_string())

    def test_cancellation_cleans_and_saves_pending(self):
        self.write_input([url('1'), url('2')])

        def cancel(info):
            Path(self.backend.call_args[0][0]['outtmpl'] + '.part').write_bytes(b'new')
            raise KeyboardInterrupt()

        self.downloader.process_info.side_effect = cancel
        with self.assertRaises(KeyboardInterrupt):
            videos.run(self.source, self.backend)
        self.assertEqual(list(self.directory.iterdir()), [])
        self.assertEqual(list(self.read_report()['Download Status']),
                         ['cancelled', 'not_queried'])
        self.backend.return_value.__exit__.assert_called_once()

    def test_run_reuses_existing_files_without_backend_or_pause(self):
        self.write_input([url('1'), url('2')])
        self.directory.mkdir()
        (self.directory / '1.mp4').write_bytes(MP4)
        (self.directory / '2.mp4').write_bytes(b'keep invalid')
        with patch('descargar_videos.load_backend') as load, patch(
                'descargar_videos.time.sleep') as sleep:
            videos.run(self.source)
        load.assert_not_called()
        sleep.assert_not_called()
        self.assertEqual(list(self.read_report()['Download Status']), ['existing', 'error'])
        self.assertEqual((self.directory / '2.mp4').read_bytes(), b'keep invalid')

    def test_unsafe_directory_and_mismatched_argument_make_no_requests(self):
        self.directory.write_bytes(b'not a directory')
        self.assertEqual(self.download()[0], 'error')
        self.assertEqual(self.directory.read_bytes(), b'not a directory')
        with self.assertRaises(ValueError):
            videos.download_video(url('123'), '../123', self.directory, self.backend)
        self.backend.assert_not_called()

    def test_missing_column_and_missing_backend(self):
        pd.DataFrame({'other': ['x']}).to_excel(self.source, index=False)
        with self.assertRaisesRegex(ValueError, 'Video Links'):
            videos.run(self.source, self.backend)
        with patch('descargar_videos.sys.version_info', (3, 12)), patch.dict(
                'sys.modules', {'yt_dlp': None}):
            with self.assertRaisesRegex(RuntimeError, 'requirements_videos.txt'):
                videos.load_backend()

    def test_destination_created_during_download_is_not_overwritten(self):
        original = self.downloader.process_info.side_effect

        def race(info):
            original(info)
            (self.directory / '123.mp4').write_bytes(b'other writer')

        self.downloader.process_info.side_effect = race
        self.assertEqual(self.download()[0], 'error')
        self.assertEqual((self.directory / '123.mp4').read_bytes(), b'other writer')

    def test_cli_does_not_report_success_when_downloads_failed(self):
        report = self.root / 'report.xlsx'
        for statuses, expected in [(['downloaded'], 0), (['error', 'not_queried'], 1),
                                   (['existing', 'error'], 1), ([], 1)]:
            with self.subTest(statuses=statuses):
                pd.DataFrame({'Download Status': statuses}).to_excel(report, index=False)
                with patch('descargar_videos.sys.argv', ['descargar_videos.py', str(self.source)]):
                    with patch('descargar_videos.sys.version_info', (3, 12)):
                        with patch('descargar_videos.run', return_value=report):
                            self.assertEqual(videos.main(), expected)


class BrowserMetadataTests(unittest.TestCase):
    def setUp(self):
        context = patch('playwright.sync_api.sync_playwright')
        self.context = context.start()
        self.addCleanup(context.stop)
        playwright = self.context.return_value.__enter__.return_value
        self.browser = playwright.chromium.launch.return_value
        self.page = self.browser.new_page.return_value
        self.page.url = url('123')
        self.page.goto.return_value.status = 200
        self.page.locator.return_value.first.is_visible.return_value = False
        self.page.evaluate.return_value = 'Test browser'
        self.item = {
            'id': '123', 'video': {'playAddr': 'https://media.invalid/123.mp4',
                                  'format': 'mp4', 'codecType': 'h264'},
        }
        self.page.wait_for_function.return_value.json_value.return_value = {
            'itemInfo': {'itemStruct': self.item},
        }

    def test_reads_public_player_metadata_and_closes_browser(self):
        info = videos.read_video_metadata(url('123'))
        self.assertEqual(info['id'], '123')
        self.assertEqual(info['formats'][0]['url'], 'https://media.invalid/123.mp4')
        self.assertEqual(info['formats'][0]['http_headers']['Referer'], url('123'))
        self.browser.close.assert_called_once()

    def test_rejects_foreign_video_and_download_disabled(self):
        for change, message in [({'id': '456'}, 'ID obtenido'),
                                ({'itemControl': {'canDownload': False}}, 'no permite descarga')]:
            with self.subTest(change=change):
                original = dict(self.item)
                self.item.update(change)
                with self.assertRaisesRegex(ValueError, message):
                    videos.read_video_metadata(url('123'))
                self.item.clear()
                self.item.update(original)

    def test_does_not_continue_after_access_restriction(self):
        for status in (403, 429):
            with self.subTest(status=status):
                self.page.goto.return_value.status = status
                with self.assertRaisesRegex(ValueError, str(status)):
                    videos.read_video_metadata(url('123'))
        self.page.wait_for_function.assert_not_called()

    def test_stops_on_captcha(self):
        self.page.locator.return_value.first.is_visible.return_value = True
        with self.assertRaisesRegex(ValueError, 'CAPTCHA'):
            videos.read_video_metadata(url('123'))
        self.browser.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()

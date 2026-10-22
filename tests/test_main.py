import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import main
from configuracion import ScraperConfig


class ConfigurationTests(unittest.TestCase):
    def test_defaults_and_invalid_values(self):
        config = ScraperConfig()
        self.assertEqual((config.videos, config.comments, config.video_delay), (10, 20, 2))
        for kwargs in ({'videos': 0}, {'comments': True}, {'video_delay': 1},
                       {'comment_wait': 0}, {'video_delay': float('nan')},
                       {'link_method': 'requests'}, {'headless': 'yes'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ScraperConfig(**kwargs)


class MainTests(unittest.TestCase):
    def test_cli_passes_configuration_and_engine(self):
        with patch('main.execute', return_value={}) as execute:
            result = main.main(['--usuario', '@demo', '--videos', '3', '--comentarios', '12',
                                '--pausa', '3', '--espera-comentarios', '4',
                                '--enlaces', 'beautifulsoup', '--sin-ventana'])
        self.assertEqual(result, 0)
        username, config, directory, engine = execute.call_args.args
        self.assertEqual(username, 'demo')
        self.assertEqual((config.videos, config.comments, config.video_delay, config.comment_wait), (3, 12, 3, 4))
        self.assertTrue(config.headless)
        self.assertEqual(engine.method, 'heuristica_v1')

    def test_invalid_configuration_does_not_open_tiktok(self):
        with patch('main.execute') as execute:
            self.assertEqual(main.main(['--usuario', 'demo', '--pausa', '1']), 1)
        execute.assert_not_called()

    def test_valid_tiktok_name_reserved_by_windows_uses_safe_output_path(self):
        data = ({'id_perfil': 'CON', 'Bio': ''}, [], [])
        with patch('main.collect', new=AsyncMock(return_value=data)):
            with patch('main.export_raw', return_value={}) as raw:
                with patch('main.export_analysis', return_value=Path('analisis.xlsx')):
                    main.execute('CON', ScraperConfig())
        self.assertEqual(raw.call_args.args[3], Path('usuario_CON'))

    def test_raw_files_survive_analysis_failure(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            profile = {'id_perfil': 'demo', 'Bio': 'Soy sociable'}
            with patch('main.collect', new=AsyncMock(return_value=(profile, [], []))):
                with patch('main.export_analysis', side_effect=ValueError('Error de prueba')):
                    with self.assertRaisesRegex(ValueError, 'Error de prueba'):
                        main.execute('demo', ScraperConfig(), directory)
            self.assertEqual(len(list(Path(directory).glob('*.xlsx'))), 3)

    def test_all_four_outputs_and_repeated_runs_do_not_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            data = ({'id_perfil': 'demo', 'Bio': ''}, [], [])
            with patch('main.collect', new=AsyncMock(return_value=data)):
                first = main.execute('demo', ScraperConfig(), directory)
                second = main.execute('demo', ScraperConfig(), directory)
            self.assertEqual(set(first), {'perfil', 'posts', 'comentarios', 'bigfive'})
            self.assertEqual(len(list(Path(directory).glob('*.xlsx'))), 8)
            self.assertTrue(set(first.values()).isdisjoint(second.values()))


if __name__ == '__main__':
    unittest.main()

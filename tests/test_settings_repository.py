"""Testes da persistencia local e do runtime config builder."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from domain.settings.entities import RatioRegion, UserSettings
from infrastructure.persistence.settings_repository import AppDataSettingsRepository
from infrastructure.runtime_config import RuntimeConfigBuilder


class SettingsRepositoryTest(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / 'settings.json'
            repository = AppDataSettingsRepository(settings_path=settings_path)
            settings = UserSettings(
                window_title='Google Play Games',
                cv_profile='cv_17',
                bottom_region=RatioRegion(0.0, 0.70, 1.0, 0.30),
            )

            repository.save(settings)
            loaded = repository.load()

            self.assertIsNotNone(loaded)
            self.assertEqual('Google Play Games', loaded.window_title)
            self.assertEqual('cv_17', loaded.cv_profile)
            self.assertEqual(0.30, loaded.bottom_region.h_ratio)

    def test_runtime_config_builder_applies_user_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / 'settings.json'
            template_path = Path(tmpdir) / 'config.example.yaml'
            template_path.write_text(
                'window:\n'
                '  title_contains: "Google Play Games"\n'
                '  title_match_mode: contains\n'
                '  activate_before_click: true\n'
                'runtime:\n'
                '  dry_run: true\n'
                '  debug_dir: "debug_saida"\n'
                'battle_bar:\n'
                '  enabled: false\n',
                encoding='utf-8',
            )
            repository = AppDataSettingsRepository(settings_path=settings_path)
            builder = RuntimeConfigBuilder(repository=repository, template_path=template_path)
            settings = UserSettings(window_title='Clash of Clans', window_match_mode='exact', dry_run=True)

            cfg, returned_path = builder.build(settings)

            self.assertEqual(template_path, returned_path)
            self.assertEqual('Clash of Clans', cfg['window']['title_contains'])
            self.assertEqual('exact', cfg['window']['title_match_mode'])
            self.assertFalse(cfg['runtime']['dry_run'])

    def test_runtime_config_builder_applies_selected_cv_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / 'settings.json'
            template_path = Path(tmpdir) / 'config.example.yaml'
            template_path.write_text(
                'window:\n'
                '  title_contains: "Clash of Clans"\n'
                'runtime:\n'
                '  dry_run: true\n'
                '  debug_dir: "debug_saida"\n'
                'deployment:\n'
                '  marker: base\n'
                'cv_profiles:\n'
                '  cv_14:\n'
                '    deployment:\n'
                '      marker: cv14\n',
                encoding='utf-8',
            )
            repository = AppDataSettingsRepository(settings_path=settings_path)
            builder = RuntimeConfigBuilder(repository=repository, template_path=template_path)

            cfg, _ = builder.build(UserSettings(cv_profile='cv_14'))

            self.assertEqual('cv_14', cfg['runtime']['cv_profile'])
            self.assertEqual('cv14', cfg['deployment']['marker'])


if __name__ == '__main__':
    unittest.main()

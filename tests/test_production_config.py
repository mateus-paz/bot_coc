"""Testes da configuracao real incorporada ao executavel desktop."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from domain.settings.entities import UserSettings
from infrastructure.persistence.settings_repository import AppDataSettingsRepository
from infrastructure.runtime_config import RuntimeConfigBuilder


class ProductionConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        settings_path = Path(self.tmpdir.name) / 'settings.json'
        repository = AppDataSettingsRepository(settings_path=settings_path)
        self.builder = RuntimeConfigBuilder(
            repository=repository,
            template_path=Path('config.yaml').resolve(),
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _build(self, profile: str):
        return self.builder.build(
            UserSettings(cv_profile=profile, dry_run=True)
        )[0]

    def test_real_clicks_are_forced_for_every_profile(self) -> None:
        for profile in ('cv_13', 'cv_14', 'cv_17'):
            with self.subTest(profile=profile):
                cfg = self._build(profile)
                self.assertFalse(cfg['runtime']['dry_run'])
                self.assertEqual('start_button', cfg['flow']['pre_search_steps'][0])
                self.assertTrue(cfg['flow']['battle_zoom_out']['enabled'])
                self.assertEqual(12, cfg['flow']['battle_zoom_out']['scroll_clicks'])

    def test_cv13_and_cv14_share_script_and_cv17_is_distinct(self) -> None:
        cv13 = self._build('cv_13')
        cv14 = self._build('cv_14')
        cv17 = self._build('cv_17')

        self.assertEqual('scripted', cv13['deployment']['mode'])
        self.assertEqual(
            cv13['deployment']['scripted']['actions'],
            cv14['deployment']['scripted']['actions'],
        )
        self.assertNotEqual(
            cv13['deployment']['scripted']['actions'],
            cv17['deployment']['scripted']['actions'],
        )

    def test_all_runtime_assets_exist_inside_assets_directory(self) -> None:
        cfg = self._build('cv_17')
        referenced = set(cfg['flow']['pre_search_steps'])
        referenced.update(cfg['flow'].get('optional_pre_search_steps', []))
        referenced.update(cfg['flow'].get('battle_finished_assets', []))
        referenced.update(cfg['flow'].get('return_steps', []))

        for key in referenced:
            with self.subTest(asset=key):
                self.assertIn(key, cfg['assets'])
                self.assertTrue((Path('config.yaml').parent / cfg['assets'][key]).exists())

    def test_fixed_coordinate_scripts_do_not_enable_battle_bar_analysis(self) -> None:
        for profile in ('cv_13', 'cv_14', 'cv_17'):
            with self.subTest(profile=profile):
                self.assertNotIn('battle_bar', self._build(profile))


if __name__ == '__main__':
    unittest.main()

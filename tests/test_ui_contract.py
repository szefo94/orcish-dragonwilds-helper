"""UI contract tests for the shared command center and in-game HUD layout."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'/'orcpresser'

class UIContract(unittest.TestCase):
    def test_fishing_does_not_duplicate_game_binding(self):
        text=(SRC/'fishing_ui.py').read_text(encoding='utf-8')
        self.assertNotIn("BIND GAME",text)
        self.assertNotIn("app.bind_game",text)

    def test_shell_has_one_shared_command_center(self):
        text=(SRC/'app.py').read_text(encoding='utf-8')
        self.assertIn("'COMMAND CENTER'",text)
        self.assertIn("'GAME & CAPTURE'",text)
        self.assertIn("def update_command_center",text)

    def test_status_hud_stacks_cards_in_middle_left_rail(self):
        text=(SRC/'status_overlay.py').read_text(encoding='utf-8')
        self.assertIn("def _card",text)
        self.assertIn("cursor=max(margin,(h-total)//2)",text)
        self.assertIn("cursor=self._card",text)
        self.assertNotIn('if pos=="tr"',text)
        self.assertNotIn('elif pos=="bl"',text)
        self.assertNotIn('else:x1,y1=max(margin,w-margin-max_w)',text)

    def test_fishing_spot_region_is_disabled_in_ui(self):
        text=(SRC/'fishing_ui.py').read_text(encoding='utf-8')
        self.assertNotIn("('spot','SPOT')",text)
        self.assertIn('SPOT was an early cast-location experiment',text)

if __name__=='__main__':
    unittest.main()

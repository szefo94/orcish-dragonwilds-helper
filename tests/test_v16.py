"""1.6: GameProfile derivation, persistent settings (exclusions survive restart)."""
import unittest, tempfile, json
from pathlib import Path
from unittest.mock import Mock
from game_profile import GameProfile, Dragonwilds
from settings import Settings

class Valheimish(GameProfile):          # a derived profile, as FRAMEWORK.md describes
    name='Other'
    window_match=('othergame',)
    actions=(('Pick up',r'^pick up\b'),('Open',r'^open\b'))
    requires_hold=('Open',)

class Profiles(unittest.TestCase):
    def test_dragonwilds_behaviour_unchanged(self):
        d=Dragonwilds()
        self.assertEqual(d.classify('Collect  Water'),'Collect Water')
        self.assertEqual(d.classify('collect stone'),'Collect')
        self.assertIsNone(d.classify('Chop'))
        self.assertFalse(d.accept('Siphon',False));self.assertTrue(d.accept('Siphon',True))
        self.assertTrue(d.matches_window('RSDragonwilds','x.exe'));self.assertFalse(d.matches_window('Notepad','notepad.exe'))
    def test_derived_profile(self):
        v=Valheimish()
        self.assertEqual(v.action_names,('Pick up','Open'))
        self.assertEqual(v.classify('Pick up Wood'),'Pick up')
        self.assertFalse(v.accept('Open',False))
        self.assertEqual(v.keycap_min_bright,GameProfile.keycap_min_bright)   # inherited default
        self.assertTrue(GameProfile().matches_window('anything','any.exe'))  # base: any window

class SettingsTests(unittest.TestCase):
    def test_roundtrip_per_profile(self):
        f=Path(tempfile.mkdtemp())/'settings.json'
        s=Settings(f,'Dragonwilds');s.set('exclude','Stone,Cabbage');s.save()
        o=Settings(f,'Other');o.set('exclude','Wood');o.save()
        self.assertEqual(Settings(f,'Dragonwilds').get('exclude'),'Stone,Cabbage')
        self.assertEqual(Settings(f,'Other').get('exclude'),'Wood')
    def test_corrupt_file_gives_defaults(self):
        f=Path(tempfile.mkdtemp())/'settings.json';f.write_text('{broken')
        self.assertEqual(Settings(f,'Dragonwilds').get('exclude',''),'')
    def test_app_persists_exclusion_on_change_and_close(self):
        from app import App
        f=Path(tempfile.mkdtemp())/'settings.json'
        a=App.__new__(App);a.settings=Settings(f,'Dragonwilds');a.save_job=None;a.root=Mock()
        a.persist('exclude','Stone');a.root.after.assert_called()
        a.settings.save();self.assertEqual(json.loads(f.read_text())['Dragonwilds']['exclude'],'Stone')


class Selection(unittest.TestCase):
    def test_load_by_name(self):
        from game_profile import load
        self.assertEqual(load('dragonwilds').name,'Dragonwilds')
        self.assertEqual(load('Other').name,'Other')          # Valheimish above is a registered subclass
        with self.assertRaises(SystemExit):load('nope')
if __name__=='__main__':unittest.main()

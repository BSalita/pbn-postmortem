import unittest
from unittest.mock import patch

import pbn_postmortem_api_server as api


class FrameResolutionTests(unittest.TestCase):
    def test_bbo_url_generates_then_returns_frame(self):
        url = "https://www.bridgebase.com/tools/handviewer.html?lin=pn|A,B,C,D|md|3S|"
        meta = {"key": "handviewer-abc", "url": url}
        frame = object()
        with patch.object(api, "_generate_isolated", return_value=meta) as gen:
            with patch.object(api.service, "load_postmortem", return_value=(frame, meta)) as load:
                loaded, loaded_meta = api._frame(url=url)
                self.assertIs(loaded, frame)
                self.assertEqual(loaded_meta["key"], "handviewer-abc")
                gen.assert_called_once_with(url)
                load.assert_called_once_with("handviewer-abc")

    def test_cache_key_loads_without_generate(self):
        sentinel = (object(), {"key": "handviewer-deadbeef"})
        with patch.object(api, "_generate_isolated") as gen:
            with patch.object(api.service, "load_postmortem", return_value=sentinel) as load:
                self.assertIs(api._frame(key="handviewer-deadbeef"), sentinel)
                load.assert_called_once_with("handviewer-deadbeef")
                gen.assert_not_called()

    def test_generate_isolated_raises_on_nonzero_exit(self):
        completed = type("P", (), {"returncode": 1, "stderr": "boom", "stdout": ""})()
        with patch.object(api.subprocess, "run", return_value=completed):
            with self.assertRaises(RuntimeError) as ctx:
                api._generate_isolated("https://example.com/game.pbn")
            self.assertIn("boom", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

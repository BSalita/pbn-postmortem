import unittest
from unittest.mock import patch

import pbn_postmortem_api_server as api


class FrameResolutionTests(unittest.TestCase):
    def test_bbo_url_generates_then_returns_frame(self):
        url = "https://www.bridgebase.com/tools/handviewer.html?lin=pn|A,B,C,D|md|3S|"
        sentinel = (object(), {"key": "handviewer-abc", "url": url})
        with patch.object(api.create, "generate_postmortem", return_value=sentinel) as gen:
            with patch.object(api.service, "load_postmortem") as load:
                self.assertIs(api._frame(url=url), sentinel)
                gen.assert_called_once_with(url)
                load.assert_not_called()

    def test_cache_key_loads_without_generate(self):
        sentinel = (object(), {"key": "handviewer-deadbeef"})
        with patch.object(api.create, "generate_postmortem") as gen:
            with patch.object(api.service, "load_postmortem", return_value=sentinel) as load:
                self.assertIs(api._frame(key="handviewer-deadbeef"), sentinel)
                load.assert_called_once_with("handviewer-deadbeef")
                gen.assert_not_called()


if __name__ == "__main__":
    unittest.main()

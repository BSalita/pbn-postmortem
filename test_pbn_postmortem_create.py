import unittest
from urllib.parse import quote

import pbn_postmortem_create as create

HANDVIEWER = (
    "https://www.bridgebase.com/tools/handviewer.html?lin="
    + quote(
        "pn|Etha,Brill,Brill,Brill|md|3SQT82HAT32DA86CA5,SJ763H874DT92CK84,"
        "SAKHKJ6D543CJ7632,S954HQ95DKQJ7CQT9|rh||ah|Board 1|sv|o|mb|1C|mb|p|"
        "mb|1H|mb|p|mb|1N|mb|p|mb|3N|mb|p|mb|p|mb|p|pg||"
    )
)


class SourceUrlTests(unittest.TestCase):
    def test_embedded_lin_from_handviewer(self):
        body = create.lin_payload_from_url(HANDVIEWER)
        self.assertIsNotNone(body)
        self.assertTrue(body.startswith("pn|Etha"))
        self.assertIsNone(create.lin_fetch_url_from_url(HANDVIEWER))
        self.assertEqual(create.input_suffix(HANDVIEWER), ".html")
        self.assertEqual(str(create.display_path_for_source(HANDVIEWER, ".lin")), "handviewer.lin")

    def test_linurl_parameter(self):
        url = (
            "https://www.bridgebase.com/tools/handviewer.html"
            "?linurl=https://www.bridgebase.com/tools/vugraph_linfetch.php?id=74447"
        )
        self.assertIsNone(create.lin_payload_from_url(url))
        self.assertEqual(
            create.lin_fetch_url_from_url(url),
            "https://www.bridgebase.com/tools/vugraph_linfetch.php?id=74447",
        )

    def test_pbn_suffix_ignores_query(self):
        url = "https://raw.githubusercontent.com/org/repo/foo.pbn?token=1"
        self.assertEqual(create.input_suffix(url), ".pbn")
        self.assertIsNone(create.lin_payload_from_url(url))

    def test_local_lin_suffix(self):
        self.assertEqual(create.input_suffix("3494191054-1682343601-bsalita.lin"), ".lin")

    def test_empty_url_rejected(self):
        with self.assertRaises(ValueError):
            create.load_boards_from_source("")

    def test_unsupported_html_without_lin(self):
        with self.assertRaises(ValueError):
            create.load_boards_from_source("https://example.com/page.html")


class LoadEmbeddedLinTests(unittest.TestCase):
    def test_handviewer_parses_one_board(self):
        boards, path_url, kind = create.load_boards_from_source(HANDVIEWER)
        self.assertEqual(kind, "lin")
        self.assertEqual(len(boards), 1)
        self.assertEqual(boards[0].board_num, 1)
        self.assertEqual(str(path_url), "handviewer.lin")


if __name__ == "__main__":
    unittest.main()

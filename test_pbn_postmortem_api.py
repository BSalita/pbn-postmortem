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


class FakeClaimChecker:
    def __init__(self, supported=True, error=None):
        self.supported = supported
        self.error = error
        self.calls = []

    def claim_supported(self):
        return self.supported

    def check_claim(self, deal, strain, declarer, plays, **kwargs):
        self.calls.append((deal, strain, declarer, plays, kwargs))
        if self.error:
            raise ValueError(self.error)
        return {"verdict": "valid", "tricks_won": 5, "tricks_left": 5, "nodes": 705}


class ClaimTests(unittest.TestCase):
    DEAL = "N:AQ... ..32. 32... K4..."

    def _post(self, checker, **fields):
        body = {"deal": self.DEAL, "strain": "NT", "declarer": "s", **fields}
        with patch.object(api, "_claim_checker", return_value=checker):
            return api.claim(api.ClaimRequest(**body))

    def test_claim_passes_the_play_and_returns_the_verdict(self):
        checker = FakeClaimChecker()
        result = self._post(checker, plays="HQ HJ", total_tricks=7, claimer="w")
        self.assertEqual(result["verdict"], "valid")
        self.assertEqual((result["declarer"], result["claimer"], result["plays"]), ("S", "W", 2))
        deal, strain, declarer, plays, kwargs = checker.calls[0]
        self.assertEqual(plays, ["HQ", "HJ"])
        self.assertEqual(kwargs["total_tricks"], 7)
        self.assertEqual(kwargs["claimer"], "w")

    def test_claim_accepts_a_list_of_cards(self):
        checker = FakeClaimChecker()
        self._post(checker, plays=["SA", "S2"])
        self.assertEqual(checker.calls[0][3], ["SA", "S2"])

    def test_bad_input_is_422(self):
        with self.assertRaises(api.HTTPException) as ctx:
            self._post(FakeClaimChecker(error="CheckClaimPBN error -98"))
        self.assertEqual(ctx.exception.status_code, 422)
        with self.assertRaises(api.HTTPException) as ctx:
            self._post(FakeClaimChecker(), budget=0)
        self.assertEqual(ctx.exception.status_code, 422)

    def test_a_library_without_claims_is_503(self):
        with self.assertRaises(api.HTTPException) as ctx:
            self._post(FakeClaimChecker(supported=False))
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()

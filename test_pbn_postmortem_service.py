import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import polars as pl

os.environ.setdefault("PBN_POSTMORTEM_CACHE_DIR", tempfile.mkdtemp(prefix="pbn-cache-"))

import pbn_postmortem_service as service


class CacheKeyTests(unittest.TestCase):
    def test_same_url_is_stable(self):
        url = "https://example.com/hands/game.pbn"
        self.assertEqual(service.url_to_cache_key(url), service.url_to_cache_key(url))

    def test_distinct_urls_with_same_name_differ(self):
        a = service.url_to_cache_key("https://a.example/game.pbn")
        b = service.url_to_cache_key("https://b.example/game.pbn")
        self.assertNotEqual(a, b)


class CacheRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pbn-svc-"))
        self.cache_patch = patch.object(service, "CACHE_DIR", self.tmp)
        self.cache_patch.start()
        service._df_cache.clear()

    def tearDown(self):
        self.cache_patch.stop()

    def test_save_list_load_sql_schema(self):
        df = pl.DataFrame(
            {
                "Board": [1, 2],
                "Contract": ["3NT", "4S"],
                "Date": ["2026-09-03", "2026-09-03"],
            }
        )
        url = "https://example.com/hands/sample.pbn"
        service.save_augmented_df_to_cache(df, url)
        listed = service.list_cached_postmortems()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["url"], url)

        loaded, meta = service.load_postmortem(listed[0]["key"])
        self.assertEqual(meta["url"], url)
        self.assertEqual(loaded.height, 2)

        schema = service.schema_columns(loaded, pattern="^Con")
        self.assertIn("Contract", schema["columns"])

        try:
            result = service.run_sql(loaded, "SELECT Board, Contract FROM self ORDER BY Board")
        except ImportError:
            self.skipTest("DuckDB/pyarrow unavailable in this environment")
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["rows"][0]["Contract"], "3NT")


if __name__ == "__main__":
    unittest.main()

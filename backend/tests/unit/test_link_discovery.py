from __future__ import annotations

import unittest

from backend.app.services.link_discovery import (
    discover_links,
    is_taiwan_government_host,
)


class LinkDiscoveryTests(unittest.TestCase):
    def test_extracts_only_main_content_and_normalizes_urls(self) -> None:
        html = """
        <html>
          <body>
            <nav>
              <a href="/menu">網站選單</a>
            </nav>
            <div id="CCMS_Content">
              <a href="#section">頁內目錄</a>
              <a href="/benefit?id=1#apply" title="喪葬補助申請">
                喪葬補助
              </a>
              <a href="/benefit?id=1">重複連結</a>
              <a href="javascript:void(0)">列印</a>
              <a href="https://example.com/info">外部說明</a>
            </div>
            <footer>
              <a href="/privacy">隱私權</a>
            </footer>
          </body>
        </html>
        """
        terms = {
            "high_precision_subsidy_phrases": ["喪葬補助"],
            "government_service_phrases": [],
            "related_financial_phrases": [],
            "death_event_low_precision": [],
            "funeral_service_terms": [],
            "economic_assistance_terms": [],
            "fee_schedule_terms": [],
            "fee_relief_terms": [],
        }

        candidates = discover_links(
            html,
            source_id="test_source",
            source_page_url="https://service.gov.tw/index",
            discovery_terms=terms,
        )

        self.assertEqual(len(candidates), 2)
        self.assertEqual(
            candidates[0].url,
            "https://service.gov.tw/benefit?id=1",
        )
        self.assertEqual(candidates[0].priority, "high")
        self.assertEqual(candidates[0].matched_terms, ("喪葬補助",))
        self.assertTrue(candidates[0].official_host)
        self.assertEqual(candidates[1].url, "https://example.com/info")
        self.assertEqual(candidates[1].priority, "review")
        self.assertFalse(candidates[1].official_host)

    def test_recognizes_taiwan_government_hosts(self) -> None:
        self.assertTrue(is_taiwan_government_host("www.gov.tw"))
        self.assertTrue(is_taiwan_government_host("law.moj.gov.tw"))
        self.assertTrue(is_taiwan_government_host("mso.gov.taipei"))
        self.assertFalse(is_taiwan_government_host("example.com"))


if __name__ == "__main__":
    unittest.main()

import csv
import json
import tempfile
import unittest
from pathlib import Path

from worker.ingestion.ad_report_parser import ParseError, parse_report


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "data" / "fixtures" / "商品推广_搜索词_报告_LED演示.xlsx"


class AdReportParserTests(unittest.TestCase):
    def test_golden_fixture_reconciles_and_matches_baseline(self):
        result = parse_report(FIXTURE)
        reconciliation = result["reconciliation"]
        self.assertTrue(reconciliation["passed"])
        self.assertTrue(reconciliation["repeat_parse_consistent"])
        self.assertEqual(reconciliation["raw_row_count"], 118)
        self.assertEqual(reconciliation["unique_keyword_count"], 91)
        self.assertEqual(reconciliation["repeated_keyword_count"], 16)
        self.assertEqual(reconciliation["duplicate_row_count"], 27)
        self.assertEqual(
            {field: reconciliation["header_mapping"][field]["label"] for field in ("keyword", "impressions", "clicks", "spend", "sales", "orders")},
            {"keyword": "客户搜索词", "impressions": "展示量", "clicks": "点击量", "spend": "花费", "sales": "7天总销售额", "orders": "7天总订单数(#)"},
        )
        self.assertEqual(reconciliation["raw_totals"]["impressions"], "1230627")
        self.assertEqual(reconciliation["raw_totals"]["clicks"], "9045")
        self.assertEqual(reconciliation["raw_totals"]["spend"], "5123.10")
        self.assertEqual(reconciliation["raw_totals"]["sales"], "20982.29")
        self.assertEqual(reconciliation["raw_totals"]["orders"], "1578")
        led = next(row for row in result["aggregated_rows"] if row["keyword"] == "led light")
        self.assertEqual({key: led[key] for key in ("impressions", "clicks", "spend", "sales", "orders")}, {"impressions": 15216, "clicks": 131, "spend": 82.96, "sales": 408.42, "orders": 30})
        self.assertAlmostEqual(led["ctr"], 131 / 15216, places=10)
        self.assertAlmostEqual(led["cvr"], 30 / 131, places=10)
        self.assertAlmostEqual(led["acos"], 82.96 / 408.42, places=10)
        samples = {
            "led strip lights for home": (4287, 70, 27.93, 241.51, 16),
            "room accessories": (3392, 43, 31.14, 58.14, 4),
        }
        for keyword, expected in samples.items():
            sampled = next(item for item in result["aggregated_rows"] if item["keyword"] == keyword)
            self.assertEqual(tuple(sampled[field] for field in ("impressions", "clicks", "spend", "sales", "orders")), expected)

    def test_dynamic_header_and_column_order_with_zero_sales(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["说明行", "此行不是表头"])
                writer.writerow(["客户搜索词", "订单", "销售额", "点击量", "展示量", "花费", "货币"])
                writer.writerow(["alpha", "0", "0", "2", "10", "$1.50", "USD"])
                writer.writerow(["alpha", "1", "10", "3", "20", "$2.50", "USD"])
            result = parse_report(path)
            row = result["aggregated_rows"][0]
            self.assertTrue(result["reconciliation"]["passed"])
            self.assertEqual(row["impressions"], 30)
            self.assertEqual(row["clicks"], 5)
            self.assertEqual(row["orders"], 1)
            self.assertEqual(row["sales"], 10)
            self.assertAlmostEqual(row["cpc"], 4 / 5)
            self.assertIsNotNone(row["acos"])

    def test_optional_ad_entity_columns_are_preserved_without_becoming_required(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "entities.csv"
            path.write_text(
                "广告活动名称,广告组名称,投放,匹配类型,客户搜索词,展示量,点击量,花费,销售额,订单\n"
                "Campaign A,Group A,led light,精准,led light,10,2,1.00,10,1\n"
                "Campaign B,Group B,led light,词组,led light,5,1,0.50,0,0\n",
                encoding="utf-8",
            )
            result = parse_report(path)
            row = result["aggregated_rows"][0]
            self.assertEqual(len(row["ad_entities"]), 2)
            self.assertEqual({item["campaign_name"] for item in row["ad_entities"]}, {"Campaign A", "Campaign B"})
            self.assertEqual({item["match_type"] for item in row["ad_entities"]}, {"精准", "词组"})
            self.assertEqual(set(result["reconciliation"]["entity_header_mapping"]), {"campaign_name", "ad_group_name", "target", "match_type"})

    def test_zero_sales_acos_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zero.csv"
            path.write_text("客户搜索词,展示量,点击量,花费,销售额,订单,货币\nzero,10,2,1.00,0,0,USD\n", encoding="utf-8")
            row = parse_report(path)["aggregated_rows"][0]
            self.assertIsNone(row["acos"])
            self.assertEqual(row["roas"], 0.0)

    def test_missing_numeric_values_remain_null_and_do_not_become_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.csv"
            path.write_text(
                "客户搜索词,展示量,点击量,花费,销售额,订单,货币\n"
                "unknown,10,2,NULL,0,0,USD\n",
                encoding="utf-8",
            )
            row = parse_report(path)["aggregated_rows"][0]
            self.assertIsNone(row["spend"])
            self.assertIsNone(row["cpc"])
            self.assertIsNone(row["acos"])
            self.assertEqual(row["missing_fields"], ["spend"])

    def test_multiple_currencies_fail_fast(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "multi.csv"
            path.write_text("客户搜索词,展示量,点击量,花费,销售额,订单,货币\na,1,1,1,1,1,USD\nb,1,1,1,1,1,EUR\n", encoding="utf-8")
            with self.assertRaisesRegex(ParseError, "multiple currencies"):
                parse_report(path)

    def test_additional_fixture_variants(self):
        dynamic = parse_report(ROOT / "data" / "fixtures" / "sample_dynamic_columns.csv")
        self.assertTrue(dynamic["reconciliation"]["passed"])
        self.assertEqual(dynamic["reconciliation"]["currency_code"], "USD")
        self.assertEqual(dynamic["reconciliation"]["unique_keyword_count"], 2)
        zero = parse_report(ROOT / "data" / "fixtures" / "sample_zero_sales.tsv")
        self.assertTrue(zero["reconciliation"]["passed"])
        self.assertIsNone(zero["aggregated_rows"][0]["acos"])

    def test_output_artifacts_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run"
            parse_report(FIXTURE, output)
            self.assertTrue((output / "ad-aggregated.json").is_file())
            self.assertTrue((output / "reconciliation.json").is_file())
            saved = json.loads((output / "reconciliation.json").read_text(encoding="utf-8"))
            self.assertTrue(saved["passed"])


    def test_input_rejects_symlinked_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "outside"
            outside.mkdir()
            source = outside / "report.csv"
            source.write_text("客户搜索词,展示量,点击量,花费,销售额,订单\na,1,1,1,1,1\n", encoding="utf-8")
            link_dir = Path(directory) / "input"
            try:
                link_dir.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            with self.assertRaisesRegex(ParseError, "symbolic link"):
                parse_report(link_dir / "report.csv")

    def test_output_rejects_symlinked_directory_and_existing_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            outside = Path(directory) / "outside"
            outside.mkdir()
            try:
                output.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links unavailable")
            with self.assertRaisesRegex(ParseError, "symbolic link"):
                parse_report(FIXTURE, output)

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            parse_report(FIXTURE, output)
            with self.assertRaisesRegex(ParseError, "already exists"):
                parse_report(FIXTURE, output)

    def test_non_finite_numeric_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "non-finite.csv"
            path.write_text(
                "keyword,impressions,clicks,spend,sales,orders\n"
                "term,10,1,NaN,2,1\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ParseError, "non-finite"):
                parse_report(path)


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from scripts.evaluate_kubios_screenshot_parser import evaluate_directory, exact_match
from src.kubios_screenshot.calibration import save_calibration
from src.kubios_screenshot.field_ocr import normalize_candidate, recognize_field, sanitize_candidate
from src.kubios_screenshot.models import OCRResult, ParsedField, TextBlock
from src.kubios_screenshot.quality import check_image_quality
from src.kubios_screenshot.region_extractor import extract_region, preprocessing_candidates, region_pixels
from src.kubios_screenshot.review import build_review
from src.kubios_screenshot.template_detector import detect_template
from src.kubios_screenshot.templates import get_template, list_templates, load_template_config, validate_region


class SequenceAdapter:
    engine = "synthetic_sequence"

    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def recognize(self, path):
        value = self.values[min(self.index, len(self.values) - 1)]
        self.index += 1
        block = TextBlock(str(value), 0.96, {}, [{"text": str(value), "confidence": 0.96}])
        return OCRResult(self.engine, "1", {"width": 400, "height": 200}, [block], str(value), [])


class TemplateParserTests(unittest.TestCase):
    def test_explicit_templates_exist(self):
        self.assertEqual(
            {item["template_id"] for item in list_templates()},
            {
                "resting_hrv_result_full",
                "readiness_summary",
                "measurement_details",
                "results_summary",
            },
        )

    def test_only_user_supplied_layouts_claim_real_calibration(self):
        templates = {item["template_id"]: item for item in list_templates()}
        for template_id in ("readiness_summary", "measurement_details"):
            self.assertEqual(templates[template_id]["calibration_status"], "calibrated_anonymized_real")
            self.assertTrue(templates[template_id]["auto_detection_enabled"])
            self.assertEqual(templates[template_id]["calibration_sample_count"], 1)
        self.assertEqual(templates["resting_hrv_result_full"]["calibration_status"], "calibrated_user_confirmed_standard")
        self.assertTrue(templates["resting_hrv_result_full"]["auto_detection_enabled"])
        self.assertEqual(templates["resting_hrv_result_full"]["calibration_sample_count"], 10)
        self.assertEqual(templates["results_summary"]["calibration_status"], "pending_real_calibration")
        self.assertFalse(templates["results_summary"]["auto_detection_enabled"])

    def test_full_result_template_uses_the_user_confirmed_standard_layout(self):
        template = get_template("resting_hrv_result_full")
        self.assertEqual(template["reference_layout"]["image_size"], [1284, 2778])
        self.assertEqual(template["reference_layout"]["source"], "user_confirmed_standard_screenshot")
        self.assertEqual(
            list(template["field_regions"]),
            [
                "mean_hr", "rmssd", "pns_index", "sns_index", "physiological_age",
                "mean_rr_ms", "sdnn", "poincare_sd1_ms", "poincare_sd2_ms",
                "stress_index", "respiratory_rate_bpm", "lf_power_ms2", "hf_power_ms2",
                "lf_power_nu", "hf_power_nu", "lf_hf_ratio", "measurement_quality", "mood_code",
            ],
        )

    def test_template_auto_detection_when_calibrated_config_allows_it(self):
        config = json.loads(Path("config/kubios_screenshot_templates.json").read_text(encoding="utf-8"))
        for template in config["templates"]:
            template["auto_detection_enabled"] = template["template_id"] == "readiness_summary"
        blocks = [TextBlock("Readiness Resting HRV RMSSD Heart rate", 0.99)]
        result = detect_template({"width": 1028, "height": 1248}, blocks, config)
        self.assertEqual(result.template_id, "readiness_summary")
        self.assertFalse(result.requires_manual_selection)

    def test_low_confidence_detection_requires_manual_selection(self):
        result = detect_template({"width": 1170, "height": 2532}, [TextBlock("unrelated page", 0.9)])
        self.assertTrue(result.requires_manual_selection)
        self.assertIsNone(result.template_id)

    def test_pending_real_calibration_always_requires_selection(self):
        result = detect_template({"width": 1170, "height": 2532}, [TextBlock("Kubios Results Recovery Readiness", 0.99)])
        self.assertEqual(result.template_id, "results_summary")
        self.assertTrue(result.requires_manual_selection)

    def test_normalized_roi_scales_with_resolution(self):
        region = {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}
        self.assertEqual(region_pixels((1000, 2000), region), (100, 400, 400, 600))
        self.assertEqual(region_pixels((500, 1000), region), (50, 200, 200, 300))

    def test_region_crop_works_at_multiple_resolutions(self):
        region = {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}
        self.assertEqual(extract_region(Image.new("RGB", (1000, 2000)), region).size, (300, 200))
        self.assertEqual(extract_region(Image.new("RGB", (500, 1000)), region).size, (150, 100))

    def test_invalid_normalized_region_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_region({"x": 0.9, "y": 0.2, "width": 0.3, "height": 0.1})

    def test_six_preprocessing_candidates_are_generated(self):
        candidates = preprocessing_candidates(Image.new("RGB", (100, 40), "white"))
        self.assertEqual(set(candidates), {"original", "grayscale", "high_contrast", "adaptive_binary", "scale_2x", "scale_3x"})
        self.assertEqual(candidates["scale_3x"].size, (300, 120))

    def test_rotated_screenshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rotated.png"
            Image.new("RGB", (1600, 800), "white").save(path)
            result = check_image_quality(path)
        self.assertFalse(result.acceptable)
        self.assertIn("rotation_or_orientation_wrong", result.warnings)

    def test_low_resolution_screenshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "small.png"
            Image.new("RGB", (300, 600), "white").save(path)
            result = check_image_quality(path)
        self.assertFalse(result.acceptable)
        self.assertIn("resolution_too_low", result.warnings)

    def test_clear_portrait_screenshot_passes_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portrait.png"
            Image.new("RGB", (1170, 2532), "white").save(path)
            result = check_image_quality(path)
        self.assertTrue(result.acceptable)

    def test_sanitized_portrait_crop_passes_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crop.png"
            Image.new("RGB", (1028, 1248), "white").save(path)
            result = check_image_quality(path)
        self.assertTrue(result.acceptable)

    def test_anonymized_real_fixtures_have_reviewed_sidecars(self):
        root = Path("tests/fixtures/kubios_screenshots/anonymized_real")
        images = sorted(root.glob("*.png"))
        self.assertEqual(len(images), 2)
        for image in images:
            truth = json.loads(image.with_suffix(".ground_truth.json").read_text(encoding="utf-8"))
            self.assertIn(truth["template_id"], {"readiness_summary", "measurement_details"})
            self.assertNotIn("name", truth)
            self.assertNotIn("account", truth)

    def test_numeric_whitelist_removes_labels_and_units(self):
        self.assertEqual(sanitize_candidate("RMSSD 54.2 ms", "numeric_decimal"), "54.2")
        self.assertEqual(sanitize_candidate("Mean HR: 58 bpm", "integer"), "58")

    def test_status_text_preserves_letters(self):
        self.assertEqual(sanitize_candidate("GOOD", "status_text"), "GOOD")

    def test_date_and_time_whitelists(self):
        self.assertEqual(sanitize_candidate("Date 2026/07/08", "date"), "2026/07/08")
        self.assertEqual(sanitize_candidate("Time 06:30", "time"), "06:30")

    def test_decimal_comma_is_normalized(self):
        self.assertEqual(normalize_candidate("54,5", "rmssd", "numeric_decimal"), 54.5)

    def test_fixed_unit_comes_from_template_not_ocr(self):
        definition = {"field_type": "numeric_decimal", "expected_unit": "ms"}
        parsed = recognize_field(Image.new("RGB", (160, 60), "white"), "rmssd", definition, SequenceAdapter(["54.5"] * 6))
        self.assertEqual(parsed.unit, "ms")

    def test_rmssd_multi_candidate_vote(self):
        definition = {"field_type": "numeric_decimal", "expected_unit": "ms"}
        parsed = recognize_field(Image.new("RGB", (160, 60), "white"), "rmssd", definition, SequenceAdapter(["54.5", "54.5", "54.5", "545", "54.5", "54.5"]))
        self.assertEqual(parsed.value, 54.5)
        self.assertTrue(parsed.candidates_consistent)

    def test_mean_hr_multi_candidate_vote(self):
        definition = {"field_type": "integer", "expected_unit": "bpm"}
        parsed = recognize_field(Image.new("RGB", (160, 60), "white"), "mean_hr", definition, SequenceAdapter(["58", "58", "58", "S8", "58", "58"]))
        self.assertEqual(parsed.value, 58)

    def test_readiness_multi_candidate_vote(self):
        definition = {"field_type": "integer", "expected_unit": None}
        parsed = recognize_field(Image.new("RGB", (160, 60), "white"), "readiness", definition, SequenceAdapter(["82", "82", "82", "82", "B2", "82"]))
        self.assertEqual(parsed.value, 82)

    def test_candidate_disagreement_is_exposed(self):
        definition = {"field_type": "integer", "expected_unit": "bpm"}
        parsed = recognize_field(Image.new("RGB", (160, 60), "white"), "mean_hr", definition, SequenceAdapter(["58", "59", "60", "61", "62", "63"]))
        self.assertFalse(parsed.candidates_consistent)
        self.assertEqual(len(parsed.candidates), 6)

    def test_review_preserves_candidate_consistency(self):
        field = ParsedField(58, 0.9, "region_numeric_ocr", "bpm", [{"value": 58}], True)
        from src.kubios_screenshot.models import ParseResult
        review = build_review(ParseResult({"mean_hr": field}, ["date", "rmssd"], [], "1.1.0", 0.4))
        self.assertTrue(review["fields"]["mean_hr"]["candidates_consistent"])

    def test_calibration_requires_explicit_confirmation(self):
        with self.assertRaisesRegex(ValueError, "calibration_confirmation_required"):
            save_calibration("readiness_summary", {"rmssd": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}}, False)

    def test_calibration_can_be_saved_to_explicit_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            save_calibration("readiness_summary", {"rmssd": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}}, True, path)
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(saved["calibrations"]["readiness_summary"]["confirmed_by_user"])

    def test_evaluation_exact_match_handles_numeric_types(self):
        self.assertTrue(exact_match(58.0, 58))
        self.assertFalse(exact_match(58.1, 58))

    def test_empty_real_evaluation_reports_no_claimed_accuracy(self):
        with tempfile.TemporaryDirectory() as directory:
            result = evaluate_directory(directory, SequenceAdapter(["1"]))
        self.assertEqual(result["sample_count"], 0)
        self.assertIsNone(result["template_detection_accuracy"])
        self.assertFalse(result["contains_real_measurements"])

    def test_template_parser_modules_have_no_network_imports(self):
        names = ("template_detector.py", "region_extractor.py", "field_ocr.py", "quality.py")
        source = "\n".join((Path("src/kubios_screenshot") / name).read_text(encoding="utf-8") for name in names)
        for forbidden in ("requests", "urllib", "socket", "http://", "https://"):
            self.assertNotIn(forbidden, source)

    def test_review_page_uses_one_editable_confirmation_form(self):
        source = Path("src/pages/2_Kubios_Screenshot_Import.py").read_text(encoding="utf-8")
        self.assertIn("for name in FIELD_ORDER", source)
        self.assertNotIn("kubios_accept_high_", source)
        self.assertNotIn("kubios_manual_mode_", source)
        self.assertNotIn("kubios_clear_prefill_", source)
        self.assertIn("confirm_import", source)


if __name__ == "__main__":
    unittest.main()

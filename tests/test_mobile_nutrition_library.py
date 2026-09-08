import base64
import tempfile
import unittest
from pathlib import Path

from src import db
from src.mobile_nutrition_library import (
    MobileNutritionLibraryError,
    mobile_food_nutrition_library,
    parse_mobile_food_label,
    save_mobile_food_label,
)


class MobileNutritionLibraryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.directory.name) / "recovery.db")
        connection = db.connect(self.db_path)
        connection.close()

    def tearDown(self):
        self.directory.cleanup()

    def test_parser_uses_desktop_label_basis_and_rounds_values(self):
        result = parse_mobile_food_label({
            "raw_text": "营养成分表\n每100毫升\n能量 180 kJ\n蛋白质 3.237 g\n脂肪 3.6 g"
        })
        self.assertEqual(result["basis"], "per 100 ml")
        self.assertEqual(result["nutrients"]["protein"], {"value": 3.24, "unit": "g"})

    def test_requires_values_and_a_label_basis(self):
        with self.assertRaisesRegex(MobileNutritionLibraryError, "NUTRITION_LABEL_VALUES_NOT_FOUND"):
            parse_mobile_food_label({"raw_text": "品牌名"})
        with self.assertRaisesRegex(MobileNutritionLibraryError, "NUTRITION_LABEL_BASIS_REQUIRED"):
            parse_mobile_food_label({"raw_text": "蛋白质 3.2 g"})

    def test_saves_and_lists_the_desktop_custom_food_library(self):
        result = save_mobile_food_label({
            "raw_text": "营养成分表\n每100g\n能量 100 kcal\n蛋白质 3.237 g",
            "food_name": "测试酸奶", "brand": "RHYTHMOS",
            "image_base64": base64.b64encode(b"test-image").decode(),
            "image_mime_type": "image/jpeg", "image_file_name": "label.jpg",
        }, db_path=self.db_path)

        self.assertEqual(result["food_name"], "测试酸奶")
        library = mobile_food_nutrition_library(db_path=self.db_path)
        self.assertEqual(library["items"][0]["food_name"], "测试酸奶")
        self.assertEqual(library["items"][0]["brand"], "RHYTHMOS")
        self.assertEqual(library["items"][0]["nutrients"]["protein"]["value"], 3.24)

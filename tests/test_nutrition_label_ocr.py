import unittest
import sqlite3

from src import db
from src.kubios_screenshot.models import OCRResult, TextBlock
from src.nutrition_logging import (
    calculate_food_values, food_catalog_by_name, food_display_name, get_meal_record,
    save_meal_record,
)
from src.nutrition_logging.label_ocr import (
    create_custom_food_from_ocr, list_custom_food_nutrition_library,
    parse_nutrition_label, parse_nutrition_ocr, save_custom_supplement_nutrition_record,
    save_food_ocr_profile,
)
from src.supplements import calculate_intake_ingredients, list_products


class NutritionLabelOCRTests(unittest.TestCase):
    def test_parses_chinese_per_100_ml_label(self):
        parsed = parse_nutrition_label(
            "营养成分表\n每100毫升\n能量 180 kJ\n蛋白质 3.2 g\n"
            "脂肪 3.6 g\n碳水化合物 4.8 g\n钠 62 mg"
        )
        self.assertEqual(parsed["basis"], "per 100 ml")
        self.assertEqual(parsed["nutrients"]["protein"], {"value": 3.2, "unit": "g"})
        self.assertEqual(parsed["nutrients"]["sodium"], {"value": 62.0, "unit": "mg"})

    def test_parses_english_serving_label(self):
        parsed = parse_nutrition_label(
            "Nutrition Facts\nPer serving\nCalories 120 kcal\n"
            "Total Fat 2 g\nTotal Carbohydrate 20 g\nDietary Fiber 3 g"
        )
        self.assertEqual(parsed["basis"], "per serving")
        self.assertEqual(parsed["nutrients"]["energy"]["value"], 120)
        self.assertEqual(parsed["nutrients"]["fiber"]["value"], 3)

    def test_does_not_guess_values_without_units(self):
        parsed = parse_nutrition_label("蛋白质 3\n脂肪 -2 g")
        self.assertEqual(parsed["nutrients"], {})

    def test_parses_separate_vision_blocks_from_chinese_table(self):
        parsed = parse_nutrition_label(
            "营养成分表\n项日\n每100g\n能量\n936kJ\n蛋白质\n7.2g\n"
            "脂肪\n3.5g\n-反式脂肪（酸）0g\n碳水化合物\n37.4g\n"
            "膳食纤维\n6.0g\n钠\n234mg\nNRV%\n11%\n12%\n6%\n12%\n24%\n12%"
        )
        self.assertEqual(parsed["basis"], "per 100 g")
        self.assertEqual(
            parsed["nutrients"],
            {
                "energy": {"value": 936.0, "unit": "kj"},
                "protein": {"value": 7.2, "unit": "g"},
                "fat": {"value": 3.5, "unit": "g"},
                "carbohydrate": {"value": 37.4, "unit": "g"},
                "fiber": {"value": 6.0, "unit": "g"},
                "sodium": {"value": 234.0, "unit": "mg"},
            },
        )

    def test_aligns_column_major_table_blocks_by_y_position(self):
        labels = [
            ("能量", .75), ("蛋白质", .64), ("脂肪", .53),
            ("-反式脂肪（酸）", .42), ("碳水化合物", .30),
            ("膳食纤维", .19), ("钠", .08),
        ]
        values = [
            ("936kJ", .75), ("7.2g", .64), ("3.5g", .53),
            ("0.0g", .42), ("37.4g", .30), ("6.0g", .19), ("234mg", .08),
        ]
        blocks = [
            TextBlock(text, 1.0, {"x": .1, "y": y, "width": .2, "height": .04})
            for text, y in labels
        ] + [
            TextBlock(text, 1.0, {"x": .45, "y": y, "width": .15, "height": .04})
            for text, y in values
        ]
        blocks.append(TextBlock("每100g", 1.0, {"x": .45, "y": .86, "width": .2, "height": .04}))
        result = OCRResult(
            "macos_vision", "test", {"width": 1264, "height": 906},
            blocks, "\n".join(block.text for block in blocks),
        )
        parsed = parse_nutrition_ocr(result)
        self.assertEqual(parsed["basis"], "per 100 g")
        self.assertEqual(parsed["nutrients"]["energy"]["value"], 936)
        self.assertEqual(parsed["nutrients"]["protein"]["value"], 7.2)
        self.assertEqual(parsed["nutrients"]["fat"]["value"], 3.5)
        self.assertEqual(parsed["nutrients"]["carbohydrate"]["value"], 37.4)
        self.assertEqual(parsed["nutrients"]["fiber"]["value"], 6.0)
        self.assertEqual(parsed["nutrients"]["sodium"]["value"], 234)

    def test_parses_chinese_written_units_from_three_column_label(self):
        labels = [("能量", .75), ("蛋白质", .62), ("脂肪", .49), ("碳水化合物", .36), ("钠", .23)]
        per_serving = [("485千焦", .75), ("24克", .62), ("0.7克", .49), ("3.0克", .36), ("70毫克", .23)]
        per_100g = [("1595千焦", .75), ("78.9克", .62), ("2.3克", .49), ("9.9克", .36), ("230毫克", .23)]
        blocks = [
            TextBlock(text, 1.0, {"x": .05, "y": y, "width": .2, "height": .04})
            for text, y in labels
        ] + [
            TextBlock(text, 1.0, {"x": .43, "y": y, "width": .15, "height": .04})
            for text, y in per_serving
        ] + [
            TextBlock(text, 1.0, {"x": .78, "y": y, "width": .15, "height": .04})
            for text, y in per_100g
        ] + [TextBlock("每份", 1.0, {"x": .43, "y": .9, "width": .1, "height": .04})]
        parsed = parse_nutrition_ocr(OCRResult(
            "macos_vision", "test", {"width": 1042, "height": 536}, blocks,
            "\n".join(block.text for block in blocks),
        ))
        self.assertEqual(parsed["basis"], "per serving")
        self.assertEqual(parsed["nutrients"]["energy"], {"value": 485.0, "unit": "kj"})
        self.assertEqual(parsed["nutrients"]["protein"], {"value": 24.0, "unit": "g"})
        self.assertEqual(parsed["nutrients"]["sodium"], {"value": 70.0, "unit": "mg"})

    def test_parses_repeated_chinese_and_english_units(self):
        parsed = parse_nutrition_label(
            "项目\n能量\n蛋白质\n脂肪\n碳水化合物\n膳食纤维\n钠\n每100克（g）\n"
            "1573千焦（kJ）\n12.8克（g）\n7.8克（g）\n58.3克（g）\n9.5克（g）\n0毫克（mg）"
        )
        self.assertEqual(parsed["basis"], "per 100 g")
        self.assertEqual(parsed["nutrients"]["energy"], {"value": 1573.0, "unit": "kj"})
        self.assertEqual(parsed["nutrients"]["fiber"], {"value": 9.5, "unit": "g"})
        self.assertEqual(parsed["nutrients"]["sodium"], {"value": 0.0, "unit": "mg"})

    def test_recovers_low_contrast_skewed_label_ocr_variants(self):
        # This is the raw text emitted by macOS Vision for a photographed,
        # halftone nutrition table. It includes the common ``glg`` unit noise,
        # a malformed carbohydrate glyph, and ``铗`` for sodium.
        parsed = parse_nutrition_label(
            "营养成分表\n每100克（g）\n2596千焦（kJ〕\n蛋白质\n36.7克lg）\n"
            "脂肪\n50.3克（g）\n碳水化合物\n．53克（g）\n铗\n0毫克（mg）"
        )
        self.assertEqual(
            parsed["nutrients"],
            {
                "energy": {"value": 2596.0, "unit": "kj"},
                "protein": {"value": 36.7, "unit": "g"},
                "fat": {"value": 50.3, "unit": "g"},
                "carbohydrate": {"value": 6.3, "unit": "g"},
                "sodium": {"value": 0.0, "unit": "mg"},
            },
        )

    def test_recognises_chinese_supplement_facts_instead_of_food_nutrition(self):
        result = OCRResult(
            "macos_vision", "test", {"width": 788, "height": 225}, [],
            "主要成分\n每2粒含量\n维生素D3 100μg(4000IU)\n维生素K2 70μg\n镁(甘氨酸镁复合) 200mg",
        )
        parsed = parse_nutrition_ocr(result)
        facts = parsed["supplement_facts"]
        self.assertEqual(parsed["nutrients"], {})
        self.assertEqual(facts["serving"], {"quantity": 2.0, "unit": "capsule"})
        self.assertEqual(facts["ingredients"]["vitamin_d3"]["value"], 100.0)
        self.assertEqual(facts["ingredients"]["vitamin_d3"]["unit"], "mcg")
        self.assertEqual(facts["ingredients"]["vitamin_d3"]["alternate_value"], 4000.0)
        self.assertEqual(facts["ingredients"]["vitamin_k2"]["value"], 70.0)
        self.assertEqual(facts["ingredients"]["magnesium"]["value"], 200.0)

    def test_recognises_generic_supplement_ingredient_rows(self):
        result = OCRResult(
            "macos_vision", "test", {"width": 540, "height": 780}, [],
            "叶黄素\n10mg\n玉米黄质\n2mg\n维生素A（视黄醇当量）\n400ug\n"
            "锌\n2.5mg\n越橘提取物\n50mg\n—相当于干越橘\n10g\n麦角硫因\n（SiyomicrO-ERGO）\n9mg",
        )
        ingredients = parse_nutrition_ocr(result)["supplement_facts"]["ingredients"]
        names = {item["display_name_zh"]: (item["value"], item["unit"]) for item in ingredients.values()}
        self.assertEqual(names["叶黄素"], (10.0, "mg"))
        self.assertEqual(names["玉米黄质"], (2.0, "mg"))
        self.assertEqual(names["维生素A（视黄醇当量）"], (400.0, "mcg"))
        self.assertEqual(names["锌"], (2.5, "mg"))
        self.assertEqual(names["越橘提取物"], (50.0, "mg"))
        self.assertNotIn("—相当于干越橘", names)
        self.assertEqual(names["麦角硫因 （SiyomicrO-ERGO）"], (9.0, "mg"))

    def test_recognises_inline_fish_oil_ingredients(self):
        parsed = parse_nutrition_ocr(OCRResult(
            "macos_vision", "test", {"width": 830, "height": 150}, [],
            "主要成分 1粒软胶囊含有1000毫克Omega-3，其中含有 DHA380mg，EPA460mg",
        ))
        facts = parsed["supplement_facts"]
        self.assertEqual(facts["serving"], {"quantity": 1.0, "unit": "capsule"})
        self.assertEqual(facts["ingredients"]["omega_3"]["value"], 1000.0)
        self.assertEqual(facts["ingredients"]["omega_3"]["unit"], "mg")
        self.assertEqual(facts["ingredients"]["dha"]["value"], 380.0)
        self.assertEqual(facts["ingredients"]["epa"]["value"], 460.0)

    def test_aligns_column_major_supplement_facts_by_y_position(self):
        blocks = [
            TextBlock("维生素D3", 1.0, {"x": .08, "y": .50, "width": .2, "height": .04}),
            TextBlock("维生素K2", 1.0, {"x": .08, "y": .35, "width": .2, "height": .04}),
            TextBlock("镁（甘氨酸镁复合）", .5, {"x": .08, "y": .20, "width": .3, "height": .04}),
            TextBlock("每2粒含量", 1.0, {"x": .65, "y": .70, "width": .2, "height": .04}),
            TextBlock("100ug（4000IU）", .5, {"x": .67, "y": .50, "width": .2, "height": .04}),
            TextBlock("70ug", .5, {"x": .67, "y": .35, "width": .2, "height": .04}),
            TextBlock("200mg", 1.0, {"x": .67, "y": .20, "width": .2, "height": .04}),
        ]
        parsed = parse_nutrition_ocr(OCRResult(
            "macos_vision", "test", {"width": 788, "height": 224}, blocks,
            "\n".join(block.text for block in blocks),
        ))
        ingredients = parsed["supplement_facts"]["ingredients"]
        self.assertEqual(ingredients["vitamin_d3"]["alternate_value"], 4000.0)
        self.assertEqual(ingredients["vitamin_k2"]["value"], 70.0)
        self.assertEqual(ingredients["magnesium"]["value"], 200.0)


class FoodOCRProfileTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        db.init_db(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_confirmed_ocr_profile_overrides_catalog_per_metric(self):
        oats = food_catalog_by_name(self.connection)["oats"]
        parsed = parse_nutrition_label(
            "每100g\n能量\n936kJ\n蛋白质\n7.2g\n脂肪\n3.5g\n"
            "碳水化合物\n37.4g\n膳食纤维\n6.0g\n钠\n234mg"
        )
        save_food_ocr_profile(
            self.connection, oats["id"], parsed,
            brand="测试品牌", source_file_sha256="sample",
        )
        updated = food_catalog_by_name(self.connection)["oats"]
        self.assertEqual(food_display_name(updated, "zh-CN"), "燕麦（测试品牌）")
        self.assertEqual(food_display_name(updated, "en"), "Oats（测试品牌）")
        values = calculate_food_values(updated, 50, "g")
        self.assertAlmostEqual(values["calories_kcal"], 936 / 4.184 / 2, places=3)
        self.assertEqual(values["protein_g"], 3.6)
        self.assertEqual(values["fat_g"], 1.75)
        self.assertEqual(values["carbohydrate_g"], 18.7)
        self.assertEqual(values["fiber_g"], 3.0)
        self.assertEqual(values["sodium_mg"], 117.0)

    def test_saved_meal_records_ocr_source_and_values(self):
        oats = food_catalog_by_name(self.connection)["oats"]
        parsed = parse_nutrition_label("每100g\n蛋白质\n7.2g")
        save_food_ocr_profile(self.connection, oats["id"], parsed)
        record_id = save_meal_record(
            self.connection,
            {
                "date": "2026-07-30", "meal_type": "breakfast",
                "eaten_at": "08:00", "status": "completed", "source": "manual",
            },
            [{"food_catalog_id": oats["id"], "quantity": 50, "unit": "g"}],
        )
        row = self.connection.execute(
            "SELECT protein_g,nutrition_source FROM meal_items WHERE meal_record_id=?",
            (record_id,),
        ).fetchone()
        self.assertEqual(row["protein_g"], 3.6)
        self.assertEqual(row["nutrition_source"], "label_ocr_confirmed")

    def test_confirmed_supplement_label_populates_matching_product_formula(self):
        product = next(
            item for item in list_products(self.connection)
            if item["product_name"] == "分离乳清蛋白粉"
        )
        product_id = save_custom_supplement_nutrition_record(
            self.connection,
            {
                "raw_text": "每24克 蛋白质24克",
                "supplement_facts": {
                    "serving": {"quantity": 24, "unit": "g"},
                    "ingredients": {
                        "protein": {
                            "value": 24, "unit": "g",
                            "display_name_zh": "蛋白质",
                            "display_name_en": "Protein",
                        },
                    },
                    "confidence": 1,
                },
            },
            product_id=product["id"], product_name=product["product_name"],
            brand="测试品牌", source_image_bytes=b"supplement-label-bridge",
            source_file_name="label.jpg", source_mime_type="image/jpeg",
        )
        ingredients = calculate_intake_ingredients(self.connection, product_id, 24, "g")
        self.assertEqual(product_id, product["id"])
        self.assertEqual(ingredients[0]["name"], "蛋白质")
        self.assertEqual(ingredients[0]["amount"], 24)

    def test_historical_branded_custom_name_uses_ocr_profile(self):
        oats = food_catalog_by_name(self.connection)["oats"]
        record_id = save_meal_record(
            self.connection,
            {
                "date": "2026-07-30", "meal_type": "breakfast",
                "eaten_at": "08:00", "status": "completed", "source": "manual",
            },
            [{"custom_food_name": "燕麦（中国农科院世壮）", "quantity": 50, "unit": "g"}],
        )
        parsed = parse_nutrition_label("每100g\n能量 936kJ\n蛋白质 7.2g")
        save_food_ocr_profile(
            self.connection, oats["id"], parsed,
            brand="中国农科院世壮", source_file_sha256="branded-oats",
        )
        record = get_meal_record(self.connection, record_id)
        self.assertEqual(record["items"][0]["food_catalog_id"], oats["id"])
        self.assertEqual(record["items"][0]["custom_food_name"], None)
        self.assertEqual(record["summary"]["protein_g"], 3.6)

    def test_uploaded_image_creates_reusable_custom_food_library_record(self):
        parsed = parse_nutrition_label(
            "每100g\n能量 936kJ\n蛋白质 7.2g\n脂肪 3.5g"
        )
        image_bytes = b"synthetic-label-image"
        food_id = create_custom_food_from_ocr(
            self.connection, "测试全麦食品", parsed, brand="测试品牌",
            source_image_bytes=image_bytes, source_file_name="label.jpg",
            source_mime_type="image/jpeg",
        )
        custom_food = next(
            item for item in food_catalog_by_name(self.connection).values()
            if item["id"] == food_id
        )
        values = calculate_food_values(custom_food, 50, "g")
        self.assertEqual(values["protein_g"], 3.6)
        self.assertEqual(values["fat_g"], 1.75)
        library = list_custom_food_nutrition_library(self.connection)
        self.assertEqual(len(library), 1)
        self.assertEqual(library[0]["food_name"], "测试全麦食品")
        self.assertEqual(library[0]["brand"], "测试品牌")
        self.assertEqual(library[0]["image_size_bytes"], len(image_bytes))
        stored = self.connection.execute(
            "SELECT source_image_blob FROM custom_food_nutrition_library"
        ).fetchone()[0]
        self.assertEqual(bytes(stored), image_bytes)
        second_id = create_custom_food_from_ocr(
            self.connection, "测试全麦食品", parsed, brand="测试品牌",
            source_image_bytes=b"new-label-image", source_file_name="label-2.jpg",
            source_mime_type="image/jpeg",
        )
        self.assertEqual(second_id, food_id)
        self.assertEqual(len(list_custom_food_nutrition_library(self.connection)), 2)


if __name__ == "__main__":
    unittest.main()

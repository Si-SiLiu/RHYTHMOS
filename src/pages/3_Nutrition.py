"""Simple food-level nutrition logging with structured local services."""

import json
import re
import sys
import tempfile
from uuid import uuid4
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.pages._bootstrap import ensure_project_root

ensure_project_root()

from datetime import date, datetime, time, timedelta
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from src.branding import browser_page_title, load_page_icon
from src.dashboard_data import get_day_metrics
from src.db import connect
from src.post_save_sync import refresh_local_coach_for_date
from src.input_habits import record_input_habit
from src.demo_sandbox import configure_demo_runtime
from src.exercise_format import time_to_hms
from src.i18n import format_date, format_number, get_translator
from src.i18n.ui import current_language, render_sidebar
from src.i18n.traditional import traditionalize
from src.nutrition_logging import (
    FOOD_COUNT_UNITS, FOOD_UNITS, MEAL_TYPES,
    SUPPLEMENT_UNITS, allowed_food_units,
    copy_meal_record,
    create_meal_record, favorite_foods, find_meal_id, find_previous_meal_id,
    find_yesterday_meal_id, food_catalog_by_id, food_unit_label_key,
    food_display_name, ensure_manual_food_option, get_meal_record,
    list_food_catalog, list_meal_records,
    meal_time_warning, predict_meal_time, recent_foods, save_meal_record,
    summarize_supplements,
    unit_label_key,
)
from src.nutrition_logging.nutrition_baseline import calculate_personal_nutrition_baseline
from src.nutrition_logging.label_ocr import (
    create_custom_food_from_ocr, list_custom_food_nutrition_library,
    list_custom_supplement_nutrition_library, parse_nutrition_ocr,
    save_custom_supplement_nutrition_record, save_food_ocr_profile,
)
from src.kubios_screenshot.ocr_adapter import LocalOCRError, VisionOCRAdapter
from src.nutrition_logging.feedback import (
    METRICS, NutritionFeedbackService, recommended_nutrition_targets,
    summarize_draft_food_items,
)
from src.personal_profile import get_personal_goals, latest_body_measurement
from src.supplements import (
    calculate_intake_ingredients, favorite_products, list_products,
    recent_intake_preferences, recent_products,
)
from src.ui_tables import centered_dataframe
from src.ui_controls import render_manual_input_styles
from src.ui_scroll import render_interaction_focus


# Bump this whenever label parsing changes so a Streamlit session cannot reuse
# an earlier failed result for the exact same image hash.
NUTRITION_OCR_PARSER_CACHE_VERSION = "2026-08-08-low-contrast-table-ocr-v4"


configure_demo_runtime(st)
PAGE_LANGUAGE = current_language(st.session_state)
st.set_page_config(
    page_title=browser_page_title(get_translator(PAGE_LANGUAGE)("domain.nutrition.title")),
    page_icon=load_page_icon(), layout="wide",
)
LANGUAGE, TR = render_sidebar(st, "nutrition")
render_manual_input_styles(st)

# A historical record selection is only useful during the current Nutrition
# page visit. Returning from another page should restore the compact history
# directories rather than reopening the previously viewed evidence.
if st.session_state.get("drc_previous_page") != "nutrition":
    for _history_state_key in (
        "nutrition_history_selected",
        "nutrition_history_details_visible",
        "nutrition_history_sections_open",
        "nutrition_history_focus_nonce",
        "nutrition_history_last_scrolled_nonce",
        "nutrition_weekly_recipe_edit_slot",
        "nutrition_weekly_recipe_editor_focus_nonce",
        "nutrition_weekly_recipe_editor_last_scrolled_nonce",
    ):
        st.session_state.pop(_history_state_key, None)


def _nutrition_number(value, suffix=""):
    return TR("common.no_data") if value in (None, "") else f"{format_number(value, LANGUAGE)}{suffix}"


def _ui(zh, en):
    return traditionalize(zh) if LANGUAGE == "zh-TW" else zh if LANGUAGE != "en" else en


def _render_html(markup, container=None):
    target = st if container is None else container
    target.markdown(markup, unsafe_allow_html=True)


def _nutrition_label_scanner(connection, editor_key, *, scan_context="food", supplement_record_key=None):
    """Render a local-only label scanner beneath the beverage add control."""
    _, upload_button_label = {
        "food": (_ui("扫描食物/饮品营养成分表", "Scan Food / Beverage Nutrition Label"), _ui("扫描新的食物/饮品营养成分表", "Scan New Food / Beverage Nutrition Label")),
        "supplement": (_ui("扫描补剂成分表", "Scan Supplement Facts Label"), _ui("扫描新的补剂成分表", "Scan New Supplement Facts Label")),
        "medication": (_ui("扫描药物成分表", "Scan Medication Facts Label"), _ui("扫描新的药物成分表", "Scan New Medication Facts Label")),
    }.get(scan_context, ("Scan Label", "Scan New Label"))
    # Some app-shell/browser style combinations collapse Streamlit's secondary
    # upload button. Keep the native file-picker trigger explicitly visible;
    # the surrounding drop area continues to support drag and drop.
    upload_button_css = """
        <style>
        [data-testid="stFileUploader"],
        [data-testid="stFileUploader"] > div,
        [data-testid="stFileUploader"] section {
            width: 100% !important;
        }
        [data-testid="stFileUploaderDropzone"] button,
        [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
            display: inline-flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            width: 100% !important;
            min-width: 0 !important;
            justify-content: center !important;
        }
        [data-testid="stFileUploaderDropzone"] {
            width: 100% !important;
            min-height: auto !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
        }
        [data-testid="stFileUploaderDropzoneInstructions"] {
            display: none !important;
        }
        [data-testid="stFileUploaderDropzone"] button p {
            font-size: 0 !important;
        }
        [data-testid="stFileUploaderDropzone"] button p::after {
            content: "__UPLOAD_BUTTON_LABEL__";
            font-size: 1rem;
        }
        </style>
        """.replace("__UPLOAD_BUTTON_LABEL__", upload_button_label)
    st.markdown(
        upload_button_css,
        unsafe_allow_html=True,
    )
    upload_revision_key = f"nutrition_label_upload_revision_{editor_key}"
    upload_revision = int(st.session_state.get(upload_revision_key, 0))
    uploaded = st.file_uploader(
        _ui("从本地选择照片", "Choose Local Photo"),
        type=("png", "jpg", "jpeg", "heic", "tif", "tiff"),
        key=f"nutrition_label_upload_{editor_key}_{upload_revision}",
        help=_ui(
            "点击上传区域右侧按钮，从电脑或手机的本地照片中选择。",
            "Use the button on the right side of the upload area to choose a local photo.",
        ),
        label_visibility="collapsed",
    )
    if uploaded is None:
        return

    adapter = VisionOCRAdapter()
    if not adapter.readiness()["ready"]:
        st.warning(_ui(
            "本机 OCR 当前不可用，请确认正在 macOS 应用中运行且 OCR 辅助程序已安装。",
            "Local OCR is unavailable. Run the macOS app and ensure its OCR helper is installed.",
        ))
        return
    digest_key = f"nutrition_label_digest_{editor_key}"
    result_key = f"nutrition_label_result_{editor_key}"
    image_bytes = uploaded.getvalue()
    import hashlib
    digest = hashlib.sha256(image_bytes).hexdigest()
    cache_signature = f"{NUTRITION_OCR_PARSER_CACHE_VERSION}:{digest}"
    if st.button(_ui("开始识别", "Scan Label"), key=f"nutrition_label_scan_{editor_key}"):
        suffix = Path(uploaded.name).suffix.lower() or ".png"
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix) as temporary:
                temporary.write(image_bytes)
                temporary.flush()
                ocr = adapter.recognize(temporary.name)
            parsed = parse_nutrition_ocr(ocr)
            st.session_state[digest_key] = cache_signature
            st.session_state[result_key] = parsed
        except LocalOCRError:
            st.error(_ui(
                "未能识别这张图片。请保持标签平整、光线均匀并重新拍摄。",
                "The image could not be read. Retake it with the label flat and evenly lit.",
            ))

    parsed = st.session_state.get(result_key) if st.session_state.get(digest_key) == cache_signature else None
    if not parsed:
        return
    nutrients = parsed["nutrients"]
    if not nutrients:
        supplement_facts = parsed.get("supplement_facts") or {}
        ingredients = supplement_facts.get("ingredients") or {}
        if ingredients:
            serving = supplement_facts.get("serving") or {}
            serving_text = ""
            if serving:
                unit_label = _ui("粒", "capsules") if serving.get("unit") == "capsule" else _ui("片", "tablets")
                serving_text = f"{_ui('每份：', 'Per serving: ')}{serving['quantity']:g} {unit_label}"
            st.success(_ui(
                "已识别为补剂成分表，不会误当作食品营养表。",
                "Recognised as a supplement facts label; it was not treated as food nutrition.",
            ))
            if serving_text:
                st.caption(serving_text)
            st.dataframe([
                {
                    _ui("主要成分", "Active ingredient"): item[_ui("display_name_zh", "display_name_en")],
                    _ui("每份含量", "Amount per serving"): (
                        f"{item['value']:g} {item['unit']}"
                        + (f" ({item['alternate_value']:g} {item['alternate_unit']})" if item.get("alternate_value") is not None else "")
                    ),
                }
                for item in ingredients.values()
            ], hide_index=True, use_container_width=True)
            _supplement_facts_calibration(parsed, result_key, digest, editor_key)
            # The food-label scanner is also available from the supplement
            # editor. In that context it can carry a reviewed match straight
            # into the current intake row, without silently changing a saved
            # product profile.
            binding_kind = "medication" if scan_context == "medication" else "supplement"
            products = [
                item for item in list_products(connection)
                if item.get("product_kind") == binding_kind
            ]
            product_by_label = {_product_label(item): item for item in products}
            target_record_key = supplement_record_key or editor_key
            binding_title = (
                _ui("绑定到具体药物", "Link to a Specific Medication")
                if binding_kind == "medication" else
                _ui("绑定到具体补剂", "Link to a Specific Supplement")
            )
            product_prompt = (
                _ui("选择对应药物", "Select matching medication")
                if binding_kind == "medication" else
                _ui("选择对应补剂", "Select matching supplement")
            )
            st.markdown(f"##### {binding_title}")
            st.caption(_ui(
                "确认后会将标签关联到该类型；可选择已有类型或输入新的自定义类型。",
                "Confirm to link this label to the selected type; choose an existing type or enter a new custom one.",
            ))
            bind_mode = st.radio(
                _ui("保存方式", "Save mode"), ("existing", "custom"), horizontal=True,
                format_func=lambda value: (
                    _ui("绑定已有类型", "Link Existing Type") if value == "existing"
                    else _ui("新建自定义类型", "Create Custom Type")
                ),
                key=f"supplement_ocr_bind_mode_{editor_key}",
            )
            selected_label = ""
            custom_product_name = ""
            if bind_mode == "existing":
                selected_label = st.selectbox(
                    product_prompt, [""] + list(product_by_label),
                    key=f"supplement_ocr_product_match_{editor_key}", placeholder=product_prompt,
                )
            else:
                custom_product_name = st.text_input(
                    _ui("自定义药物类型", "Custom Medication Type")
                    if binding_kind == "medication" else _ui("自定义补剂类型", "Custom Supplement Type"),
                    key=f"supplement_ocr_custom_product_{editor_key}",
                    placeholder=_ui("请输入类型名称", "Enter a type name"),
                )
            brand = st.text_input(
                _ui("品牌", "Brand"),
                key=f"supplement_ocr_brand_{editor_key}",
                placeholder=_ui("可选", "Optional"),
            )
            if st.button(
                _ui("确认匹配并保存", "Confirm Match and Save"),
                key=f"supplement_ocr_apply_{editor_key}", type="primary",
                disabled=not (selected_label if bind_mode == "existing" else custom_product_name.strip()),
            ):
                product = product_by_label.get(selected_label)
                resolved_product_name = product["product_name"] if product else custom_product_name.strip()
                save_custom_supplement_nutrition_record(
                    connection, parsed, product_id=product["id"] if product else None,
                    product_name=resolved_product_name,
                    brand=brand, source_image_bytes=image_bytes, source_file_name=uploaded.name,
                    source_mime_type=uploaded.type, product_kind=binding_kind,
                )
                st.success(_ui(
                    "已保存到对应类型与自定义成分数据库；未加入当前餐次。",
                    "Saved to the matching type and custom ingredient library; not added to the current meal.",
                ))
            st.caption(_ui(
                "请确认绑定后再保存本餐；识别结果不会被静默写入记录。",
                "Confirm the binding before saving this meal; recognised values are never silently added.",
            ))
            with st.expander(_ui("查看 OCR 原文", "View OCR text")):
                st.code(parsed["raw_text"], language=None)
            return
        st.warning(_ui(
            "已读取图片，但没有找到可识别的营养项目。请换一张更清晰、完整的标签图片。",
            "The image was read, but no nutrition values were found. Try a clearer, complete label.",
        ))
        return
    labels = {
        "energy": _ui("能量", "Energy"), "protein": _ui("蛋白质", "Protein"),
        "fat": _ui("脂肪", "Fat"), "carbohydrate": _ui("碳水化合物", "Carbohydrate"),
        "sugar": _ui("糖", "Sugar"), "fiber": _ui("膳食纤维", "Dietary fibre"),
        "sodium": _ui("钠", "Sodium"),
    }
    rows = [
        {
            _ui("营养项目", "Nutrient"): labels[key],
            _ui("含量", "Amount"): f"{value['value']:g} {value['unit']}",
        }
        for key, value in nutrients.items()
    ]
    basis = parsed.get("basis")
    if basis:
        st.caption((_ui("标示基准：", "Label basis: ")) + basis)
    st.dataframe(rows, hide_index=True, use_container_width=True)
    _nutrition_label_calibration(parsed, result_key, digest, editor_key)
    if scan_context in {"supplement", "medication"}:
        _render_contextual_product_binding(
            connection, parsed, image_bytes, uploaded, editor_key,
            scan_context, supplement_record_key,
        )
        return
    st.markdown(f"##### {_ui('绑定到具体食物', 'Link to a Specific Food')}")
    st.caption(_ui(
        "确认后，该食物将优先使用这份标签计算营养；标签缺失的项目仍使用食物库数据。",
        "Once confirmed, this label takes priority for that food. Missing fields still fall back to the catalog.",
    ))
    bind_mode = st.radio(
        _ui("保存方式", "Save mode"),
        ("existing", "custom"),
        format_func=lambda value: (
            _ui("绑定已有食物", "Link Existing Food")
            if value == "existing"
            else _ui("新建自定义食物", "Create Custom Food")
        ),
        horizontal=True,
        key=f"nutrition_label_bind_mode_{editor_key}",
    )
    catalog_items = list_food_catalog(connection)
    catalog_by_name = {_display_food(item): item for item in catalog_items}
    selected_name = ""
    custom_food_name = ""
    if bind_mode == "existing":
        selected_name = st.selectbox(
            _ui("选择对应食物", "Select matching food"),
            [""] + list(catalog_by_name),
            key=f"nutrition_label_food_{editor_key}",
            placeholder=_ui("请选择标签对应的食物", "Choose the food shown on the label"),
        )
    else:
        custom_food_name = st.text_input(
            _ui("自定义食物名称", "Custom Food Name"),
            key=f"nutrition_label_custom_food_{editor_key}",
            placeholder=_ui("例如：某品牌全麦面包", "For example: Brand Wholegrain Bread"),
        )
    brand = st.text_input(
        _ui("品牌（可选）", "Brand (optional)"),
        key=f"nutrition_label_brand_{editor_key}",
    )
    basis_ready = parsed.get("basis") in {"per 100 g", "per 100 ml", "per serving"}
    if not basis_ready:
        st.warning(_ui(
            "没有识别到“每100克 / 每100毫升 / 每份”，请重新拍摄包含表头的完整标签。",
            "No per-100-g, per-100-ml, or per-serving basis was found. Retake the complete label including its header.",
        ))
    if st.button(
        _ui("确认绑定并设为优先数据", "Confirm and Use as Priority Data"),
        key=f"nutrition_label_bind_{editor_key}",
        type="primary",
        disabled=not (selected_name if bind_mode == "existing" else custom_food_name.strip()) or not basis_ready,
    ):
        if bind_mode == "existing":
            saved_food_name = selected_name
            save_food_ocr_profile(
                connection, catalog_by_name[selected_name]["id"], parsed,
                brand=brand, source_file_sha256=digest,
                source_image_bytes=image_bytes, source_file_name=uploaded.name,
                source_mime_type=uploaded.type,
            )
        else:
            saved_food_name = custom_food_name.strip()
            create_custom_food_from_ocr(
                connection, saved_food_name, parsed, brand=brand,
                source_image_bytes=image_bytes, source_file_name=uploaded.name,
                source_mime_type=uploaded.type,
            )
        st.success(_ui(
            f"已保存“{saved_food_name}”及原始图片，后续营养计算将优先使用此标签。",
            f"Saved “{saved_food_name}” and its source image. Future calculations will prioritise this label.",
        ))
        st.session_state[upload_revision_key] = upload_revision + 1
        st.session_state.pop(digest_key, None)
        st.session_state.pop(result_key, None)
        st.session_state[f"nutrition_label_saved_flash_{editor_key}"] = saved_food_name
        st.rerun()
    with st.expander(_ui("查看 OCR 原文", "View OCR text")):
        st.code(parsed["raw_text"], language=None)


def _render_contextual_product_binding(
    connection, parsed, image_bytes, uploaded, editor_key, product_kind, record_key,
):
    """Bind any scanned label to the active supplement or medication domain."""
    products = [item for item in list_products(connection) if item.get("product_kind") == product_kind]
    product_by_label = {_product_label(item): item for item in products}
    binding_title = (
        _ui("绑定到具体药物", "Link to a Specific Medication")
        if product_kind == "medication" else _ui("绑定到具体补剂", "Link to a Specific Supplement")
    )
    product_prompt = (
        _ui("选择对应药物", "Select matching medication")
        if product_kind == "medication" else _ui("选择对应补剂", "Select matching supplement")
    )
    st.markdown(f"##### {binding_title}")
    st.caption(_ui(
        "确认后会将标签关联到该类型；可选择已有类型或输入新的自定义类型。",
        "Confirm to link this label to the selected type; choose an existing type or enter a new custom one.",
    ))
    bind_mode = st.radio(
        _ui("保存方式", "Save mode"), ("existing", "custom"), horizontal=True,
        format_func=lambda value: _ui("绑定已有类型", "Link Existing Type") if value == "existing" else _ui("新建自定义类型", "Create Custom Type"),
        key=f"contextual_ocr_bind_mode_{editor_key}",
    )
    selected_label = ""
    custom_product_name = ""
    if bind_mode == "existing":
        selected_label = st.selectbox(product_prompt, [""] + list(product_by_label), key=f"contextual_ocr_product_{editor_key}", placeholder=product_prompt)
    else:
        custom_product_name = st.text_input(
            _ui("自定义药物类型", "Custom Medication Type") if product_kind == "medication" else _ui("自定义补剂类型", "Custom Supplement Type"),
            key=f"contextual_ocr_custom_{editor_key}", placeholder=_ui("请输入类型名称", "Enter a type name"),
        )
    brand = st.text_input(_ui("品牌", "Brand"), key=f"contextual_ocr_brand_{editor_key}", placeholder=_ui("可选", "Optional"))
    if st.button(
        _ui("确认匹配并保存", "Confirm Match and Save"),
        key=f"contextual_ocr_apply_{editor_key}", type="primary",
        disabled=not (selected_label if bind_mode == "existing" else custom_product_name.strip()),
    ):
        product = product_by_label.get(selected_label)
        product_name = product["product_name"] if product else custom_product_name.strip()
        save_custom_supplement_nutrition_record(
            connection, parsed, product_id=product["id"] if product else None,
            product_name=product_name, brand=brand, source_image_bytes=image_bytes,
            source_file_name=uploaded.name, source_mime_type=uploaded.type,
            product_kind=product_kind,
        )
        st.success(_ui(
            "已保存到对应类型与自定义成分数据库；未加入当前餐次。",
            "Saved to the matching type and custom ingredient library; not added to the current meal.",
        ))


def _nutrition_label_calibration(parsed, result_key, digest, editor_key):
    nutrient_labels = {
        "energy": _ui("能量", "Energy"),
        "protein": _ui("蛋白质", "Protein"),
        "fat": _ui("脂肪", "Fat"),
        "carbohydrate": _ui("碳水化合物", "Carbohydrate"),
        "sugar": _ui("糖", "Sugar"),
        "fiber": _ui("膳食纤维", "Dietary fibre"),
        "sodium": _ui("钠", "Sodium"),
    }
    unit_options = {
        "energy": ("kJ", "kcal"),
        "sodium": ("mg", "g"),
        "protein": ("g",), "fat": ("g",), "carbohydrate": ("g",),
        "sugar": ("g",), "fiber": ("g",),
    }
    basis_options = ("per 100 g", "per 100 ml", "per serving")
    with st.expander(_ui("手动校准识别结果", "Manually Calibrate Results")):
        st.caption(_ui(
            "可修改错误数值或补填漏识别项目。应用后，绑定与营养计算均使用校准结果。",
            "Correct values or fill missing fields. Binding and calculations will use the calibrated result.",
        ))
        with st.form(f"nutrition_label_calibration_{editor_key}_{digest}"):
            current_basis = parsed.get("basis")
            basis = st.selectbox(
                _ui("标示基准", "Label Basis"),
                basis_options,
                index=basis_options.index(current_basis) if current_basis in basis_options else 0,
            )
            calibrated_fields = {}
            for nutrient, label in nutrient_labels.items():
                current = (parsed.get("nutrients") or {}).get(nutrient) or {}
                columns = st.columns((1.3, 1.0, .7))
                columns[0].markdown(f"**{label}**")
                value = columns[1].number_input(
                    _ui(f"{label}数值", f"{label} value"),
                    min_value=0.0,
                    value=(
                        float(current["value"])
                        if current.get("value") is not None else None
                    ),
                    step=0.1,
                    key=f"calibration_value_{editor_key}_{digest}_{nutrient}",
                    label_visibility="collapsed",
                    placeholder=_ui("未识别", "Not found"),
                )
                options = unit_options[nutrient]
                current_unit = str(current.get("unit") or options[0]).lower()
                unit_lookup = {option.lower(): option for option in options}
                unit = columns[2].selectbox(
                    _ui(f"{label}单位", f"{label} unit"),
                    options,
                    index=options.index(unit_lookup.get(current_unit, options[0])),
                    key=f"calibration_unit_{editor_key}_{digest}_{nutrient}",
                    label_visibility="collapsed",
                )
                if value is not None:
                    calibrated_fields[nutrient] = {
                        "value": float(value), "unit": unit.lower(),
                    }
            submitted = st.form_submit_button(
                _ui("应用校准", "Apply Calibration"),
                type="primary",
                use_container_width=True,
            )
        if submitted:
            calibrated = {
                **parsed,
                "basis": basis,
                "nutrients": calibrated_fields,
                "manually_calibrated": True,
            }
            st.session_state[result_key] = calibrated
            st.rerun()


def _supplement_facts_calibration(parsed, result_key, digest, editor_key):
    """Allow corrections before a scanned supplement is matched to a product."""
    facts = parsed.get("supplement_facts") or {}
    ingredients = facts.get("ingredients") or {}
    with st.expander(_ui("手动校正 OCR 成分与剂量", "Manually Correct OCR Ingredients and Amounts")):
        st.caption(_ui(
            "可更正成分名称、数值和单位；应用后，下方匹配前会显示校正后的结果。",
            "Correct ingredient names, amounts, and units before matching below.",
        ))
        with st.form(f"supplement_facts_calibration_{editor_key}_{digest}"):
            corrected = {}
            for key, item in ingredients.items():
                columns = st.columns((1.5, 1, .7))
                name = columns[0].text_input(
                    _ui("成分", "Ingredient"),
                    value=item.get(_ui("display_name_zh", "display_name_en"), key),
                    key=f"supplement_calibration_name_{editor_key}_{digest}_{key}",
                    label_visibility="collapsed",
                )
                value = columns[1].number_input(
                    _ui("含量", "Amount"), min_value=0.0, value=float(item["value"]), step=.1,
                    key=f"supplement_calibration_value_{editor_key}_{digest}_{key}",
                    label_visibility="collapsed",
                )
                unit_options = ("g", "mg", "mcg", "ml", "iu")
                unit = columns[2].selectbox(
                    _ui("单位", "Unit"), unit_options,
                    index=unit_options.index(item["unit"]) if item["unit"] in unit_options else 0,
                    key=f"supplement_calibration_unit_{editor_key}_{digest}_{key}",
                    label_visibility="collapsed",
                )
                corrected[key] = {
                    **item, "value": float(value), "unit": unit,
                    "display_name_zh": name if LANGUAGE != "en" else item.get("display_name_zh"),
                    "display_name_en": name if LANGUAGE == "en" else item.get("display_name_en"),
                }
            submitted = st.form_submit_button(_ui("应用校正", "Apply Corrections"), type="primary")
        if submitted:
            st.session_state[result_key] = {
                **parsed,
                "supplement_facts": {**facts, "ingredients": corrected, "manually_calibrated": True},
            }
            st.rerun()


def _nutrition_library_detail_rows(record):
    try:
        nutrient_values = json.loads(record["nutrients_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        nutrient_values = {}
    nutrient_labels = {
        "energy": _ui("能量", "Energy"),
        "protein": _ui("蛋白质", "Protein"),
        "fat": _ui("脂肪", "Fat"),
        "carbohydrate": _ui("碳水化合物", "Carbohydrate"),
        "sugar": _ui("糖", "Sugar"),
        "fiber": _ui("膳食纤维", "Dietary fibre"),
        "sodium": _ui("钠", "Sodium"),
    }
    return [
        {
            _ui("营养项目", "Nutrient"): label,
            _ui("标示含量", "Label Amount"): (
                f"{float(value['value']):g} {value['unit']}"
                if (value := nutrient_values.get(nutrient))
                and value.get("value") is not None else "—"
            ),
            _ui("数据状态", "Data Status"): (
                _ui("OCR 已识别", "Recognised by OCR")
                if value and value.get("value") is not None
                else _ui("标签未识别", "Not found on label")
            ),
        }
        for nutrient, label in nutrient_labels.items()
    ]


@st.dialog(_ui("营养详情", "Nutrition Details"))
def _show_nutrition_library_dialog(record):
    st.subheader(record["food_name"])
    if record.get("brand"):
        st.caption(_ui("品牌：", "Brand: ") + str(record["brand"]))
    st.caption(
        _ui("标签标示基准：", "Label basis: ")
        + f"{float(record['basis_quantity']):g} {record['basis_unit']}"
    )
    st.dataframe(
        _nutrition_library_detail_rows(record),
        hide_index=True,
        use_container_width=True,
    )
    st.caption(
        _ui("OCR 置信度：", "OCR confidence: ")
        + f"{float(record.get('ocr_confidence') or 0):.0%}"
    )
    st.caption(_ui(
        "“标签未识别”的项目在实际营养计算中会回退使用食物目录数据，不会按 0 计算。",
        "Fields not found on the label fall back to catalog data during calculation; they are not treated as zero.",
    ))


@st.dialog(_ui("补剂营养详情", "Supplement Nutrition Details"))
def _show_supplement_nutrition_library_dialog(record):
    st.subheader(record["product_name"])
    if record.get("brand"):
        st.caption(_ui("品牌：", "Brand: ") + str(record["brand"]))
    if record.get("serving_quantity"):
        st.caption(
            _ui("标签标示基准：", "Label basis: ")
            + f"{float(record['serving_quantity']):g} {record.get('serving_unit') or ''}"
        )
    try:
        ingredients = json.loads(record.get("ingredients_json") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        ingredients = {}
    st.dataframe([
        {
            _ui("主要成分", "Active ingredient"): item.get(_ui("display_name_zh", "display_name_en"), key),
            _ui("标示含量", "Label amount"): (
                f"{float(item.get('value')):g} {item.get('unit') or ''}"
                + (f" ({float(item['alternate_value']):g} {item['alternate_unit']})" if item.get("alternate_value") is not None else "")
            ),
        }
        for key, item in ingredients.items()
    ], hide_index=True, use_container_width=True)
    st.caption(
        _ui("OCR 置信度：", "OCR confidence: ")
        + f"{float(record.get('ocr_confidence') or 0):.0%}"
    )


def _custom_nutrition_library_label(connection, library_kind):
    if library_kind == "food":
        count = len(list_custom_food_nutrition_library(connection))
        return _ui(
            f"食物/饮品成分数据库（{count}）",
            f"Food / Drink Ingredient Library ({count})",
        )
    count = sum(
        item.get("product_kind") == library_kind
        for item in list_custom_supplement_nutrition_library(connection)
    )
    return (
        _ui(f"补剂成分数据库（{count}）", f"Supplement Ingredient Library ({count})")
        if library_kind == "supplement" else
        _ui(f"药物成分数据库（{count}）", f"Medication Ingredient Library ({count})")
    )


def _render_custom_food_nutrition_records(records):
    if not records:
        st.caption(_ui("暂无食物/饮品营养记录。", "No food or drink nutrition records yet."))
        return
    headers = (
        _ui("食物/饮品", "Food / Drink"), _ui("品牌", "Brand"),
        _ui("标示基准", "Basis"), _ui("OCR置信度", "OCR confidence"),
        _ui("保存时间", "Saved at"), _ui("操作", "Action"),
    )
    widths = (1.15, 1.15, .85, .95, 1.4, 1.05)
    for column, header in zip(st.columns(widths), headers):
        column.markdown(f"**{header}**")
    for row in records:
        columns = st.columns(widths)
        columns[0].write(row["food_name"])
        columns[1].write(row.get("brand") or "—")
        columns[2].write(f"{row['basis_quantity']:g} {row['basis_unit']}")
        columns[3].write(f"{float(row.get('ocr_confidence') or 0):.0%}")
        columns[4].write(row["created_at"])
        if columns[5].button(
            _ui("查看营养详情", "View Details"),
            key=f"custom_food_nutrition_detail_{row['id']}",
            use_container_width=True,
        ):
            _show_nutrition_library_dialog(row)


def _render_custom_product_nutrition_records(records, product_kind):
    if not records:
        st.caption(
            _ui("暂无补剂营养记录。", "No supplement nutrition records yet.")
            if product_kind == "supplement" else
            _ui("暂无药物营养记录。", "No medication nutrition records yet.")
        )
        return
    headers = (
        _ui("补剂", "Supplement") if product_kind == "supplement" else _ui("药物", "Medication"),
        _ui("品牌", "Brand"), _ui("每份", "Per serving"),
        _ui("OCR置信度", "OCR confidence"), _ui("保存时间", "Saved at"), _ui("操作", "Action"),
    )
    widths = (1.15, 1.15, .85, .95, 1.4, 1.05)
    for column, header in zip(st.columns(widths), headers):
        column.markdown(f"**{header}**")
    for row in records:
        columns = st.columns(widths)
        columns[0].write(row["product_name"])
        columns[1].write(row.get("brand") or "—")
        columns[2].write(
            f"{float(row['serving_quantity']):g} {row['serving_unit']}"
            if row.get("serving_quantity") else "—"
        )
        columns[3].write(f"{float(row.get('ocr_confidence') or 0):.0%}")
        columns[4].write(row["created_at"])
        if columns[5].button(
            _ui("查看营养详情", "View Details"),
            key=f"custom_{product_kind}_nutrition_detail_{row['id']}",
            use_container_width=True,
        ):
            _show_supplement_nutrition_library_dialog(row)


@st.dialog(_ui("自定义成分数据库", "Custom Ingredient Library"), width="large")
def _show_custom_nutrition_library_dialog(connection, library_kind):
    if library_kind == "food":
        _render_custom_food_nutrition_records(
            list_custom_food_nutrition_library(connection),
        )
        return
    _render_custom_product_nutrition_records(
        [
            item for item in list_custom_supplement_nutrition_library(connection)
            if item.get("product_kind") == library_kind
        ],
        library_kind,
    )


FEEDBACK_METRIC_LABELS = {
    "calories_kcal": ("热量", "Calories", "kcal"),
    "protein_g": ("蛋白质", "Protein", "g"),
    "carbohydrate_g": ("碳水化合物", "Carbohydrate", "g"),
    "fat_g": ("脂肪", "Fat", "g"),
    "fiber_g": ("膳食纤维", "Fibre", "g"),
    "water_ml": ("水分", "Water", "ml"),
}


def _feedback_metric_label(metric):
    zh, en, _ = FEEDBACK_METRIC_LABELS[metric]
    return _ui(zh, en)


def _feedback_value(metric, value):
    if value is None:
        return _ui("数据不足", "Insufficient data")
    if metric == "calories_kcal":
        return f"{round(float(value))} kcal"
    if metric == "water_ml":
        amount = float(value)
        return f"{amount / 1000:.1f} L" if amount >= 1000 else f"{amount:.0f} mL"
    return f"{float(value):.1f} g"


def _recommendation_difference(metric, current, target):
    """Make the recorded-versus-recommended gap explicit on every card."""
    if current is None:
        return _ui("目标差值：待补充有效记录", "Difference: awaiting recognised records")
    if not target or target[0] is None:
        return _ui("目标差值：暂无法生成", "Difference: recommendation unavailable")
    lower, upper = target
    if current < lower:
        return _ui(
            f"目标差值：还差 {_feedback_value(metric, lower - current)}",
            f"Difference: {_feedback_value(metric, lower - current)} below the recommendation",
        )
    if upper is not None and current > upper:
        return _ui(
            f"目标差值：超出 {_feedback_value(metric, current - upper)}",
            f"Difference: {_feedback_value(metric, current - upper)} above the recommendation",
        )
    return _ui(
        f"目标差值：高于下限 {_feedback_value(metric, current - lower)}",
        f"Difference: {_feedback_value(metric, current - lower)} above the lower recommendation",
    )


def _meal_feedback_status_tags(meal_type, summary):
    tags = [("neutral", _meal_name(meal_type))]
    if summary.get("unidentified_food_count"):
        names = "、".join(summary.get("unidentified_food_names") or [])
        tags.extend([
            ("warning", _ui("部分数据", "Partial data")),
            ("warning", _ui(
                f"未识别食物：{names or '未命名食物'}",
                f"Unrecognised food: {names or 'unnamed food'}",
            )),
        ])
    elif summary.get("identified_food_count"):
        tags.append(("success", _ui("数据完整", "Data complete")))
    else:
        tags.append(("warning", _ui("数据不足", "Insufficient data")))
    return "".join(
        f'<span class="drc-feedback-status {style}">{escape(str(label))}</span>'
        for style, label in tags
    )


def _render_meal_feedback(advice, meal_type, *, section_number=2):
    header_html = (
        '<div class="drc-feedback-heading">'
        f'<div class="drc-feedback-heading-title">{escape(_ui("营养建议", "Nutrition Advice"))}</div>'
        f'<div class="drc-feedback-statuses"><span class="drc-feedback-status neutral">{escape(_meal_name(meal_type))}</span></div>'
        '</div>'
    )
    advice_html = "".join(
        f'<li><span class="drc-feedback-dot">•</span>{escape(str(situation))}</li>'
        for situation in advice
    ) or f'<li><span class="drc-feedback-dot">•</span>{escape(_ui("继续记录饮食和训练后，建议会更加个性化。", "Keep logging food and training for more personalised advice."))}</li>'
    detail_html = (
        '<section class="drc-feedback-card drc-feedback-advice-card">'
        f'<ul>{advice_html}</ul>'
        '</section>'
    )
    # Keep the title and its advice in one Markdown block so Streamlit does
    # not insert a separate component gap between them.
    _render_html(header_html + detail_html)


def _today_nutrition_status(metric, detail, summary):
    """Return one concise display status without changing nutrition logic."""
    current = detail.get("current")
    if current is not None:
        try:
            if float(current) < 0:
                return "error", _ui("数据异常", "Data anomaly"), _ui("当前值不能为负数。", "The current value cannot be negative.")
        except (TypeError, ValueError):
            return "error", _ui("数据异常", "Data anomaly"), _ui("当前值无法解析。", "The current value cannot be parsed.")
    if current is None:
        return "muted", _ui("数据不足", "Insufficient data"), _ui("当前没有可识别的营养数据。", "No recognised nutrition data is available.")
    if summary.get("unidentified_food_count"):
        names = "、".join(summary.get("unidentified_food_names") or [])
        return "attention", _ui("部分数据", "Partial data"), _ui(
            f"当前数值已同步饮食记录中的可识别项目；未识别食物：{names or '未命名食物'}。",
            f"This value is synced from recognised dietary items; unrecognised food: {names or 'unnamed food'}.",
        )
    if detail.get("target"):
        lower, upper = detail["target"]
        if current < lower:
            return "attention", _ui("低于目标", "Below target"), _ui("当前值低于今日目标下限。", "The current value is below today's target minimum.")
        if upper is not None and current > upper:
            return "attention", _ui("高于目标", "Above target"), _ui("当前值高于今日目标上限。", "The current value is above today's target maximum.")
        return "good", _ui("处于目标范围", "In target range"), _ui("当前值处于今日目标范围内。", "The current value is within today's target range.")
    if detail.get("baseline") is None:
        return "muted", _ui("基线建立中", "Baseline building"), _ui("记录更多完整日期后建立个人基线。", "Log more complete days to build a personal baseline.")
    return "muted", _ui("目标未设置", "Target not set"), _ui("当前营养目标尚未设置。", "A nutrition target has not been set.")


def _records_with_live_draft(records, day, live_summary, replacing_record_id):
    """Replace the open meal with its draft for every same-page calculation."""
    aligned_records = [record for record in records if record.get("id") != replacing_record_id]
    food_count = int(live_summary.get("food_count") or 0)
    identified = int(live_summary.get("identified_food_count") or 0)
    unidentified = int(live_summary.get("unidentified_food_count") or 0)
    unidentified_names = list(live_summary.get("unidentified_food_names") or [])
    draft_items = []
    if food_count:
        if identified:
            draft_items.append({
                "food_catalog_id": 1,
                "custom_food_name": None,
                **{metric: live_summary.get(metric) for metric in METRICS},
            })
            draft_items.extend({"food_catalog_id": 1, "custom_food_name": None} for _ in range(max(identified - 1, 0)))
        draft_items.extend(
            {"food_catalog_id": None, "custom_food_name": name}
            for name in (unidentified_names or ["未命名食物"] * unidentified)[:unidentified]
        )
    aligned_records.append({"id": replacing_record_id, "date": day, "status": "completed", "items": draft_items})
    return aligned_records


def _category_feedback(service, summary):
    """Short feedback grounded in the same current/goal values as category cards."""
    if not summary.get("identified_food_count"):
        return service.meal_feedback(summary)
    situations, suggestion = [], None
    for metric, detail in service.daily_metrics().items():
        current, target = detail.get("current"), detail.get("target")
        if current is None or not target:
            continue
        lower, upper = target
        label = _feedback_metric_label(metric)
        if current < lower:
            situations.append(_ui(f"{label}低于今日目标。", f"{label} is below today's target."))
            suggestion = suggestion or _ui(f"后续餐次优先补充{label}来源。", f"Prioritise a {label.lower()} source later today.")
        elif upper is not None and current > upper:
            situations.append(_ui(f"{label}高于今日目标。", f"{label} is above today's target."))
        elif len(situations) < 2:
            situations.append(_ui(f"{label}处于今日目标范围。", f"{label} is within today's target range."))
        if len(situations) >= 3:
            break
    return {
        "status": "ready",
        "situations": situations[:3],
        "suggestion": suggestion or _ui("继续完成当天饮食记录后再查看整体反馈。", "Continue logging today's meals for a fuller review."),
    }


def _daily_calorie_balance(connection, day, intake):
    """Return expenditure minus recorded intake for a day.

    A positive value is a calorie gap; a negative value is a calorie surplus.
    The meal editor can contain a live, unsaved draft, so ``intake`` is passed
    in by the caller rather than read again from the database.
    """
    if not day or intake is None:
        return None
    try:
        row = connection.execute(
            "SELECT calories FROM daily_recovery_metrics WHERE date=? LIMIT 1",
            (str(day),),
        ).fetchone()
        expenditure = row["calories"] if row else None
        if expenditure is None:
            return None
        return float(expenditure) - float(intake)
    except (TypeError, ValueError, KeyError):
        return None


def _calorie_balance_advice(balance, training_goal, configured_adjustment=None):
    """Translate the current calorie gap/surplus into one concise suggestion."""
    if balance is None:
        return None
    try:
        balance = float(balance)
    except (TypeError, ValueError):
        return None
    threshold = 100.0
    configured = None
    try:
        if configured_adjustment is not None:
            configured = float(configured_adjustment)
    except (TypeError, ValueError):
        configured = None
    amount = abs(round(balance))
    if abs(balance) <= threshold:
        return _ui(
            "按当前已记录摄入，热量基本平衡；后续继续结合训练量和身体变化调整份量。",
            "Based on the intake logged so far, calories are broadly balanced; adjust portions with training load and body changes in mind.",
        )

    if balance > threshold:  # expenditure > intake: calorie gap
        if training_goal == "fat_loss":
            if configured is not None and balance > configured * 1.5:
                return _ui(
                    f"当前热量缺口约 {amount} kcal，明显高于设定缺口；后续不要继续压低摄入，优先补充蛋白质、蔬菜和全谷物以保证恢复。",
                    f"The current calorie gap is about {amount} kcal, well above the configured gap; do not restrict further, and prioritise protein, vegetables, and whole grains for recovery.",
                )
            return _ui(
                f"当前热量缺口约 {amount} kcal，符合减脂方向；后续保持适度缺口，优先安排蛋白质和高纤维食物。",
                f"The current calorie gap is about {amount} kcal, consistent with fat loss; keep it moderate and prioritise protein and high-fibre foods later.",
            )
        if training_goal == "muscle_gain":
            return _ui(
                f"当前热量缺口约 {amount} kcal，与增肌目标不一致；后续餐次增加一份主食或其他高营养密度食物，并保证蛋白质。",
                f"The current calorie gap is about {amount} kcal, which conflicts with muscle gain; add a carbohydrate or other nutrient-dense food later and keep protein adequate.",
            )
        return _ui(
            f"当前热量缺口约 {amount} kcal；如果并非主动控重，后续餐次补充一份均衡食物，避免缺口持续扩大。",
            f"The current calorie gap is about {amount} kcal; unless intentional, add a balanced food later to avoid extending the gap.",
        )

    # intake > expenditure: calorie surplus
    if training_goal == "muscle_gain":
        if configured is not None and abs(balance) > configured * 1.5:
            return _ui(
                f"当前热量盈余约 {amount} kcal，明显高于设定盈余；后续控制高能量密度零食，保持适度盈余并优先蛋白质和主食。",
                f"The current calorie surplus is about {amount} kcal, well above the configured surplus; limit energy-dense snacks and keep a moderate surplus built around protein and carbohydrates.",
            )
        return _ui(
            f"当前热量盈余约 {amount} kcal，符合增肌方向；后续保持适度盈余，优先蛋白质、主食和训练后恢复。",
            f"The current calorie surplus is about {amount} kcal, consistent with muscle gain; keep it moderate and prioritise protein, carbohydrates, and post-training recovery.",
        )
    if training_goal == "fat_loss":
        return _ui(
            f"当前热量盈余约 {amount} kcal，与减脂目标不一致；后续减少高能量密度零食，优先选择蛋白质、蔬菜和全谷物。",
            f"The current calorie surplus is about {amount} kcal, which conflicts with fat loss; reduce energy-dense snacks and favour protein, vegetables, and whole grains later.",
        )
    return _ui(
        f"当前热量盈余约 {amount} kcal；如果并非主动增重，后续控制份量和高能量密度食物，避免盈余持续扩大。",
        f"The current calorie surplus is about {amount} kcal; unless intentional, moderate portions and energy-dense foods later to avoid extending the surplus.",
    )


def _nutrition_advice(connection, summary, targets=None, day=None):
    """Generate non-redundant advice from goals, balance, and body context."""
    goals = get_personal_goals(connection) or {}
    body = latest_body_measurement(connection) or {}
    advice = []
    training_goal = goals.get("training_goal") or "maintenance"
    goal_text = {
        "muscle_gain": _ui(
            "训练目标（增肌期）：后续餐次优先安排优质蛋白，并在训练前后搭配适量主食或水果。",
            "Training goal (muscle gain): prioritise quality protein, with a suitable carbohydrate source around training.",
        ),
        "fat_loss": _ui(
            "训练目标（减脂期）：保持蛋白质和蔬菜/全谷物摄入，优先选择低能量密度食物，减少随意加餐。",
            "Training goal (fat loss): keep protein and vegetables/whole grains consistent; favour lower-energy-density foods and limit unplanned snacks.",
        ),
        "maintenance": _ui(
            "训练目标（保持期）：保持蛋白质、主食、蔬菜和水分的稳定搭配，并根据训练量调整份量。",
            "Training goal (maintenance): keep protein, carbohydrates, vegetables, and fluids consistent, adjusting portions to training load.",
        ),
    }
    configured_adjustment = goals.get("daily_calorie_adjustment_kcal")
    balance = _daily_calorie_balance(connection, day, summary.get("calories_kcal"))
    balance_advice = _calorie_balance_advice(
        balance, training_goal, configured_adjustment,
    )
    advice.append(balance_advice or goal_text[training_goal])

    targets = targets or {}
    protein_low = (
        summary.get("protein_g") is not None and targets.get("protein_g")
        and summary["protein_g"] < targets["protein_g"][0]
    )
    fiber_low = (
        summary.get("fiber_g") is not None and targets.get("fiber_g")
        and summary["fiber_g"] < targets["fiber_g"][0]
    )
    water_low = (
        summary.get("water_ml") is not None and targets.get("water_ml")
        and summary["water_ml"] < targets["water_ml"][0]
    )
    if protein_low and fiber_low:
        advice.append(_ui(
            "饮食搭配：下一餐同时加入一份蛋白质和一份蔬菜或全谷物，让搭配更均衡。",
            "Meal balance: add both a protein source and vegetables or whole grains at the next meal.",
        ))
    elif protein_low:
        advice.append(_ui(
            "饮食搭配：下一餐优先补充一份蛋白质来源，并与主食和蔬菜组合。",
            "Meal balance: prioritise a protein source next, paired with a carbohydrate and vegetables.",
        ))
    elif fiber_low:
        advice.append(_ui(
            "饮食搭配：下一餐增加蔬菜、水果或全谷物，改善膳食纤维和整体多样性。",
            "Meal balance: add vegetables, fruit, or whole grains next to improve fibre and variety.",
        ))
    elif water_low:
        advice.append(_ui(
            "饮食搭配：结合训练前后和餐间时段分次补充水分。",
            "Meal balance: add fluids in smaller amounts around training and between meals.",
        ))
    else:
        advice.append(_ui(
            "饮食搭配：继续保持蛋白质、主食、蔬菜/水果和水分的组合，避免单一来源。",
            "Meal balance: keep a combination of protein, carbohydrates, vegetables/fruit, and fluids.",
        ))

    current_weight = body.get("weight_kg")
    target_weight = goals.get("target_weight_kg")
    current_body_fat = body.get("body_fat_percent")
    target_body_fat = goals.get("target_body_fat_percent")
    if current_body_fat is not None and target_body_fat is not None and current_body_fat > target_body_fat:
        advice.append(_ui(
            "身体情况：当前体脂高于设定目标，优先保持规律训练和高蛋白、低能量密度的饮食结构。",
            "Body context: body fat is above the set target; keep training regular and favour a high-protein, lower-energy-density pattern.",
        ))
    elif current_weight is not None and target_weight is not None:
        if training_goal == "fat_loss" and current_weight > target_weight:
            advice.append(_ui(
                "身体情况：当前体重高于目标，保持稳定的能量控制和训练节奏，避免用极端节食替代长期习惯。",
                "Body context: current weight is above target; keep energy control and training steady rather than using extreme restriction.",
            ))
        elif training_goal == "muscle_gain" and current_weight < target_weight:
            advice.append(_ui(
                "身体情况：当前体重低于目标，训练日可在正餐或训练后增加一份营养密度较高的食物。",
                "Body context: current weight is below target; add a nutrient-dense food to a main or post-training meal.",
            ))
    elif not body:
        advice.append(_ui(
            "身体情况：补充近期体重、体脂等数据后，建议可以进一步结合身体变化调整。",
            "Body context: recent weight and body-composition data would make these suggestions more personalised.",
        ))
    return advice[:3]


def _render_today_nutrition(
    records,
    day,
    *,
    historical=False,
    section_number=3,
    targets=None,
    live_meal_summary=None,
    replacing_record_id=None,
):
    """Render day totals, optionally replacing the open meal with its live draft.

    This keeps the category cards aligned with the values currently visible in
    the food/drink editor instead of waiting for a save-and-rerun cycle.
    """
    aligned_records = records if live_meal_summary is None else _records_with_live_draft(
        records, day, live_meal_summary, replacing_record_id,
    )
    active_targets = {
        metric: target for metric, target in (targets or {}).items()
        if target and target[0] is not None
    }
    service = NutritionFeedbackService(aligned_records, day, LANGUAGE, targets=active_targets)
    metrics = service.daily_metrics()
    summary = service.today_summary()
    section_title = (
        _ui(f"{section_number}. 营养详情", f"{section_number}. Nutrition Details")
        if historical
        else _ui("今日营养详情", "Today's Nutrition Details")
    )
    st.subheader(section_title)
    st.caption(_ui(
        "以下为所选日期已记录摄入；未识别食物不会按 0 计算。"
        if historical else "以下数据已与上方饮食记录对齐；目标范围会根据个人资料、训练目标和热量缺口自动更新。",
        "These are recorded intakes for the selected date; unrecognised foods are not counted as zero."
        if historical else "These values are aligned with the food record above; target ranges update automatically from personal details, training goals, and the calorie adjustment.",
    ))
    cards = []
    for metric in METRICS:
        detail = metrics[metric]
        status_style, status_text, status_description = _today_nutrition_status(metric, detail, summary)
        baseline_text = _feedback_value(metric, detail["baseline"]) if detail["baseline"] is not None else _ui("建立中", "Building")
        if detail["target"]:
            lower, upper = detail["target"]
            target_text = _feedback_value(metric, lower)
            if upper is not None:
                target_text += f"–{_feedback_value(metric, upper)}"
        else:
            target_text = _ui("未设置", "Not set")
        difference_text = _recommendation_difference(metric, detail["current"], detail["target"])
        actual_value_text = _ui("实际值：", "Actual: ") + _feedback_value(metric, detail["current"])
        cards.append(
            f'<article class="drc-today-nutrition-card drc-today-nutrition-card--{escape(status_style)}" tabindex="0">'
            '<div class="drc-today-nutrition-card-head">'
            f'<div class="drc-today-nutrition-name">{escape(_feedback_metric_label(metric))}</div>'
            f'<div class="drc-today-nutrition-difference {status_style}" title="{escape(status_description)}">'
            f'<span>{escape(str(difference_text))}</span>'
            '</div>'
            '</div>'
            f'<div class="drc-today-nutrition-value">{escape(actual_value_text.replace(" ", "\u00a0"))}</div>'
            '<div class="drc-today-nutrition-meta">'
            f'<span>{escape(_ui("目标值", "Target value"))}：{escape(str(target_text))}</span>'
            f'<span>{escape(_ui("典型值", "Typical"))}：{escape(str(baseline_text))}</span>'
            '</div>'
            '</article>'
        )
    _render_html(f'<div class="drc-today-nutrition-grid">{"".join(cards)}</div>')
    return service, active_targets


def _polar_resting_calories(metrics):
    """Derive Polar's resting/BMR estimate from its daily activity fields."""
    total = metrics.get("calories")
    active = metrics.get("active_calories")
    if total in (None, "") or active in (None, ""):
        return None
    try:
        estimate = float(total) - float(active)
    except (TypeError, ValueError):
        return None
    return estimate if estimate >= 0 else None

SIMPLE_NUTRITION_CSS = """
<style>
.drc-simple-title,.drc-simple-position,.drc-nutrition-column-title{display:flex;align-items:center;justify-content:center;text-align: center !important;font-weight:600;min-height:2.5rem}
div[data-testid="stNumberInput"] input{
    box-sizing:border-box!important;
    padding-left:0!important;
    padding-right:0!important;
    text-indent:0!important;
    text-align:center!important;
}
div[data-testid="stNumberInput"] button{display:none!important}
div[data-testid="stNumberInput"] button[aria-label*="Clear"],
div[data-testid="stNumberInput"] button[title*="Clear"],
div[data-testid="stNumberInput"] button[aria-label*="clear" i],
div[data-testid="stNumberInput"] button[title*="clear" i]{
    display:none!important;
}
div[data-testid="stTextInput"] label{display:flex!important;justify-content:center!important;width:100%!important;text-align:center!important}
div[data-testid="stTextInput"] input{text-align:center!important}
div[data-testid="stTextInput"] input:disabled{color:var(--text-color)!important;-webkit-text-fill-color:var(--text-color)!important;opacity:1!important}
div[data-testid="stSelectbox"] div[data-baseweb="select"] div[value]{
    flex:1 1 auto!important;
    width:100%!important;
    padding-left:2rem!important;
    text-align:center!important;
}
div[data-testid="stSelectbox"] div[data-baseweb="select"] input{
    text-align:center!important;
}
div[data-testid="stDateInput"] label,
div[data-testid="stTimeInput"] label{
    display:flex!important;
    justify-content:center!important;
    width:100%!important;
    text-align:center!important;
}
div[data-testid="stDateInput"] input{
    text-align:center!important;
}
div[data-testid="stTimeInput"] div[data-baseweb="select"] div[value]{
    flex:1 1 auto!important;
    width:100%!important;
    text-align:center!important;
    transform:translateX(1rem)!important;
}
/* Keep the nutrition-cycle controls visually aligned with the strength-cycle
   controls: the same type scale, weight, and high-contrast dark-theme text. */
[class*="st-key-nutrition_cycle_"],[class*="st-key-nutrition_new_cycle_"]{text-align:center!important}
[class*="st-key-nutrition_cycle_"] [data-testid="stWidgetLabel"],[class*="st-key-nutrition_new_cycle_"] [data-testid="stWidgetLabel"]{display:flex!important;justify-content:center!important;width:100%!important;text-align:center!important;color:var(--text-color)!important;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif!important;font-size:1rem!important;font-weight:600!important;opacity:1!important}
[class*="st-key-nutrition_cycle_"] [data-testid="stWidgetLabel"] p,[class*="st-key-nutrition_new_cycle_"] [data-testid="stWidgetLabel"] p{width:100%!important;text-align:center!important}
[class*="st-key-nutrition_cycle_"] input,[class*="st-key-nutrition_new_cycle_"] input,[class*="st-key-nutrition_cycle_"] [data-baseweb="select"] > div,[class*="st-key-nutrition_new_cycle_"] [data-baseweb="select"] > div{color:var(--text-color)!important;-webkit-text-fill-color:var(--text-color)!important;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif!important;font-size:1rem!important;font-weight:600!important;opacity:1!important}
[class*="st-key-nutrition_cycle_"] [data-baseweb="select"] *,[class*="st-key-nutrition_new_cycle_"] [data-baseweb="select"] *{color:var(--text-color)!important;-webkit-text-fill-color:var(--text-color)!important;font-family:ui-sans-serif,-apple-system,"system-ui","SF Pro Text","PingFang SC","PingFang TC","Microsoft YaHei","Segoe UI",sans-serif!important;font-size:1rem!important;font-weight:600!important;opacity:1!important}
[class*="st-key-nutrition_cycle_"]:has(input:disabled),[class*="st-key-nutrition_new_cycle_"]:has(input:disabled),[class*="st-key-nutrition_cycle_"] div[data-testid="stTextInput"]:has(input:disabled),[class*="st-key-nutrition_new_cycle_"] div[data-testid="stTextInput"]:has(input:disabled){opacity:1!important}
.drc-feedback-heading{display:flex;align-items:center;justify-content:space-between;gap:1rem;margin:0 0 .35rem}
.drc-feedback-heading-title{margin:0;font-size:var(--drc-subsection-title-size);font-weight:600;line-height:1.4}
.drc-feedback-statuses{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:.4rem}
.drc-feedback-status{display:inline-flex;align-items:center;padding:.2rem .55rem;border:1px solid var(--secondary-background-color);border-radius:999px;font-size:.78rem;line-height:1.25;white-space:nowrap}
.drc-feedback-status.success{border-color:#2d9d6f;color:#2d9d6f}
.drc-feedback-status.warning{border-color:#d28a28;color:#d28a28}
.drc-nutrient-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:4.35rem;column-gap:.5rem;row-gap:.3rem;margin-bottom:.55rem;align-items:start}
.drc-nutrient-card,.drc-feedback-card{box-sizing:border-box;border:1px solid var(--secondary-background-color);background:var(--secondary-background-color);border-radius:.75rem}
.drc-nutrient-card{display:flex;flex-direction:column;justify-content:center;height:4.35rem;padding:.45rem .75rem}
.drc-nutrient-name{font-size:.8rem;opacity:.78;margin-bottom:.12rem}
.drc-nutrient-value{font-size:1.12rem;font-weight:650;line-height:1.2;white-space:nowrap}
.drc-feedback-detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.5rem;margin-bottom:.65rem}
.drc-feedback-card{min-height:5.8rem;padding:.6rem .75rem}
.drc-feedback-card-title{font-weight:650;margin-bottom:.3rem}
.drc-feedback-card p{margin:0;line-height:1.55}
.drc-feedback-card ul{list-style:none;margin:0;padding:0}
.drc-feedback-card li{display:flex;gap:.4rem;line-height:1.55;margin:.18rem 0}
.drc-feedback-dot{color:#ff4b4b;font-weight:700}
.drc-meal-action-title{margin:.25rem 0 .55rem;font-size:.9rem;font-weight:650;opacity:.8}
.drc-today-nutrition-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:minmax(8.25rem,auto);gap:.75rem;min-width:0;margin:.6rem 0 1rem}
.drc-today-nutrition-card{box-sizing:border-box;display:flex;flex-direction:column;justify-content:flex-start;min-width:0;min-height:10.5rem;height:auto;padding:1.1rem 1.2rem;border:1px solid rgba(117,130,148,.2);border-radius:16px;background:linear-gradient(145deg,rgba(117,130,148,.095),rgba(117,130,148,.045));box-shadow:0 1px 1px rgba(15,23,42,.04),0 10px 24px rgba(15,23,42,.05);color:var(--rh-text);overflow:visible;outline:none}
.drc-today-nutrition-card:focus-visible{outline:2px solid rgba(82,105,128,.78);outline-offset:2px}
.drc-today-nutrition-card--good{border-color:rgba(58,166,117,.3)}
.drc-today-nutrition-card--attention{border-color:rgba(224,160,43,.34)}
.drc-today-nutrition-card--error{border-color:rgba(208,75,75,.36)}
.drc-today-nutrition-card--muted{border-color:rgba(117,130,148,.22)}
.drc-today-nutrition-card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:.65rem;min-width:0}
.drc-today-nutrition-name{color:var(--rh-text);font-size:.9375rem;font-weight:600;letter-spacing:-.004em;line-height:1.4;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.drc-today-nutrition-status{display:inline-flex;align-items:center;gap:.28rem;flex:0 0 auto;padding:.25rem .5rem;border-radius:var(--rh-radius-small);font-size:.75rem;font-weight:600;line-height:1.25;white-space:nowrap;background:var(--rh-surface-inset)}
.drc-today-nutrition-dot{width:.375rem;height:.375rem;border-radius:50%;background:#8c8c8c;display:inline-block;box-shadow:none}
.drc-today-nutrition-status.good{color:var(--rh-status-positive);background:var(--rh-status-positive-surface)}.drc-today-nutrition-status.good .drc-today-nutrition-dot{background:var(--rh-status-positive);box-shadow:none}
.drc-today-nutrition-status.attention{color:var(--rh-status-caution);background:var(--rh-status-caution-surface)}.drc-today-nutrition-status.attention .drc-today-nutrition-dot{background:var(--rh-status-caution);box-shadow:none}
.drc-today-nutrition-status.error{color:var(--rh-status-negative);background:var(--rh-status-negative-surface)}.drc-today-nutrition-status.error .drc-today-nutrition-dot{background:var(--rh-status-negative);box-shadow:none}
.drc-today-nutrition-status.muted{color:var(--rh-text-secondary)}
.drc-today-nutrition-difference{flex:0 1 62%;text-align:right;color:var(--rh-text-secondary);font-size:.75rem;font-weight:600;line-height:1.4}
.drc-today-nutrition-difference.good{color:var(--rh-status-positive)}.drc-today-nutrition-difference.attention{color:var(--rh-status-caution)}.drc-today-nutrition-difference.error{color:var(--rh-status-negative)}
.drc-today-nutrition-value{color:var(--rh-text);margin:.85rem 0 .55rem;min-width:0;font-size:clamp(1.5rem,1.65vw,2.25rem);font-weight:750;letter-spacing:-.02em;line-height:1.15;white-space:nowrap;overflow:visible;font-variant-numeric:tabular-nums}
.drc-today-nutrition-meta{display:flex;flex-direction:column;gap:.16rem;color:var(--rh-text-muted);font-size:.8125rem;line-height:1.4;white-space:normal;overflow:visible}
.drc-today-nutrition-meta span{overflow:visible;white-space:nowrap}
.drc-today-evaluation-inline{margin:.15rem 0 .75rem;padding:.55rem .75rem;border-top:1px solid rgba(127,127,127,.18);color:var(--text-color);font-size:.86rem;line-height:1.5}
.drc-today-evaluation-inline strong{font-weight:650}
.drc-today-evaluation-status{color:var(--text-color);opacity:.55;font-size:.76rem}
.drc-recipe-period-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.6rem;margin:.2rem 0 .8rem}
.drc-recipe-period-field{min-width:0;padding:.7rem .8rem;border:1px solid rgba(117,130,148,.22);border-radius:.7rem;background:rgba(117,130,148,.055)}
.drc-recipe-period-label{color:var(--rh-text-muted);font-size:.75rem;font-weight:600;line-height:1.35}
.drc-recipe-period-value{margin-top:.14rem;color:var(--rh-text);font-size:.95rem;font-weight:650;line-height:1.4;font-variant-numeric:tabular-nums}
.drc-cycle-section-title{margin:1rem 0 .65rem;color:var(--text-color);font-size:1.05rem;font-weight:650;line-height:1.5;text-align:center}
.drc-recipe-plan-grid{overflow-x:auto;margin:.35rem 0 .7rem;padding-bottom:.15rem}
.drc-recipe-plan-row{display:grid;grid-template-columns:1.15fr repeat(7,minmax(8rem,1fr));min-width:54rem;border-left:1px solid rgba(117,130,148,.22);border-top:1px solid rgba(117,130,148,.22)}
.drc-recipe-plan-cell{display:flex;align-items:center;justify-content:center;min-height:4.65rem;min-width:0;padding:.45rem;border-right:1px solid rgba(117,130,148,.22);border-bottom:1px solid rgba(117,130,148,.22);text-align:center}
.drc-recipe-plan-header,.drc-recipe-plan-label{display:flex;align-items:center;justify-content:center;width:100%;min-height:3rem;text-align:center}
.drc-recipe-plan-header{color:var(--rh-text-secondary);font-size:.78rem;font-weight:650;line-height:1.35}
.drc-recipe-plan-label{padding:0;color:var(--rh-text);font-size:.83rem;font-weight:650}
.drc-recipe-plan-entry{width:100%;padding:.42rem .48rem;border:1px solid rgba(214,151,32,.28);border-radius:.55rem;background:rgba(214,151,32,.10);color:var(--rh-text);font-size:.76rem;line-height:1.4;overflow-wrap:anywhere}
.drc-recipe-plan-empty{color:var(--rh-text-muted);font-size:.8rem}
.drc-recipe-edit-grid-marker,.drc-recipe-edit-cell-marker{display:none!important}
.drc-recipe-editor-marker,.drc-recipe-cycle-settings-marker{display:none!important}
.drc-meal-editor-marker{display:none!important}
div[data-testid="stExpander"]:has(.drc-recipe-editor-marker) label[data-testid="stWidgetLabel"],div[data-testid="stExpander"]:has(.drc-recipe-cycle-settings-marker) label[data-testid="stWidgetLabel"]{width:100%!important;justify-content:center!important;text-align:center!important}
div[data-testid="stExpander"]:has(.drc-recipe-editor-marker) label[data-testid="stWidgetLabel"] p,div[data-testid="stExpander"]:has(.drc-recipe-cycle-settings-marker) label[data-testid="stWidgetLabel"] p{width:100%!important;text-align:center!important}
div[data-testid="stExpander"]:has(.drc-recipe-editor-marker) [data-baseweb="input"] input,div[data-testid="stExpander"]:has(.drc-recipe-cycle-settings-marker) [data-baseweb="input"] input{text-align:center!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) label[data-testid="stWidgetLabel"],div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) label[data-testid="stWidgetLabel"]{display:flex!important;align-items:center!important;justify-content:center!important;width:100%!important;min-height:1.4rem;padding:0!important;text-align:center!important;line-height:1!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) label[data-testid="stWidgetLabel"] p,div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) label[data-testid="stWidgetLabel"] p{width:100%!important;margin:0!important;text-align:center!important;line-height:1.2!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) [data-baseweb="input"] input,div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) [data-testid="stTimeInput"] input{text-align:center!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) div[data-testid="stSelectbox"] [data-baseweb="select"]>div{position:relative}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) div[data-testid="stSelectbox"] [data-baseweb="select"]>div>div:first-child{position:absolute!important;inset:0;display:flex!important;align-items:center!important;justify-content:center!important;padding:0!important;text-align:center!important;line-height:1!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) div[data-testid="stSelectbox"] [data-baseweb="select"]>div>div:first-child *{padding:0!important;text-align:center!important;line-height:1!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) div[data-testid="stSelectbox"] [data-baseweb="select"]>div>div:last-child{margin-left:auto!important;z-index:1!important}
div[data-testid="stExpander"]:has(.drc-recipe-editor-marker) [data-baseweb="select"]>div{position:relative}
div[data-testid="stExpander"]:has(.drc-recipe-editor-marker) [data-baseweb="select"]>div>div:first-child{position:absolute!important;inset:0;display:flex!important;align-items:center;justify-content:center!important;text-align:center!important}
div[data-testid="stExpander"]:has(.drc-recipe-editor-marker) [data-baseweb="select"]>div>div:first-child *{text-align:center!important}
div[data-testid="stExpander"]:has(.drc-recipe-editor-marker) [data-baseweb="select"]>div>div:last-child{margin-left:auto!important;z-index:1!important}
div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) div[data-testid="stSelectbox"] [data-baseweb="select"]>div{position:relative}
div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) div[data-testid="stSelectbox"] [data-baseweb="select"]>div>div:first-child{position:absolute!important;inset:0;display:flex!important;align-items:center!important;justify-content:center!important;padding:0!important;text-align:center!important;line-height:1!important}
div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) div[data-testid="stSelectbox"] [data-baseweb="select"]>div>div:first-child *{padding:0!important;text-align:center!important;line-height:1!important}
div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) div[data-testid="stSelectbox"] [data-baseweb="select"]>div>div:last-child{margin-left:auto!important;z-index:1!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) [data-testid="stTimeInput"] [data-baseweb="select"]>div,div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) [data-testid="stTimeInput"] [data-baseweb="select"]>div{display:flex!important;align-items:center!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) [data-testid="stTimeInput"] [data-baseweb="select"] div[value],div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) [data-testid="stTimeInput"] [data-baseweb="select"] div[value]{display:flex!important;align-items:center!important;justify-content:center!important;min-height:100%!important;padding-top:0!important;padding-bottom:0!important;line-height:1.2!important}
div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) [data-testid="stTimeInput"] input{width:100%!important;text-align:center!important}
/* Streamlit's select labels use a baseline-aligned inner wrapper.  Pin the
   recipe editor controls to a real flex centre so labels and values remain
   centred on both axes regardless of the browser's native control padding. */
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) label[data-testid="stWidgetLabel"],div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) label[data-testid="stWidgetLabel"]{height:1.5rem!important;min-height:1.5rem!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) [data-testid="stSelectbox"] [data-baseweb="select"]>div,div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) [data-testid="stTimeInput"] [data-baseweb="select"]>div,div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) [data-testid="stSelectbox"] [data-baseweb="select"]>div,div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) [data-testid="stTimeInput"] [data-baseweb="select"]>div{position:relative!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) [data-testid="stSelectbox"] [data-baseweb="select"] div[value],div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-meal-editor-marker) [data-testid="stTimeInput"] [data-baseweb="select"] div[value],div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) [data-testid="stSelectbox"] [data-baseweb="select"] div[value],div[data-testid="stColumn"]:has(.drc-recipe-schedule-control-marker) [data-testid="stTimeInput"] [data-baseweb="select"] div[value]{position:absolute!important;inset:0!important;display:flex!important;align-items:center!important;justify-content:center!important;min-height:0!important;margin:0!important;padding:0!important;text-align:center!important;line-height:1.2!important;transform:none!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker){overflow-x:auto;gap:0!important;row-gap:0!important;margin:.35rem 0 .7rem;border:1px solid rgba(117,130,148,.22);border-radius:.75rem}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker)>div[data-testid="stElementContainer"]{margin:0!important;padding:0!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker)>div[data-testid="stElementContainer"]:has(.drc-recipe-edit-grid-marker){display:none!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stHorizontalBlock"]{position:relative;min-width:54rem;gap:0!important;margin:0!important;border-bottom:0!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stHorizontalBlock"]::after{content:"";position:absolute;z-index:2;right:0;bottom:0;left:0;height:1px;background:rgba(117,130,148,.48);pointer-events:none}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stHorizontalBlock"]:last-child::after{display:none}
/* Keep every meal row stable.  Long plans scroll inside their own cell rather
   than increasing a whole row and moving the surrounding schedule. */
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stHorizontalBlock"]:has(.drc-recipe-plan-label){height:7.5rem!important;min-height:7.5rem!important;max-height:7.5rem!important;align-items:stretch!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stHorizontalBlock"]:has(.drc-recipe-plan-label) div[data-testid="stColumn"]{height:100%!important;min-height:0!important}
/* Do not rely on percentage heights here: Streamlit resolves the nested
   column wrappers against their intrinsic content and leaves labels at the
   top of a cell.  Give each layer the row's fixed height explicitly. */
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stHorizontalBlock"]:has(.drc-recipe-plan-label)>div[data-testid="stColumn"],div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stHorizontalBlock"]:has(.drc-recipe-plan-label)>div[data-testid="stColumn"]>div[data-testid="stVerticalBlock"],div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stHorizontalBlock"]:has(.drc-recipe-plan-label)>div[data-testid="stColumn"]>div[data-testid="stVerticalBlock"]>div[data-testid="stElementContainer"]{height:7.5rem!important;min-height:7.5rem!important;max-height:7.5rem!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]{min-height:4.25rem;padding:0!important;border-right:1px solid rgba(117,130,148,.30);border-bottom:1px solid rgba(117,130,148,.52)!important;display:flex;align-items:stretch;justify-content:stretch}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:last-child{border-right:0}
/* Markers share Streamlit's element-container wrapper with visible content.
   Collapse that wrapper too; otherwise it occupies half of every cell and
   shifts the actual label/button away from the cell centre. */
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"] div[data-testid="stElementContainer"]:has(.drc-recipe-edit-cell-marker){display:none!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]>div[data-testid="stVerticalBlock"]{display:flex!important;flex:1 1 auto!important;align-items:stretch!important;justify-content:stretch!important;width:100%!important;height:100%!important;min-height:4.25rem!important;gap:0!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"] div[data-testid="stElementContainer"]{display:flex!important;align-items:stretch!important;justify-content:stretch!important;flex:1 1 auto!important;width:100%!important;min-height:4.25rem!important;height:100%!important;margin:0!important}
/* Streamlit places Markdown inside two intrinsic-width wrappers.  Centre the
   full wrapper, rather than only its text, so every header and meal label is
   centred against the actual table cell on both axes. */
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stHorizontalBlock"]:has(.drc-recipe-plan-label){display:flex!important;align-items:stretch!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]{align-self:stretch!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"] div[data-testid="stElementContainer"]>[data-testid="stMarkdown"],div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"] div[data-testid="stElementContainer"]>[data-testid="stMarkdown"]>div{display:flex!important;align-items:stretch!important;justify-content:stretch!important;flex:1 1 100%!important;width:100%!important;height:100%!important;min-width:0!important;min-height:0!important;margin:0!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stMarkdownContainer"]{flex:1 1 auto!important;width:100%;height:100%;min-height:4.25rem;display:flex;align-items:center;justify-content:center;text-align:center}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stMarkdownContainer"],div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) .drc-recipe-plan-header,div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) .drc-recipe-plan-label{align-self:stretch!important;align-items:center!important;display:flex!important;flex:1 1 auto!important;width:100%!important;height:100%!important;min-height:0!important;margin:0!important;text-align:center!important;justify-content:center!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stMarkdownContainer"] p{width:100%!important;margin:0!important;text-align:center!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stButton"]{display:flex!important;align-items:stretch!important;flex:1 1 auto!important;width:100%;height:100%}
/* Filled plan cells retain the normal scroll layout: the wrapper starts at
   the first line, and only its own content scrolls.  Empty cells receive the
   separate centred treatment below. */
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stButton"] button{position:relative!important;display:block!important;width:100%;min-height:4.25rem;height:100%;border:0!important;border-radius:0!important;background:transparent!important;color:var(--rh-text-secondary);font-size:.76rem;line-height:1.35;text-align:center;white-space:normal;padding:0!important;overflow:hidden!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stButton"] button>div{display:block!important;width:100%!important;height:100%!important;min-height:0!important;max-height:7.5rem!important;padding:.45rem!important;overflow-x:hidden!important;overflow-y:auto!important;overscroll-behavior:contain;scrollbar-gutter:stable;touch-action:pan-y}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stButton"] button>div>p{display:grid!important;place-items:center!important;width:100%!important;min-height:calc(7.5rem - .9rem)!important;margin:0!important;text-align:center!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stButton"] button>div::-webkit-scrollbar{width:.36rem}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stButton"] button>div::-webkit-scrollbar-thumb{background:rgba(167,181,200,.52);border-radius:999px}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-auto) [data-testid="stButton"] button{background:rgba(214,151,32,.10)!important;color:var(--rh-text)}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-manual) [data-testid="stButton"] button{background:rgba(77,145,214,.13)!important;color:var(--rh-text)}
/* Filled cells use the same readable text rhythm as the training-plan table. */
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-auto) [data-testid="stButton"] button,div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-manual) [data-testid="stButton"] button{font-size:.82rem!important;line-height:1.5!important;text-align:center!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-auto) [data-testid="stButton"] button>div,div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-manual) [data-testid="stButton"] button>div{padding:.6rem .7rem!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty) [data-testid="stButton"] button{color:var(--rh-text-muted)}
/* Empty plan cells are actions rather than scrollable content.  Make every
   Streamlit wrapper fill the table cell, then centre the add label on both
   axes so it cannot drift upward with the cell's intrinsic layout. */
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty){position:relative!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty) [data-testid="stButton"],div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty) [data-testid="stButton"] button,div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty) [data-testid="stButton"] button>div,div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty) [data-testid="stButton"] button>div p{display:flex!important;align-items:center!important;justify-content:center!important;width:100%!important;height:100%!important;min-height:0!important;max-height:none!important;margin:0!important;padding:0!important;text-align:center!important;line-height:1.35!important}
/* The add-action needs a positional wrapper as well as flex alignment.
   Streamlit otherwise gives that wrapper only its intrinsic text height and
   places it at the top of the fixed recipe row.  This rule is intentionally
   scoped to empty cells, so filled plan content is left untouched. */
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty)>div[data-testid="stVerticalBlock"]>div[data-testid="stElementContainer"]:has([data-testid="stButton"]){position:absolute!important;inset:0!important;display:flex!important;align-items:stretch!important;justify-content:stretch!important;width:auto!important;height:auto!important;min-height:0!important;max-height:none!important}
div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty)>div[data-testid="stVerticalBlock"]>div[data-testid="stElementContainer"]:has([data-testid="stButton"]) [data-testid="stButton"],div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty)>div[data-testid="stVerticalBlock"]>div[data-testid="stElementContainer"]:has([data-testid="stButton"]) button,div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty)>div[data-testid="stVerticalBlock"]>div[data-testid="stElementContainer"]:has([data-testid="stButton"]) button>div,div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) div[data-testid="stColumn"]:has(.drc-recipe-edit-cell-marker-empty)>div[data-testid="stVerticalBlock"]>div[data-testid="stElementContainer"]:has([data-testid="stButton"]) button>div>*{display:flex!important;align-items:center!important;justify-content:center!important;flex:1 1 auto!important;width:100%!important;height:100%!important;min-height:0!important;max-height:none!important;margin:0!important;padding:0!important;text-align:center!important}
@media (hover:hover) and (pointer:fine){div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stButton"] button{transition:background .16s ease,transform .16s ease!important}div[data-testid="stVerticalBlock"]:has(> div[data-testid="stElementContainer"] .drc-recipe-edit-grid-marker) [data-testid="stButton"] button:hover{transform:scale(.985);background:rgba(117,130,148,.12)!important}}
@media (hover:hover) and (pointer:fine){.drc-recipe-plan-entry{transition:transform .16s ease,background .16s ease}.drc-recipe-plan-entry:hover{transform:translateY(-1px);background:rgba(214,151,32,.15)}}
@media (prefers-reduced-motion:reduce){.drc-recipe-plan-entry{transition:none!important}.drc-recipe-plan-entry:hover{transform:none}}
@media (prefers-reduced-motion: reduce){.drc-today-nutrition-card{transition:none}.drc-today-nutrition-card:hover{transform:none}}
.drc-nutrition-target-heading{text-align:center;font-size:1rem;font-weight:700;margin:.1rem 0 .4rem}
div[data-testid="stNumberInput"] label{justify-content:center!important;text-align:center!important;width:100%!important}
@media (max-width: 900px){.drc-nutrient-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (max-width: 640px){
  .drc-recipe-period-grid{grid-template-columns:1fr}
  .drc-feedback-heading{align-items:flex-start;flex-direction:column;margin-top:.7rem}
  .drc-feedback-statuses{justify-content:flex-start}
  .drc-nutrient-grid,.drc-feedback-detail-grid,.drc-today-nutrition-grid{grid-template-columns:1fr}
  .drc-feedback-card{min-height:0}
}
@media (min-width: 641px) and (max-width: 900px){.drc-today-nutrition-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
"""
st.markdown(SIMPLE_NUTRITION_CSS, unsafe_allow_html=True)


def _meal_name(value):
    return TR(f"nutrition_entry.meals.{value}")


def _cell(value, css="drc-simple-title"):
    return f'<div class="{css}">{escape(str(value))}</div>'


def _time_value(value):
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).time()
        except (TypeError, ValueError):
            return datetime.now().time().replace(second=0, microsecond=0)


FIXED_RECOMMENDED_MEAL_TIMES = {
    "breakfast": "08:00", "morning_snack": "10:30", "lunch": "12:30",
    "afternoon_snack": "15:30", "dinner": "18:30", "bedtime_fuel": "21:30",
}


def _current_meal_time():
    current = datetime.now().astimezone()
    rounded_minute = (current.minute // 5) * 5
    return current.replace(minute=rounded_minute, second=0, microsecond=0).time()


def _recommended_meal_time(connection, meal_type, meal_date):
    predicted = predict_meal_time(connection, meal_type, meal_date)
    if predicted:
        return predicted
    fixed = FIXED_RECOMMENDED_MEAL_TIMES.get(meal_type)
    if fixed:
        return time.fromisoformat(fixed)
    if meal_type == "training_fuel":
        rows = connection.execute(
            """SELECT start_time FROM polar_training_sessions_raw
               WHERE date=? AND start_time IS NOT NULL ORDER BY start_time""",
            (meal_date.isoformat(),),
        ).fetchall()
        candidates = [_time_value(row[0]) for row in rows if row[0]]
        if candidates:
            reference = _current_meal_time()
            return min(candidates, key=lambda value: abs(
                value.hour * 60 + value.minute - reference.hour * 60 - reference.minute
            ))
    return _current_meal_time()


def _display_food(catalog):
    return food_display_name(catalog, LANGUAGE)


def _food_rows_state(existing, item_type):
    record_key = (existing or {}).get("id", 0)
    key = f"simple_food_row_ids_{item_type}_{record_key}"
    if key not in st.session_state:
        count = sum(
            1 for item in (existing or {}).get("items", [])
            if (item.get("item_type", "food") in {"food", "beverage"}
                if item_type == "food_beverage" else item.get("item_type", "food") == item_type)
        )
        st.session_state[key] = list(range(1, max(count, 1) + 1))
    return record_key, key


def _clear_editor_widget_state(editor_key):
    """Force a saved meal to render again from persisted database values."""
    markers = (
        f"simple_food_row_ids_food_{editor_key}",
        f"simple_food_row_ids_beverage_{editor_key}",
        f"simple_food_row_ids_food_beverage_{editor_key}",
        f"food_food_", f"food_beverage_", f"supplement_",
    )
    for key in list(st.session_state):
        if key in markers[:3] or (
            any(key.startswith(prefix) for prefix in markers[3:])
            and f"_{editor_key}" in key
        ):
            del st.session_state[key]


def _food_editor(connection, existing, item_type, editor_key=None):
    catalog_items = list_food_catalog(connection)
    combined = item_type == "food_beverage"
    editor_catalog_items = [
        item for item in catalog_items
        if combined or ("beverage" in item["category_tags"]) == (item_type == "beverage")
    ]
    by_id = {item["id"]: item for item in catalog_items}
    by_display_name = {
        name: item
        for item in catalog_items
        for name in (
            item["canonical_name"], item["display_name_zh"], item["display_name_en"],
            _display_food(item),
        )
        if name
    }
    saved_items = [
        item for item in (existing or {}).get("items", [])
        if (
            item.get("item_type", "food") in {"food", "beverage"}
            if combined else item.get("item_type", "food") == item_type
        )
    ]
    record_key, row_ids_key = _food_rows_state(existing, item_type)
    if editor_key is not None:
        record_key = editor_key
        row_ids_key = f"simple_food_row_ids_{item_type}_{record_key}"
        if row_ids_key not in st.session_state:
            st.session_state[row_ids_key] = list(range(1, max(len(saved_items), 1) + 1))
    pending_add_key = f"food_{item_type}_pending_add_{record_key}"
    pending_add = bool(st.session_state.pop(pending_add_key, False))
    if not pending_add:
        active_ids = []
        for row_id in st.session_state[row_ids_key]:
            if row_id <= len(saved_items):
                active_ids.append(row_id)
                continue
            name_key = f"food_{item_type}_name_{record_key}_{row_id}"
            if str(st.session_state.get(name_key) or "").strip():
                active_ids.append(row_id)
        # Every food and beverage editor keeps one blank row, but stale extra
        # rows are discarded instead of appearing after a selection rerun.
        if not active_ids:
            active_ids = [min(st.session_state[row_ids_key], default=1)]
        st.session_state[row_ids_key] = active_ids
    recent = recent_foods(connection)
    recent_names = []
    for recent_item in recent:
        recent_catalog = recent_item.get("catalog")
        if not combined and recent_item.get("item_type") != item_type:
            continue
        recent_name = _display_food(recent_catalog) if recent_catalog else recent_item.get("custom_food_name")
        if recent_name and recent_name not in recent_names:
            recent_names.append(recent_name)
    recent_usage = {
        (item["food_catalog_id"] if item["food_catalog_id"] is not None else ("custom", item["custom_food_name"])): item
        for item in recent
    }
    favorites = favorite_foods(connection)
    widget_prefix = f"food_{item_type}"
    item_label = _ui(
        "食物/饮品" if combined else "食物" if item_type == "food" else "饮品",
        "Food / Beverage" if combined else "Food" if item_type == "food" else "Beverage",
    )
    add_item_label = TR("simple_nutrition.add_item")
    add_item_label = _ui(
        "添加食物/饮品" if combined else "添加食物" if item_type == "food" else "添加饮品",
        "Add Food / Beverage" if combined else "Add Food" if item_type == "food" else "Add Beverage",
    )
    if favorites:
        st.caption(TR("simple_nutrition.favorites") + "：" + " · ".join(
            _display_food(item) for item in favorites
        ))

    headers = (item_label, "quantity", "unit", "actions")
    for column, key in zip(st.columns((2.0, 1.0, 0.8, 0.8)), headers):
        # The first header is already a localized display label, not an i18n
        # lookup key. Translating it again produces `[missing: ...]` in zh-TW
        # because the traditionalized slash/name no longer matches a key.
        label = key if key in {"quantity", "unit", "actions"} else key
        if key in {"quantity", "unit", "actions"}:
            label = TR(f"simple_nutrition.{key}")
        column.markdown(_cell(label), unsafe_allow_html=True)

    rows = []
    for index, row_id in enumerate(list(st.session_state[row_ids_key])):
        saved = saved_items[row_id - 1] if isinstance(row_id, int) and 1 <= row_id <= len(saved_items) else {}
        saved_catalog = by_id.get(saved.get("food_catalog_id"))
        initial_food_name = _display_food(saved_catalog) if saved_catalog else (saved.get("custom_food_name") or "")
        columns = st.columns((2.0, 1.0, 0.8, 0.8))
        food_name_key = f"{widget_prefix}_name_{record_key}_{row_id}"
        unit_key = f"{widget_prefix}_unit_{record_key}_{row_id}"
        quantity_key = f"{widget_prefix}_quantity_{record_key}_{row_id}"

        def reset_food_preferences(name_state=food_name_key, unit_state=unit_key, quantity_state=quantity_key):
            selected_name = str(st.session_state.get(name_state) or "")
            selected = by_display_name.get(selected_name)
            usage_key = selected["id"] if selected else ("custom", selected_name.strip())
            usage = recent_usage.get(usage_key)
            st.session_state[unit_state] = (
                usage.get("unit") if usage and usage.get("unit") else
                selected["default_unit"] if selected else "g"
            )
            if usage and usage.get("quantity") not in (None, ""):
                st.session_state[quantity_state] = float(usage["quantity"])
            elif selected:
                # A newly selected food must not inherit the previous row's
                # amount (for example, 100 g becoming 100 individual buns).
                st.session_state[quantity_state] = float(selected.get("serving_quantity") or 1.0)

        catalog_names = [_display_food(item) for item in editor_catalog_items]
        food_options = [""] + recent_names + [
            name for name in catalog_names if name not in recent_names
        ]
        if initial_food_name and initial_food_name not in food_options:
            food_options.append(initial_food_name)
        food_name = columns[0].selectbox(
            TR("simple_nutrition.food_or_beverage"), food_options,
            index=food_options.index(initial_food_name) if initial_food_name else 0,
            key=food_name_key,
            on_change=reset_food_preferences, label_visibility="collapsed",
            accept_new_options=True,
            placeholder=_ui(
                "选择或输入食物/饮品" if combined else "选择或输入食物" if item_type == "food" else "选择或输入饮品",
                "Select or enter food or beverage" if combined else "Select or enter food" if item_type == "food" else "Select or enter beverage",
            ),
        ) or ""
        selected = by_display_name.get(food_name)
        custom_name = None if selected else food_name.strip() or None
        units = list(allowed_food_units(selected))
        usage_key = selected["id"] if selected else ("custom", food_name.strip())
        usage = recent_usage.get(usage_key) or {}
        initial_unit = (
            saved.get("unit") or usage.get("unit") or
            (selected or {}).get("default_unit") or
            ("ml" if item_type == "beverage" else "g")
        )
        if unit_key not in st.session_state or st.session_state[unit_key] not in units:
            st.session_state[unit_key] = initial_unit if initial_unit in units else units[0]
        unit = columns[2].selectbox(
            TR("simple_nutrition.unit"), units, key=unit_key,
            format_func=lambda value: TR(food_unit_label_key(value)),
            label_visibility="collapsed",
        )
        quantity = columns[1].number_input(
            TR("simple_nutrition.quantity"), min_value=0.01,
            value=(
                saved.get("quantity") if saved.get("quantity") not in (None, "") else
                usage.get("quantity") if usage.get("quantity") not in (None, "") else
                None
            ),
            step=1.0 if unit in FOOD_COUNT_UNITS else 0.1,
            key=quantity_key, label_visibility="collapsed",
        )
        if columns[3].button(
            TR("simple_nutrition.delete_row"),
            key=f"{widget_prefix}_delete_{record_key}_{row_id}",
            use_container_width=True,
        ):
            st.session_state[row_ids_key].remove(row_id)
            if not st.session_state[row_ids_key]:
                st.session_state[row_ids_key] = [max(row_id, 1) + 1]
            st.rerun()

        rows.append({
            "uuid": saved.get("uuid"),
            "food_catalog_id": selected["id"] if selected else None,
            "custom_food_name": custom_name,
            "item_type": "beverage" if selected and "beverage" in selected["category_tags"] else "food",
            "quantity": quantity, "unit": unit,
            "brand": saved.get("brand"),
            "cooking_method": saved.get("cooking_method"),
            "notes": saved.get("notes"),
        })
    # The scanner's native upload trigger is intentionally more compact than
    # the add/library buttons. Reserve a matching compact middle column so all
    # three controls have the same visible gap instead of leaving a blank area
    # to the scanner's right.
    controls = st.columns((2, 1, 2), vertical_alignment="bottom")
    if controls[0].button(
        add_item_label, key=f"{widget_prefix}_add_{record_key}", use_container_width=True,
    ):
        next_id = max(st.session_state[row_ids_key], default=0) + 1
        st.session_state[row_ids_key].append(next_id)
        st.session_state[pending_add_key] = True
        # The row list has already been rendered in this Streamlit run.
        # Rerun immediately so a single click displays the new input row.
        st.rerun()
    if item_type in {"beverage", "food_beverage"}:
        with controls[1]:
            _nutrition_label_scanner(connection, record_key, scan_context="food")
        if controls[2].button(
            _custom_nutrition_library_label(connection, "food"),
            key=f"custom_nutrition_library_{record_key}",
            use_container_width=True,
        ):
            _show_custom_nutrition_library_dialog(connection, "food")
        saved_food_name = st.session_state.pop(
            f"nutrition_label_saved_flash_{record_key}", None
        )
        if saved_food_name:
            st.success(_ui(
                f"已保存“{saved_food_name}”，上传图片已清除。",
                f"Saved “{saved_food_name}”; the uploaded image has been cleared.",
            ))
    return rows


def _product_label(product):
    variant = f" · {product['product_variant']}" if product.get("product_variant") else ""
    return f"{product['product_name']}{variant}"


def _stored_supplement_kind(row, products_by_id):
    """Classify persisted custom rows as well as catalog-backed rows."""
    explicit_kind = row.get("product_kind")
    if explicit_kind in {"supplement", "medication"}:
        return explicit_kind
    product = products_by_id.get(str(row.get("supplement_product_id"))) or {}
    if product.get("product_kind") in {"supplement", "medication"}:
        return product["product_kind"]
    name = str(row.get("custom_product_name") or row.get("item_name") or "").strip().lower()
    brand = str(row.get("custom_brand_name") or row.get("brand_name") or "").strip().lower()
    if "非那雄胺" in name or "finasteride" in name or brand == "保法止":
        return "medication"
    return "supplement"


def _supplement_editor(connection, existing, record_key, taken_at, product_kind="supplement"):
    # Load the label-backed library first. It upgrades legacy OCR records to
    # linked products before this selector builds its candidate list.
    ingredient_library = list_custom_supplement_nutrition_library(connection)
    all_products = list_products(connection)
    all_products_by_id = {str(item["id"]): item for item in all_products}
    products = [item for item in all_products if item.get("product_kind") == product_kind]
    saved_rows = [
        row for row in (existing or {}).get("supplements", [])
        if _stored_supplement_kind(row, all_products_by_id) == product_kind
        and (
            row.get("supplement_product_id")
            or str(row.get("custom_brand_name") or "").strip()
            or str(row.get("custom_product_name") or row.get("item_name") or "").strip()
        )
    ]
    by_id = {item["id"]: item for item in products}
    row_ids_key = f"supplement_row_ids_{product_kind}_{record_key}"
    pending_add_key = f"supplement_pending_add_{product_kind}_{record_key}"
    if row_ids_key not in st.session_state:
        st.session_state[row_ids_key] = list(range(1, max(len(saved_rows), 1) + 1))
    pending_match = st.session_state.pop(
        f"supplement_ocr_pending_match_{product_kind}_{record_key}", None,
    )
    if pending_match:
        row_id = pending_match["row_id"]
        if row_id not in st.session_state[row_ids_key]:
            st.session_state[row_ids_key].append(row_id)
        prefix = f"supplement_{{}}_supplement_{record_key}_{row_id}"
        st.session_state[prefix.format("product")] = pending_match["product_name"]
        st.session_state[prefix.format("unit")] = pending_match["unit"]
        st.session_state[prefix.format("quantity")] = pending_match["quantity"]
        if pending_match.get("product_id") is not None:
            st.session_state[f"supplement_matched_product_id_{record_key}_{row_id}"] = pending_match["product_id"]
        else:
            st.session_state.pop(f"supplement_matched_product_id_{record_key}_{row_id}", None)
        st.session_state[f"supplement_scanned_brand_{record_key}_{row_id}"] = pending_match.get("brand")
        st.success(_ui(
            "已带入当前补剂行；请在保存本餐前核对剂量。",
            "Applied to the current supplement row. Review the dose before saving the meal.",
        ))
    pending_add = bool(st.session_state.pop(pending_add_key, False))
    if not pending_add and st.session_state[row_ids_key]:
        # Clear stale blank rows left in the current Streamlit session. A blank
        # row is kept only for the rerun immediately following Add Supplement /
        # Add Medication.
        active_ids = []
        for row_id in st.session_state[row_ids_key]:
            if row_id <= len(saved_rows):
                active_ids.append(row_id)
                continue
            product_value = st.session_state.get(f"supplement_product_{product_kind}_{record_key}_{row_id}", "")
            values_kind = _stored_supplement_kind(
                {"custom_product_name": product_value},
                {},
            )
            if str(product_value).strip() and values_kind == product_kind:
                active_ids.append(row_id)
        # Keep one empty input row in every supplement/medication editor while
        # removing only stale additional blanks.
        st.session_state[row_ids_key] = active_ids or [min(st.session_state[row_ids_key], default=1)]

    recent = recent_products(connection)
    intake_preferences = recent_intake_preferences(connection)
    learned_by_key = {}
    for preference in intake_preferences:
        if preference.get("supplement_product_id") is not None:
            learned_by_key[("product", int(preference["supplement_product_id"]))] = preference
        else:
            custom_name = str(preference.get("custom_product_name") or "").strip().casefold()
            if custom_name:
                learned_by_key[("custom", custom_name)] = preference
    recent_product_ids = [item["id"] for item in recent if item.get("id")]
    products.sort(key=lambda item: (
        recent_product_ids.index(item["id"]) if item["id"] in recent_product_ids else len(recent_product_ids),
        item.get("product_name") or "",
    ))
    favorites = favorite_products(connection)
    if favorites and product_kind == "supplement":
        st.caption(TR("supplement_products.favorite_product") + "：" + " · ".join(_product_label(item) for item in favorites))

    add_label = _ui("添加补剂", "Add Supplement") if product_kind == "supplement" else _ui("添加用药", "Add Medication")
    # Mirror food/beverage selection behaviour: recent choices first, then
    # the complete local catalog, including labels previously saved through
    # OCR as custom nutrition data.
    recent_names = []
    for item in recent:
        if item.get("product_kind") != product_kind:
            continue
        name = str(item.get("product_name") or "").strip()
        if name and name not in recent_names:
            recent_names.append(name)
    for preference in intake_preferences:
        if preference.get("product_kind") not in {None, product_kind}:
            continue
        name = str(
            preference.get("product_name") or preference.get("custom_product_name") or ""
        ).strip()
        if name and name not in recent_names:
            recent_names.append(name)
    custom_product_names = []
    latest_brand_by_product = {}
    if product_kind in {"supplement", "medication"}:
        for item in ingredient_library:
            if item.get("product_kind") != product_kind:
                continue
            name = str(item.get("product_name") or "").strip()
            if name and name not in custom_product_names:
                custom_product_names.append(name)
            brand = str(item.get("brand") or "").strip()
            if name and brand and name not in latest_brand_by_product:
                latest_brand_by_product[name] = brand
    product_display_by_name = {
        item["product_name"]: (
            f"{item['product_name']}（{latest_brand_by_product[item['product_name']]}）"
            if item["product_name"] in latest_brand_by_product else item["product_name"]
        )
        for item in products if item.get("product_name")
    }
    rows = []
    if st.session_state[row_ids_key]:
        headers = ("product_name", "quantity", "unit", "actions")
        # Keep the three nutrition sections visually aligned: only the first
        # column's label changes (food/beverage, supplement, medication).
        supplement_column_widths = (2.0, 1.0, .8, .8)
        header_labels = {
            "product_name": _ui("补剂类型", "Supplement Type")
            if product_kind == "supplement" else _ui("药物类型", "Medication Type"),
            "quantity": TR("supplement_products.quantity"),
            "unit": TR("supplement_products.unit"),
            "actions": TR("supplement_products.actions"),
        }
        for column, key in zip(st.columns(supplement_column_widths), headers):
            column.markdown(_cell(header_labels[key]), unsafe_allow_html=True)
        for index, row_id in enumerate(list(st.session_state[row_ids_key])):
            saved = saved_rows[row_id - 1] if isinstance(row_id, int) and 1 <= row_id <= len(saved_rows) else {}
            saved_product = by_id.get(int(saved["supplement_product_id"])) if str(saved.get("supplement_product_id") or "").isdigit() else None
            matched_product = by_id.get(st.session_state.get(f"supplement_matched_product_id_{record_key}_{row_id}"))
            initial_product_name = (
                matched_product.get("product_name") if matched_product else
                saved_product.get("product_name") if saved_product else
                saved.get("custom_product_name") or saved.get("item_name") or ""
            )
            columns = st.columns(supplement_column_widths)
            catalog_product_names = [item["product_name"] for item in products if item.get("product_name")]
            raw_product_options = list(dict.fromkeys(
                recent_names + custom_product_names + catalog_product_names
            ))
            product_options = [""] + [product_display_by_name.get(name, name) for name in raw_product_options]
            option_to_product_name = {
                product_display_by_name.get(name, name): name for name in raw_product_options
            }
            initial_product_option = product_display_by_name.get(initial_product_name, initial_product_name)
            if initial_product_option and initial_product_option not in product_options:
                product_options.append(initial_product_option)
            product_label = _ui("补剂类型", "Supplement Type") if product_kind == "supplement" else _ui("用药类型", "Medication Type")
            product_state_key = f"supplement_product_{product_kind}_{record_key}_{row_id}"
            if st.session_state.get(product_state_key) == initial_product_name and initial_product_option != initial_product_name:
                st.session_state[product_state_key] = initial_product_option
            unit_key = f"supplement_unit_{product_kind}_{record_key}_{row_id}"
            quantity_key = f"supplement_quantity_{product_kind}_{record_key}_{row_id}"

            def reset_supplement_preferences(
                product_key=product_state_key,
                unit_state=unit_key,
                quantity_state=quantity_key,
            ):
                chosen = str(st.session_state.get(product_key) or "")
                raw_name = option_to_product_name.get(chosen, chosen).strip()
                chosen_product = next(
                    (item for item in products if item.get("product_name", "").strip() == raw_name),
                    None,
                )
                learned = learned_by_key.get(
                    ("product", int(chosen_product["id"])) if chosen_product
                    else ("custom", raw_name.casefold())
                )
                st.session_state[unit_state] = (
                    learned.get("unit") if learned and learned.get("unit")
                    else (chosen_product or {}).get("default_intake_unit") or "g"
                )
                st.session_state[quantity_state] = (
                    float(learned["quantity"]) if learned and learned.get("quantity") not in (None, "")
                    else float((chosen_product or {}).get("serving_quantity") or 1.0)
                )

            product_choice = columns[0].selectbox(_ui(product_label, TR("supplement_products.product_name")), product_options, index=product_options.index(initial_product_option) if initial_product_option else 0, key=product_state_key, on_change=reset_supplement_preferences, label_visibility="collapsed", accept_new_options=True, placeholder=_ui("选择或输入补剂类型" if product_kind == "supplement" else "选择或输入药品名称", "Select or enter supplement" if product_kind == "supplement" else "Select or enter medication")) or ""
            product_name = option_to_product_name.get(product_choice, product_choice)
            selected = matched_product if (
                matched_product and product_name.strip() == matched_product.get("product_name", "").strip()
            ) else next(
                (item for item in products if item.get("product_name", "").strip() == product_name.strip()),
                None,
            )
            learned = learned_by_key.get(
                ("product", int(selected["id"])) if selected
                else ("custom", product_name.strip().casefold())
            )
            initial_unit = (
                saved.get("unit") or (learned or {}).get("unit") or
                (selected or {}).get("default_intake_unit") or "g"
            )
            units = list(SUPPLEMENT_UNITS)
            if unit_key not in st.session_state or st.session_state[unit_key] not in units:
                st.session_state[unit_key] = initial_unit if initial_unit in units else units[0]
            unit = columns[2].selectbox(TR("supplement_products.unit"), units, key=unit_key, format_func=lambda value: TR(unit_label_key(value)), label_visibility="collapsed")
            initial_quantity = (
                saved.get("quantity") if saved.get("quantity") not in (None, "") else
                (learned or {}).get("quantity") if (learned or {}).get("quantity") not in (None, "") else
                (selected or {}).get("serving_quantity") if selected else
                (1.0 if product_name.strip() else None)
            )
            if not product_name.strip() and saved.get("quantity") in (None, ""):
                st.session_state[quantity_key] = None
            elif product_name.strip() and st.session_state.get(quantity_key) in (None, ""):
                st.session_state[quantity_key] = initial_quantity
            quantity = columns[1].number_input(
                TR("supplement_products.quantity"), min_value=0.01,
                value=initial_quantity,
                step=1.0 if unit in {"capsule", "tablet", "sachet", "scoop", "drop"} else .1,
                key=quantity_key, label_visibility="collapsed",
            )
            if columns[3].button(TR("simple_nutrition.delete_row"), key=f"supplement_delete_{product_kind}_{record_key}_{row_id}", use_container_width=True):
                st.session_state[row_ids_key].remove(row_id)
                if not st.session_state[row_ids_key]:
                    st.session_state[row_ids_key] = [max(row_id, 1) + 1]
                st.rerun()
            if selected:
                ingredients_ready = calculate_intake_ingredients(
                    connection, selected["id"], quantity, unit,
                ) is not None
                # A successful calculation is the normal state and should not
                # add visual noise beneath every input row. Only draw a status
                # when the user needs to resolve missing ingredient data.
                if not ingredients_ready:
                    st.caption(TR(
                        "supplement_products.ingredients_unconfirmed",
                        product=_product_label(selected),
                    ))
                if selected["product_kind"] == "medication":
                    st.warning(TR("supplement_products.medication_boundary"))
            rows.append({"supplement_product_id": selected["id"] if selected else None, "custom_brand_name": st.session_state.get(f"supplement_scanned_brand_{record_key}_{row_id}"), "custom_product_name": None if selected else product_name.strip() or None, "quantity": quantity, "unit": unit, "taken_at": taken_at, "notes": saved.get("notes") or saved.get("item_notes")})
    # Keep the action row visually balanced: the compact upload control lives
    # in the narrow center column and the two full-width actions flank it.
    controls = st.columns((2, 1, 2), vertical_alignment="bottom")
    if controls[0].button(
        add_label, key=f"supplement_add_{product_kind}_{record_key}", use_container_width=True,
    ):
        ids = st.session_state[row_ids_key]
        if len(ids) < 5:
            ids.append(max(ids, default=0) + 1)
            st.session_state[pending_add_key] = True
            # Render the newly appended blank row on this one click instead
            # of waiting for a second interaction with the page.
            st.rerun()
    if product_kind in {"supplement", "medication"}:
        with controls[1]:
            _nutrition_label_scanner(
                connection, f"{product_kind}_{record_key}",
                scan_context=product_kind, supplement_record_key=record_key,
            )
        if controls[2].button(
            _custom_nutrition_library_label(connection, product_kind),
            key=f"custom_{product_kind}_nutrition_library_{record_key}",
            use_container_width=True,
        ):
            _show_custom_nutrition_library_dialog(connection, product_kind)
    return rows


def _quick_actions(connection, existing, meal_type, meal_date, eaten_at, food_items, supplements):
    columns = st.columns(2)
    if columns[0].button(TR("simple_nutrition.copy_yesterday")):
        source_id = find_yesterday_meal_id(connection, meal_type, meal_date.isoformat())
        if source_id:
            new_id = copy_meal_record(connection, source_id, meal_date.isoformat(), eaten_at.isoformat(timespec="seconds"))
            st.session_state["simple_meal_selector_pending"] = new_id; st.success(TR("simple_nutrition.copied")); st.rerun()
        st.warning(TR("simple_nutrition.no_copy_source"))
    if columns[1].button(TR("simple_nutrition.copy_previous_meal")):
        source_id = find_previous_meal_id(connection, (existing or {}).get("id"))
        if source_id:
            new_id = copy_meal_record(connection, source_id, meal_date.isoformat(), eaten_at.isoformat(timespec="seconds"))
            st.session_state["simple_meal_selector_pending"] = new_id; st.success(TR("simple_nutrition.copied")); st.rerun()
        st.warning(TR("simple_nutrition.no_copy_source"))


def _next_unrecorded_meal_type(records, meal_date, extra_meal_type=None):
    recorded = {
        row.get("meal_type") for row in records
        if row.get("date") == meal_date.isoformat()
    }
    if extra_meal_type:
        recorded.add(extra_meal_type)
    return next((meal_type for meal_type in MEAL_TYPES if meal_type not in recorded), MEAL_TYPES[0])



def _render_active_nutrition_editor_body(
    connection, existing, editor_key, eaten_at_value, draft_key,
):
    """Render only the selected intake editor as an independently refreshed area."""
    section_options = ("diet", "supplement", "medication")
    section_labels = {
        "diet": _ui("🍽 饮食", "🍽 Diet"),
        "supplement": _ui("💊 补剂", "💊 Supplements"),
        "medication": _ui("用药", "Medication"),
    }
    st.session_state.setdefault("simple_active_nutrition_section", "diet")
    active_section = st.segmented_control(
        _ui("分类", "Category"),
        section_options,
        format_func=lambda value: section_labels[value],
        selection_mode="single",
        key="simple_active_nutrition_section",
        label_visibility="collapsed",
        width="stretch",
    ) or "diet"

    persisted_items = (existing or {}).get("items", [])
    persisted_products = {str(item["id"]): item for item in list_products(connection)}
    persisted_supplements = (existing or {}).get("supplements", [])
    persisted_medications = [
        item for item in persisted_supplements
        if _stored_supplement_kind(item, persisted_products) == "medication"
    ]
    persisted_regular_supplements = [
        item for item in persisted_supplements if item not in persisted_medications
    ]

    if active_section == "diet":
        food_items = _food_editor(connection, existing, "food_beverage", editor_key)
    else:
        food_items = list(persisted_items)

    if active_section == "supplement":
        supplements = _supplement_editor(
            connection, existing, editor_key, eaten_at_value, "supplement"
        )
    else:
        supplements = list(persisted_regular_supplements)

    if active_section == "medication":
        medications = _supplement_editor(
            connection, existing, editor_key, eaten_at_value, "medication"
        )
        supplements.extend(medications)
    supplements.extend(persisted_medications)

    # The parent form reads the draft on a save rerun. During a category
    # switch only this fragment reruns, so the rest of the page stays stable.
    st.session_state[draft_key] = {
        "active_section": active_section,
        "food_items": food_items,
        "supplements": supplements,
    }


@st.fragment
def _render_active_nutrition_editor(existing, editor_key, eaten_at_value, draft_key):
    """Own a short-lived database connection for fragment-only reruns."""
    # `main()` completed migration before the fragment is mounted. Skipping
    # schema checks here keeps a category switch limited to its editor work.
    editor_connection = connect(migrate=False)
    try:
        _render_active_nutrition_editor_body(
            editor_connection, existing, editor_key, eaten_at_value, draft_key,
        )
    finally:
        editor_connection.close()


def _render_current_nutrition_details(connection, records, meal_state, targets):
    """Render the read-only daily details outside the meal editor expander."""
    meal_date = meal_state["meal_date"]
    live_summary = summarize_draft_food_items(connection, meal_state["food_items"])
    _, resolved_targets = _render_today_nutrition(
        records,
        meal_date.isoformat(),
        section_number=2,
        targets=targets,
        live_meal_summary=live_summary,
        replacing_record_id=meal_state["record_id"],
    )
    aligned_records = _records_with_live_draft(
        records, meal_date.isoformat(), live_summary, meal_state["record_id"],
    )
    feedback_summary = NutritionFeedbackService(
        aligned_records, meal_date.isoformat(), LANGUAGE, targets=resolved_targets,
    ).today_summary()
    return feedback_summary, resolved_targets


def _render_current_nutrition_advice(connection, feedback_summary, targets, meal_state):
    """Keep advice separate so history can sit directly above it."""
    _render_meal_feedback(
        _nutrition_advice(
            connection,
            feedback_summary,
            targets,
            day=meal_state["meal_date"].isoformat(),
        ),
        meal_state["meal_type"],
        section_number=3,
    )


def _meal_form(connection, existing, records, targets=None, flash_key=None):
    record_key = (existing or {}).get("id", 0)
    _render_html('<span class="drc-meal-editor-marker"></span>')
    pending_section = st.session_state.pop("simple_pending_nutrition_section", None)
    if pending_section in {"diet", "supplement", "medication"}:
        st.session_state["simple_active_nutrition_section"] = pending_section
    meal_type = st.selectbox(
        TR("simple_nutrition.meal"), MEAL_TYPES,
        format_func=_meal_name, key="simple_active_meal_type",
    )
    left, right = st.columns(2)
    meal_date = left.date_input(
        TR("nutrition_entry.date"),
        key="simple_active_meal_date",
    )
    recommended_time = _recommended_meal_time(connection, meal_type, meal_date)
    planned_time = _time_value(
        (existing or {}).get("planned_meal_time") or recommended_time
    )
    time_key = f"simple_meal_time_{record_key}"
    recommendation_signature = f"{meal_type}:{meal_date.isoformat()}"
    signature_key = f"simple_meal_recommendation_signature_{record_key}"
    if existing:
        st.session_state.setdefault(
            time_key,
            _time_value(existing.get("actual_meal_time") or existing.get("eaten_at")),
        )
    elif st.session_state.get(signature_key) != recommendation_signature:
        st.session_state[time_key] = recommended_time
        st.session_state[signature_key] = recommendation_signature
    eaten_at = right.time_input(
        TR("simple_nutrition.actual_meal_time"),
        step=300, key=time_key,
    )
    if meal_time_warning(meal_type, eaten_at.isoformat(timespec="seconds")):
        st.warning(TR("simple_nutrition.time_warning"))

    # New meal/date combinations get isolated widget state, so inputs from a
    # previous meal cannot leak into the next one.
    editor_key = f"{record_key}_{meal_type}_{meal_date.isoformat()}"

    scanner_target_section = st.session_state.pop("supplement_ocr_switch_to_section", None)
    if scanner_target_section in {"supplement", "medication"}:
        st.session_state["simple_active_nutrition_section"] = scanner_target_section
    else:
        st.session_state.setdefault("simple_active_nutrition_section", "diet")
    draft_key = f"nutrition-entry-draft-{editor_key}"
    _render_active_nutrition_editor(
        existing, editor_key, eaten_at.isoformat(timespec="seconds"), draft_key,
    )
    draft = st.session_state.get(draft_key, {})
    active_section = draft.get(
        "active_section", st.session_state["simple_active_nutrition_section"],
    )
    food_items = draft.get("food_items", list((existing or {}).get("items", [])))
    supplements = draft.get("supplements", list((existing or {}).get("supplements", [])))

    action_title_html = (
        f'<div class="drc-meal-action-title">{escape(_ui("操作", "Actions"))}</div>'
    )
    _render_html(action_title_html)
    copy_actions, save_action = st.columns((2, 1))
    with copy_actions:
        _quick_actions(connection, existing, meal_type, meal_date, eaten_at, food_items, supplements)
    with save_action:
        complete = st.button(
            TR("simple_nutrition.save_meal"), type="primary", use_container_width=True,
        )
    if flash_key:
        st.success(TR(flash_key))

    # Notes remain intact on existing records, but are no longer part of the
    # nutrition-entry interface.
    existing_notes = (existing or {}).get("notes") or ""
    if complete:
        try:
            # Keep names entered in the editor available for future selection.
            # The current item remains unclassified until nutrition values are
            # supplied, so this never invents nutrient data.
            for item in food_items:
                if item.get("food_catalog_id") is None and item.get("custom_food_name"):
                    ensure_manual_food_option(
                        connection,
                        item["custom_food_name"],
                        item.get("item_type", "food"),
                    )
            connection.commit()
            action = save_meal_record if existing else create_meal_record
            meal = {
                "date": meal_date.isoformat(), "meal_type": meal_type,
                "eaten_at": eaten_at.isoformat(timespec="seconds"),
                "planned_meal_time": planned_time.isoformat(timespec="seconds"),
                "actual_meal_time": eaten_at.isoformat(timespec="seconds"),
                "status": "completed", "source": (existing or {}).get("source", "manual"),
                "notes": existing_notes,
            }
            if existing:
                record_id = action(connection, meal, food_items, supplements, existing["id"])
            else:
                record_id = action(connection, meal, food_items, supplements)
            # The weekly plan reads this saved meal directly for its matching
            # calendar date. Do not create a history-derived plan mirror:
            # the meal record remains the only source of actual intake.
            record_input_habit(
                connection,
                "nutrition.meal",
                fields=[
                    "food_items" if food_items else "",
                    "supplements" if supplements else "",
                    "planned_meal_time" if planned_time else "",
                    "actual_meal_time" if eaten_at else "",
                ],
                choices={
                    "nutrition.meal_type": meal_type,
                    "nutrition.category": active_section,
                },
                numeric={"nutrition.food_item_count": len(food_items)},
            )
            refresh_local_coach_for_date(meal_date.isoformat(), connection=connection)
            # Apply the active editor category before the next segmented
            # control is created. This keeps medication saves on Medication.
            st.session_state["simple_pending_nutrition_section"] = active_section
            st.session_state["simple_nutrition_advance_on_reentry"] = {
                "meal_type": meal_type,
                "date": meal_date.isoformat(),
            }
            _clear_editor_widget_state(editor_key)
            st.session_state["simple_meal_selector_pending"] = record_id
            st.session_state["simple_nutrition_flash"] = "simple_nutrition.saved"
            st.rerun()
        except Exception as exc:
            st.error(TR("manual_logging.submit_failed", message=str(exc)))

    return {
        "record_id": (existing or {}).get("id"),
        "meal_date": meal_date,
        "meal_type": meal_type,
        "food_items": food_items,
    }


def _daily_nutrition_summaries(records):
    """Build daily rollups once for the history table and selected-day view."""
    daily = {}
    for record in records:
        day = record["date"]
        source = record.get("summary") or {}
        bucket = daily.setdefault(day, {
            "food_count": 0,
            "identified_food_count": 0,
            **{metric: 0.0 for metric in METRICS},
            "known_metrics": set(),
        })
        for key in ("food_count", "identified_food_count"):
            bucket[key] += source.get(key) or 0
        for metric in METRICS:
            if source.get(metric) is not None:
                bucket[metric] += float(source[metric])
                bucket["known_metrics"].add(metric)
    for summary in daily.values():
        for metric in METRICS:
            if metric not in summary["known_metrics"]:
                summary[metric] = None
    return daily


def _historical_nutrition_row(day, summary):
    return {
        TR("nutrition_entry.date"): format_date(day, LANGUAGE),
        TR("simple_nutrition.recorded_count"): summary["food_count"],
        TR("simple_nutrition.identified_count"): summary["identified_food_count"],
        TR("simple_nutrition.calories"): _feedback_value("calories_kcal", summary["calories_kcal"]),
        TR("simple_nutrition.protein"): _feedback_value("protein_g", summary["protein_g"]),
        TR("simple_nutrition.carbohydrate"): _feedback_value("carbohydrate_g", summary["carbohydrate_g"]),
        TR("simple_nutrition.fat"): _feedback_value("fat_g", summary["fat_g"]),
        TR("simple_nutrition.fiber"): _feedback_value("fiber_g", summary["fiber_g"]),
        TR("simple_nutrition.water"): _feedback_value("water_ml", summary["water_ml"]),
    }


def _history(records):
    """Historical nutrition record table with the shared View interaction."""
    sections_open = st.session_state.get("nutrition_history_sections_open", False)
    with st.expander(TR("simple_nutrition.history"), expanded=sections_open):
        daily = _daily_nutrition_summaries(records)
        if not daily:
            st.info(TR("common.no_data"))
            return None, daily

        dates = sorted(daily, reverse=True)
        selected_date = st.session_state.get("nutrition_history_selected")
        if selected_date not in daily:
            selected_date = dates[0]
            st.session_state["nutrition_history_selected"] = selected_date
        rows = [_historical_nutrition_row(day, daily[day]) for day in dates]
        view_label = _ui("查看", "View")
        headers = list(rows[0]) + [_ui("操作", "Action")]
        widths = [1.05, .85, .95, .95, .95, 1.05, .8, .95, .9, .8]
        with st.container(height=430, border=True):
            header_columns = st.columns(widths)
            for column, label in zip(header_columns, headers):
                _render_html(
                    f'<div style="text-align:center;font-weight:600;">{escape(str(label))}</div>',
                    column,
                )
            for day, row in zip(dates, rows):
                columns = st.columns(widths, vertical_alignment="center")
                for column, label in zip(columns[:-1], headers[:-1]):
                    _render_html(
                        f'<div style="text-align:center;">{escape(str(row[label]))}</div>',
                        column,
                    )
                if columns[-1].button(
                    view_label, key=f"nutrition_history_view_{day}", use_container_width=True,
                ):
                    st.session_state["nutrition_history_selected"] = day
                    st.session_state["nutrition_history_details_visible"] = True
                    st.session_state["nutrition_history_sections_open"] = True
                    st.session_state["nutrition_history_focus_nonce"] = (
                        st.session_state.get("nutrition_history_focus_nonce", 0) + 1
                    )
                    st.rerun()
    return selected_date, daily


def _history_food_rows(record, item_type, catalog):
    rows = []
    for item in record.get("items", []):
        if item.get("item_type", "food") != item_type:
            continue
        catalog_item = catalog.get(item.get("food_catalog_id"))
        name = _display_food(catalog_item) if catalog_item else item.get("custom_food_name")
        rows.append({
            _ui("食物", "Food") if item_type == "food" else _ui("饮品", "Beverage"):
                name or TR("common.no_data"),
            TR("simple_nutrition.quantity"): _nutrition_number(item.get("quantity")),
            TR("simple_nutrition.unit"): TR(food_unit_label_key(item.get("unit") or "g")),
        })
    return rows


def _history_supplement_rows(record, product_kind, products_by_id):
    rows = []
    for item in record.get("supplements", []):
        if _stored_supplement_kind(item, products_by_id) != product_kind:
            continue
        rows.append({
            _ui("补剂类型", "Supplement Type") if product_kind == "supplement" else _ui("用药类型", "Medication Type"):
                item.get("product_name") or item.get("custom_product_name") or item.get("item_name") or TR("common.no_data"),
            TR("supplement_products.quantity"): _nutrition_number(item.get("quantity")),
            TR("supplement_products.unit"): TR(unit_label_key(item.get("unit") or "g")),
        })
    return rows


def _render_history_rows(rows, empty_text):
    if rows:
        centered_dataframe(rows, max_height="18rem")
    else:
        st.info(empty_text)


def _historical_nutrition_details(connection, records, selected_date):
    """Read-only historical counterpart of the current nutrition details."""
    def keep_history_sections_open():
        # A child control rerun should keep the selected history evidence open.
        st.session_state["nutrition_history_sections_open"] = True

    day_records = sorted(
        (item for item in records if item.get("date") == selected_date),
        key=lambda item: str(item.get("actual_meal_time") or item.get("eaten_at") or ""),
    )
    if not day_records:
        st.info(TR("common.no_data"))
        return

    record_by_id = {item["id"]: item for item in day_records}
    selected_meal_id = st.session_state.get(f"nutrition_history_detail_meal_{selected_date}")
    if selected_meal_id not in record_by_id:
        selected_meal_id = day_records[0]["id"]
        st.session_state[f"nutrition_history_detail_meal_{selected_date}"] = selected_meal_id
    selected_record = record_by_id[selected_meal_id]

    st.subheader(_ui("1. 饮食记录", "1. Food Record"))
    st.selectbox(
        TR("simple_nutrition.meal"),
        list(record_by_id),
        format_func=lambda record_id: _meal_name(record_by_id[record_id].get("meal_type")),
        key=f"nutrition_history_detail_meal_{selected_date}", on_change=keep_history_sections_open,
    )
    left, right = st.columns(2)
    left.text_input(
        TR("nutrition_entry.date"), value=format_date(selected_date, LANGUAGE),
        key=f"nutrition_history_detail_date_{selected_date}", disabled=True,
    )
    right.text_input(
        TR("simple_nutrition.actual_meal_time"),
        value=time_to_hms(selected_record.get("actual_meal_time") or selected_record.get("eaten_at")),
        key=f"nutrition_history_detail_time_{selected_date}_{selected_meal_id}", disabled=True,
    )

    section_options = ("diet", "supplement", "medication")
    section_labels = {
        "diet": _ui("🍽 饮食", "🍽 Diet"),
        "supplement": _ui("💊 补剂", "💊 Supplements"),
        "medication": _ui("用药", "Medication"),
    }
    section_key = f"nutrition_history_detail_section_{selected_date}_{selected_meal_id}"
    st.session_state.setdefault(section_key, "diet")
    active_section = st.segmented_control(
        _ui("分类", "Category"), section_options,
        format_func=lambda value: section_labels[value], selection_mode="single",
        key=section_key, label_visibility="collapsed", width="stretch",
        on_change=keep_history_sections_open,
    ) or "diet"

    if active_section == "diet":
        catalog = food_catalog_by_id(connection)
        _render_history_rows(
            _history_food_rows(selected_record, "food", catalog),
            _ui("本餐没有食物记录。", "No food recorded for this meal."),
        )
        _render_history_rows(
            _history_food_rows(selected_record, "beverage", catalog),
            _ui("本餐没有饮品记录。", "No beverages recorded for this meal."),
        )
    else:
        products_by_id = {str(item["id"]): item for item in list_products(connection)}
        _render_history_rows(
            _history_supplement_rows(selected_record, active_section, products_by_id),
            _ui("本餐没有补剂记录。", "No supplements recorded for this meal.")
            if active_section == "supplement" else
            _ui("本餐没有用药记录。", "No medication recorded for this meal."),
        )

    summary = selected_record.get("summary") or {}
    feedback_service = NutritionFeedbackService(records, selected_date, LANGUAGE)
    _render_meal_feedback(
        _nutrition_advice(
            connection, summary, recommended_nutrition_targets(connection), day=selected_date,
        ),
        selected_record.get("meal_type"), section_number=3,
    )
    _render_today_nutrition(
        records, selected_date, historical=True, section_number=2,
        targets=recommended_nutrition_targets(connection),
    )


def _historical_nutrition_situation(connection, records, *, auto_expand=False, focus_nonce=0):
    """Selected-day nutrition data and meal details, matching other domains."""
    data_title = _ui("历史营养数据", "Historical Nutrition Data")
    details_title = _ui("历史营养详情", "Historical Nutrition Details")

    # Historical records are the first child directory of the situation.
    selected_date, _ = _history(records)
    if not selected_date or not st.session_state.get("nutrition_history_details_visible", False):
        return

    sections_open = bool(auto_expand or st.session_state.get("nutrition_history_sections_open", False))
    with st.expander(data_title, expanded=sections_open):
        centered_dataframe([_nutrition_energy_row(records, selected_date)])

    with st.expander(details_title, expanded=sections_open):
        _historical_nutrition_details(connection, records, selected_date)

    if auto_expand:
        render_interaction_focus(
            components,
            target_expander_label=data_title,
            nonce=focus_nonce,
            top_offset=80,
        )


def _nutrition_energy_row(records, day):
    """The shared energy-balance data shape for today and historical dates."""
    metrics = get_day_metrics(day) or {}
    # An absent nutrition summary is not a zero-calorie intake.  Keeping it
    # as ``None`` prevents a misleading full-day calorie gap from appearing
    # before the user has any usable intake data.
    intake_values = []
    for record in records:
        if record.get("date") != day:
            continue
        value = (record.get("summary") or {}).get("calories_kcal")
        if value in (None, ""):
            continue
        try:
            intake_values.append(float(value))
        except (TypeError, ValueError):
            continue
    intake = sum(intake_values) if intake_values else None
    total_consumption = metrics.get("calories")
    # Keep this sign convention explicit for the table: total expenditure
    # minus total intake. Positive is a calorie gap; negative is a surplus.
    try:
        calorie_balance = (
            float(total_consumption) - intake
            if total_consumption not in (None, "") and intake is not None
            else None
        )
    except (TypeError, ValueError):
        calorie_balance = None
    balance_unavailable = intake is None
    surplus_text = (
        "N/A" if balance_unavailable
        else f"{abs(calorie_balance):.2f}" if calorie_balance is not None and calorie_balance < 0 else "—"
    )
    gap_text = (
        "N/A" if balance_unavailable
        else f"{calorie_balance:.2f}" if calorie_balance is not None and calorie_balance > 0 else "—"
    )
    return {
        _ui("摄入热量总值（kcal）", "Total Intake (kcal)"): f"{intake:g}" if intake is not None else TR("common.no_data"),
        _ui("运动消耗（kcal）", "Training Expenditure (kcal)"): _nutrition_number(metrics.get("training_calories")),
        _ui("静息消耗估计（kcal）", "Estimated Resting Expenditure (kcal)"): _nutrition_number(_polar_resting_calories(metrics)),
        _ui("活动消耗（kcal）", "Active Expenditure (kcal)"): _nutrition_number(metrics.get("active_calories")),
        _ui("总消耗（kcal）", "Total Expenditure (kcal)"): _nutrition_number(metrics.get("calories")),
        _ui("热量盈余（kcal）", "Calorie Surplus (kcal)"): surplus_text,
        _ui("热量缺口（kcal）", "Calorie Gap (kcal)"): gap_text,
    }


def _today_nutrition_table(records, day):
    st.subheader(TR("simple_nutrition.today_data"))
    centered_dataframe([_nutrition_energy_row(records, day)])


WEEKLY_RECIPE_AUTO_MARKER = "__nutrition_auto_recipe__"
WEEKLY_RECIPE_MANUAL_MARKER = "__nutrition_manual_recipe__"


def _weekly_recipe_marker(item):
    """Return the plan source and meal-type marker kept in an item's notes."""
    notes = str(item.get("notes") or "")
    for source, prefix in (
        ("manual", WEEKLY_RECIPE_MANUAL_MARKER),
        ("auto", WEEKLY_RECIPE_AUTO_MARKER),
    ):
        token = f"{prefix}:"
        if notes.startswith(token):
            return source, notes.removeprefix(token).split("|", 1)[0]
    return None, None


def _is_auto_generated_weekly_recipe_item(item):
    """Recognize legacy learned entries that were once saved with a manual marker."""
    normalized_item = dict(item or {})
    source, _ = _weekly_recipe_marker(normalized_item)
    if source == "auto":
        return True
    notes = str(normalized_item.get("notes") or "")
    return (
        _ui("根据历史输入自动生成", "Learned from meal history") in notes
        or "根据历史输入自动生成" in notes
        or "Learned from meal history" in notes
    )


def _weekly_recipe_notes(marker, notes, *, source):
    prefix = (
        WEEKLY_RECIPE_MANUAL_MARKER
        if source == "manual" else WEEKLY_RECIPE_AUTO_MARKER
    )
    detail = str(notes or "").strip()
    return f"{prefix}:{marker}|{detail}"


def _weekly_recipe_title(connection, record):
    """Turn a saved meal into a compact, copyable recipe title."""
    catalog = food_catalog_by_id(connection)
    labels = []
    for item in record.get("items", []):
        catalog_item = catalog.get(item.get("food_catalog_id"))
        name = _display_food(catalog_item) if catalog_item else item.get("custom_food_name")
        if not name:
            continue
        quantity = item.get("quantity")
        unit = item.get("unit") or ""
        amount = f" {quantity:g}{unit}" if isinstance(quantity, (int, float)) else ""
        labels.append(f"{name}{amount}")
    for item in record.get("supplements", []):
        name = item.get("product_name") or item.get("custom_product_name") or item.get("item_name")
        if name:
            quantity = item.get("quantity")
            unit = item.get("unit") or ""
            amount = f" {quantity:g}{unit}" if isinstance(quantity, (int, float)) else ""
            labels.append(f"{name}{amount}")
    if not labels:
        return _meal_name(record.get("meal_type"))
    return f"{_meal_name(record.get('meal_type'))}：" + "、".join(labels[:8])


def _weekly_recipe_time(record):
    start = _time_value(record.get("actual_meal_time") or record.get("eaten_at"))
    start_minutes = start.hour * 60 + start.minute
    end_minutes = min(start_minutes + 45, 23 * 60 + 59)
    return start, time(end_minutes // 60, end_minutes % 60)


NUTRITION_CYCLE_STATUSES = ("planned", "active", "completed", "archived")


def _cycle_end_date_for_weeks(start_date, duration_weeks):
    """Return the inclusive end date for a nutrition cycle in whole weeks."""
    weeks = int(duration_weeks)
    if weeks < 1 or weeks != float(duration_weeks):
        raise ValueError("INVALID_NUTRITION_CYCLE_DURATION")
    return start_date + timedelta(days=weeks * 7 - 1)


def _list_nutrition_plan_cycles(connection, *, include_archived=False):
    where = "" if include_archived else "WHERE status!='archived'"
    return [dict(row) for row in connection.execute(
        f"SELECT * FROM nutrition_plan_cycles {where} ORDER BY start_date DESC,id DESC"
    ).fetchall()]


def _current_nutrition_plan_cycle(connection, *, on_date=None):
    target = (on_date or date.today()).isoformat()
    row = connection.execute(
        """SELECT * FROM nutrition_plan_cycles
           WHERE status IN ('active','planned') AND start_date<=? AND end_date>=?
           ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,start_date DESC,id DESC
           LIMIT 1""",
        (target, target),
    ).fetchone()
    return dict(row) if row else None


def _create_nutrition_plan_cycle(connection, name, start_date, duration_weeks, *, notes=None):
    normalized_start = start_date - timedelta(days=start_date.weekday())
    end_date = _cycle_end_date_for_weeks(normalized_start, duration_weeks)
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("NUTRITION_CYCLE_NAME_REQUIRED")
    cursor = connection.execute(
        """INSERT INTO nutrition_plan_cycles(
               uuid,name,start_date,end_date,notes,status
           ) VALUES(?,?,?,?,?,'planned')""",
        (str(uuid4()), clean_name, normalized_start.isoformat(), end_date.isoformat(),
         str(notes or "").strip() or None),
    )
    connection.commit()
    return cursor.lastrowid


def _update_nutrition_plan_cycle(connection, cycle_id, start_date, duration_weeks, *, name=None):
    normalized_start = start_date - timedelta(days=start_date.weekday())
    end_date = _cycle_end_date_for_weeks(normalized_start, duration_weeks)
    clean_name = None if name is None else str(name).strip()
    if clean_name == "":
        raise ValueError("NUTRITION_CYCLE_NAME_REQUIRED")
    cursor = connection.execute(
        """UPDATE nutrition_plan_cycles
           SET name=COALESCE(?,name),start_date=?,end_date=?,updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (clean_name, normalized_start.isoformat(), end_date.isoformat(), cycle_id),
    )
    if not cursor.rowcount:
        raise ValueError("NUTRITION_CYCLE_NOT_FOUND")
    if clean_name is not None:
        connection.execute(
            """UPDATE user_weekly_plans
               SET title=?,updated_at=CURRENT_TIMESTAMP
               WHERE nutrition_cycle_id=? AND deleted_at IS NULL""",
            (clean_name, cycle_id),
        )
    connection.commit()
    return normalized_start, end_date


def _delete_nutrition_plan_cycle(connection, cycle_id):
    """Delete only the planned recipe content; actual meal records remain intact."""
    plan_rows = connection.execute(
        "SELECT plan_id FROM user_weekly_plans WHERE nutrition_cycle_id=?",
        (cycle_id,),
    ).fetchall()
    for row in plan_rows:
        connection.execute(
            "UPDATE user_weekly_plan_items SET deleted_at=CURRENT_TIMESTAMP WHERE plan_id=?",
            (row["plan_id"],),
        )
        connection.execute(
            "UPDATE user_weekly_plans SET deleted_at=CURRENT_TIMESTAMP WHERE plan_id=?",
            (row["plan_id"],),
        )
    cursor = connection.execute("DELETE FROM nutrition_plan_cycles WHERE id=?", (cycle_id,))
    if not cursor.rowcount:
        raise ValueError("NUTRITION_CYCLE_NOT_FOUND")
    connection.commit()


def _cycle_week_segment(cycle, *, on_date=None):
    """Return the displayed week within the chosen nutrition cycle."""
    start = date.fromisoformat(cycle["start_date"])
    end = date.fromisoformat(cycle["end_date"])
    target = on_date or date.today()
    if start <= target <= end:
        index = (target - start).days // 7 + 1
        week_start = target - timedelta(days=target.weekday())
    else:
        index = 1
        week_start = start
    return {"index": index, "week_start": week_start, "end_date": end}


def _nutrition_cycle_week_segments(cycle):
    """List the full-week plan segments belonging to a nutrition cycle."""
    start = date.fromisoformat(cycle["start_date"])
    end = date.fromisoformat(cycle["end_date"])
    week_count = max(1, (end - start).days // 7 + 1)
    return [
        {
            "index": index,
            "week_start": start + timedelta(days=(index - 1) * 7),
            "week_end": min(start + timedelta(days=index * 7 - 1), end),
        }
        for index in range(1, week_count + 1)
    ]


def _nutrition_cycle_week_selector(cycle, *, state_key, container=None):
    """Select a nutrition-plan week while defaulting to the current one."""
    segments = _nutrition_cycle_week_segments(cycle)
    if container is None:
        container = st
    options = [segment["index"] for segment in segments]
    current_segment = _cycle_week_segment(cycle)
    default_index = current_segment["index"] if current_segment["index"] in options else options[0]
    selected_index = st.session_state.get(state_key)
    if selected_index not in options:
        selected_index = default_index
        st.session_state[state_key] = selected_index
    chosen_index = container.selectbox(
        " ",
        options,
        index=options.index(selected_index),
        format_func=lambda index: _ui(
            f"{cycle['name']} · 第{index}周",
            f"{cycle['name']} · Week {index}",
        ),
        key=state_key,
        label_visibility="collapsed",
    )
    return next(segment for segment in segments if segment["index"] == chosen_index)


def _ensure_weekly_recipe_plan(connection, monday, *, cycle_id=None, title=None):
    row = connection.execute(
        """SELECT plan_id,nutrition_cycle_id FROM user_weekly_plans
           WHERE week_start=? AND deleted_at IS NULL""",
        (monday.isoformat(),),
    ).fetchone()
    if row:
        if cycle_id is not None and row["nutrition_cycle_id"] != cycle_id:
            connection.execute(
                "UPDATE user_weekly_plans SET nutrition_cycle_id=?,updated_at=CURRENT_TIMESTAMP WHERE plan_id=?",
                (cycle_id, row["plan_id"]),
            )
        return row["plan_id"]
    plan_id = str(uuid4())
    connection.execute(
        """INSERT INTO user_weekly_plans(
               plan_id, week_start, title, timezone, nutrition_cycle_id
           ) VALUES(?, ?, ?, ?, ?)""",
        (plan_id, monday.isoformat(), title or _ui("周期性饮食计划", "Recurring Nutrition Plan"),
         "local", cycle_id),
    )
    return plan_id


def _save_weekly_recipe_item(
    connection, plan_id, weekday, title, start_time, end_time, *, notes=None, marker=None,
    source="manual", existing_item_id=None,
):
    """Persist one user-authored weekly meal-plan cell."""
    normalized_notes = str(notes or "").strip() or None
    if marker:
        marker_prefix = (
            WEEKLY_RECIPE_MANUAL_MARKER
            if source == "manual" else WEEKLY_RECIPE_AUTO_MARKER
        )
        note_prefix = f"{marker_prefix}:{marker}|"
        normalized_notes = _weekly_recipe_notes(marker, normalized_notes, source=source)
        existing = None
        if source == "auto":
            # A user-edited cell is an explicit preference: automatic learning
            # must not replace it on each rendering of the page.
            manual = connection.execute(
                """SELECT item_id FROM user_weekly_plan_items
                   WHERE plan_id=? AND weekday=? AND category='meal'
                     AND deleted_at IS NULL AND notes LIKE ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (plan_id, weekday, f"{WEEKLY_RECIPE_MANUAL_MARKER}:{marker}|%"),
            ).fetchone()
            if manual:
                return manual["item_id"]
        if existing_item_id:
            existing = connection.execute(
                """SELECT item_id, title, start_time, end_time, notes FROM user_weekly_plan_items
                   WHERE item_id=? AND plan_id=? AND deleted_at IS NULL""",
                (existing_item_id, plan_id),
            ).fetchone()
        if existing is None:
            existing = connection.execute(
                """SELECT item_id, title, start_time, end_time, notes FROM user_weekly_plan_items
                   WHERE plan_id=? AND weekday=? AND category='meal'
                     AND deleted_at IS NULL AND notes LIKE ?
                   ORDER BY updated_at DESC LIMIT 1""",
                (plan_id, weekday, f"{note_prefix}%"),
            ).fetchone()
        if existing:
            start_text = start_time.strftime("%H:%M")
            end_text = end_time.strftime("%H:%M")
            if (
                existing["title"] != title
                or existing["start_time"] != start_text
                or existing["end_time"] != end_text
                or existing["notes"] != normalized_notes
            ):
                connection.execute(
                    """UPDATE user_weekly_plan_items
                       SET weekday=?, title=?, start_time=?, end_time=?, notes=?, updated_at=CURRENT_TIMESTAMP
                       WHERE item_id=? AND deleted_at IS NULL""",
                    (weekday, title, start_text, end_text, normalized_notes, existing["item_id"]),
                )
            return existing["item_id"]
    next_order = connection.execute(
        """SELECT COALESCE(MAX(sort_order), -1) + 1
           FROM user_weekly_plan_items WHERE plan_id=? AND weekday=?""",
        (plan_id, weekday),
    ).fetchone()[0]
    item_id = str(uuid4())
    connection.execute(
        """INSERT INTO user_weekly_plan_items(
               item_id, plan_id, weekday, title, start_time, end_time,
               category, notes, sort_order
           ) VALUES(?, ?, ?, ?, ?, ?, 'meal', ?, ?)""",
        (
            item_id, plan_id, weekday, title, start_time.strftime("%H:%M"),
            end_time.strftime("%H:%M"), normalized_notes, next_order,
        ),
    )
    return item_id


def _sync_actual_meal_to_weekly_recipe(connection, record_id):
    """Keep a saved meal represented in its week's recipe automatically."""
    record = get_meal_record(connection, record_id)
    if not record or (not record.get("items") and not record.get("supplements")):
        return
    meal_date = date.fromisoformat(record["date"])
    monday = meal_date - timedelta(days=meal_date.weekday())
    cycle = _current_nutrition_plan_cycle(connection, on_date=meal_date)
    plan_id = _ensure_weekly_recipe_plan(
        connection, monday,
        cycle_id=cycle["id"] if cycle else None,
        title=cycle["name"] if cycle else None,
    )
    start_time, end_time = _weekly_recipe_time(record)
    _save_weekly_recipe_item(
        connection, plan_id, meal_date.weekday(), _weekly_recipe_title(connection, record),
        start_time, end_time, notes=record.get("notes"), marker=record.get("meal_type"), source="auto",
    )
    connection.commit()


def _learn_weekly_recipe(connection, records, monday, *, cycle_id=None, cycle_title=None):
    """Build a real weekly recipe from the user's recurring meal history."""
    cutoff = monday - timedelta(days=56)
    candidates = [
        item for item in records
        if item.get("status", "completed") == "completed"
        and item.get("date")
        and cutoff <= date.fromisoformat(item["date"]) < monday
    ]
    if not candidates:
        candidates = [item for item in records if item.get("items") or item.get("supplements")]
    grouped = {}
    for record in candidates:
        key = (date.fromisoformat(record["date"]).weekday(), record.get("meal_type"))
        title = _weekly_recipe_title(connection, record)
        bucket = grouped.setdefault(key, {})
        entry = bucket.setdefault(title, {"count": 0, "record": record})
        entry["count"] += 1
        if record.get("date", "") > entry["record"].get("date", ""):
            entry["record"] = record
    created = 0
    plan_id = _ensure_weekly_recipe_plan(
        connection, monday, cycle_id=cycle_id, title=cycle_title,
    )
    for (weekday, meal_type), choices in grouped.items():
        best = max(choices.values(), key=lambda value: (value["count"], value["record"].get("date", "")))
        record = best["record"]
        start_time, end_time = _weekly_recipe_time(record)
        _save_weekly_recipe_item(
            connection, plan_id, weekday, _weekly_recipe_title(connection, record),
            start_time, end_time, notes=_ui("根据历史输入自动生成", "Learned from meal history"),
            marker=meal_type or "meal",
        )
        created += 1
    connection.commit()
    return created


def _copy_previous_recipe_week(connection, plan_id, monday, cycle_id):
    """Copy user-authored nutrition-plan cells from the preceding week."""
    source = connection.execute(
        """SELECT plan_id FROM user_weekly_plans
           WHERE week_start=? AND nutrition_cycle_id=? AND deleted_at IS NULL""",
        ((monday - timedelta(days=7)).isoformat(), cycle_id),
    ).fetchone()
    if not source:
        return 0
    source_items = connection.execute(
        """SELECT weekday,title,start_time,end_time,notes,sort_order
           FROM user_weekly_plan_items
           WHERE plan_id=? AND category='meal' AND deleted_at IS NULL
             AND notes LIKE ?
           ORDER BY weekday,start_time,sort_order,created_at""",
        (source["plan_id"], f"{WEEKLY_RECIPE_MANUAL_MARKER}%"),
    ).fetchall()
    existing = {
        (row["weekday"], row["title"], row["start_time"], row["end_time"], row["notes"])
        for row in connection.execute(
            """SELECT weekday,title,start_time,end_time,notes
               FROM user_weekly_plan_items
               WHERE plan_id=? AND category='meal' AND deleted_at IS NULL""",
            (plan_id,),
        ).fetchall()
    }
    copied = 0
    for item in source_items:
        if _is_auto_generated_weekly_recipe_item(item):
            continue
        signature = (item["weekday"], item["title"], item["start_time"], item["end_time"], item["notes"])
        if signature in existing:
            continue
        next_order = connection.execute(
            """SELECT COALESCE(MAX(sort_order), -1) + 1
               FROM user_weekly_plan_items WHERE plan_id=? AND weekday=?""",
            (plan_id, item["weekday"]),
        ).fetchone()[0]
        connection.execute(
            """INSERT INTO user_weekly_plan_items(
                   item_id,plan_id,weekday,title,start_time,end_time,category,notes,sort_order
               ) VALUES(?,?,?,?,?,?,'meal',?,?)""",
            (str(uuid4()), plan_id, item["weekday"], item["title"], item["start_time"],
             item["end_time"], item["notes"], next_order),
        )
        existing.add(signature)
        copied += 1
    connection.commit()
    return copied


def _weekly_recipe_payload(item):
    """Read structured plan content while keeping legacy manual titles intact."""
    notes = str((item or {}).get("notes") or "")
    detail = notes.split("|", 1)[1] if "|" in notes else ""
    try:
        payload = json.loads(detail)
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict) and payload.get("version") == 1:
        return {
            "items": list(payload.get("items") or []),
            "supplements": list(payload.get("supplements") or []),
            "notes": str(payload.get("notes") or ""),
            "legacy_title": str(payload.get("legacy_title") or ""),
        }
    return {
        "items": [], "supplements": [], "notes": detail,
        "legacy_title": str((item or {}).get("title") or ""),
    }


def _weekly_recipe_quantity_text(quantity, unit):
    try:
        return f"{float(quantity):g}{unit or ''}"
    except (TypeError, ValueError):
        return str(unit or "")


def _weekly_recipe_payload_labels(connection, payload):
    """Return each structured plan item as an independent display label."""
    food_by_id = food_catalog_by_id(connection)
    products_by_id = {str(product["id"]): product for product in list_products(connection)}
    labels = []
    for item in payload.get("items", []):
        catalog = food_by_id.get(item.get("food_catalog_id"))
        name = _display_food(catalog) if catalog else str(item.get("custom_food_name") or "").strip()
        if name:
            labels.append(f"{name} {_weekly_recipe_quantity_text(item.get('quantity'), item.get('unit'))}".strip())
    for item in payload.get("supplements", []):
        product = products_by_id.get(str(item.get("supplement_product_id")))
        name = (product or {}).get("product_name") or str(item.get("custom_product_name") or "").strip()
        if name:
            labels.append(f"{name} {_weekly_recipe_quantity_text(item.get('quantity'), item.get('unit'))}".strip())
    return labels


def _weekly_recipe_payload_title(connection, payload):
    """Create the compact persisted title from structured planned items."""
    labels = _weekly_recipe_payload_labels(connection, payload)
    return "、".join(labels) or str(payload.get("legacy_title") or "").strip()


def _weekly_recipe_plan_cell_text(connection, item):
    """Format plan cells with standalone times and one item per visual line."""
    payload = _weekly_recipe_payload(item)
    labels = _weekly_recipe_payload_labels(connection, payload)
    if labels:
        start_time = str(item.get("start_time") or "").strip()
        end_time = str(item.get("end_time") or "").strip()
        time_line = "–".join(value for value in (start_time, end_time) if value)
        return "\n".join(([time_line] if time_line else []) + [f"· {label}" for label in labels])

    # Legacy records contain a free-text meal plan such as
    # ``07:30：燕麦75g、希腊酸奶150g``.  Preserve every timestamp as a
    # heading and make every individual food its own bulleted line.
    legacy = str(payload.get("legacy_title") or item.get("title") or "").strip()
    lines = []
    for raw_line in legacy.splitlines() or [legacy]:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        time_match = re.match(r"^(\d{1,2}:\d{2})\s*[：:]\s*(.*)$", raw_line)
        if time_match:
            lines.append(time_match.group(1))
            raw_line = time_match.group(2).strip()
        lines.extend(
            f"· {part.strip()}"
            for part in re.split(r"[、，,；;]+", raw_line)
            if part.strip()
        )
    return "\n".join(lines)


def _weekly_recipe_editor_state(connection, payload, editor_key):
    """Initialize a plan editor's local row state from its saved payload."""
    initialized_key = f"nutrition_recipe_editor_initialized_{editor_key}"
    if st.session_state.get(initialized_key):
        return
    food_rows = list(payload.get("items") or []) or [{}]
    st.session_state[f"nutrition_recipe_food_rows_{editor_key}"] = list(range(1, len(food_rows) + 1))
    for row_id, item in enumerate(food_rows, start=1):
        catalog = food_catalog_by_id(connection).get(item.get("food_catalog_id"))
        st.session_state[f"nutrition_recipe_food_name_{editor_key}_{row_id}"] = (
            _display_food(catalog) if catalog else str(item.get("custom_food_name") or "")
        )
        st.session_state[f"nutrition_recipe_food_quantity_{editor_key}_{row_id}"] = item.get("quantity")
        st.session_state[f"nutrition_recipe_food_unit_{editor_key}_{row_id}"] = item.get("unit") or "g"
    for kind in ("supplement", "medication"):
        saved_rows = [
            item for item in payload.get("supplements", [])
            if item.get("product_kind", "supplement") == kind
        ] or [{}]
        st.session_state[f"nutrition_recipe_{kind}_rows_{editor_key}"] = list(range(1, len(saved_rows) + 1))
        products_by_id = {str(product["id"]): product for product in list_products(connection)}
        for row_id, item in enumerate(saved_rows, start=1):
            product = products_by_id.get(str(item.get("supplement_product_id")))
            st.session_state[f"nutrition_recipe_{kind}_name_{editor_key}_{row_id}"] = (
                (product or {}).get("product_name") or str(item.get("custom_product_name") or "")
            )
            st.session_state[f"nutrition_recipe_{kind}_quantity_{editor_key}_{row_id}"] = item.get("quantity")
            st.session_state[f"nutrition_recipe_{kind}_unit_{editor_key}_{row_id}"] = item.get("unit") or "g"
    st.session_state[f"nutrition_recipe_notes_{editor_key}"] = payload.get("notes") or ""
    st.session_state[initialized_key] = True


def _render_weekly_recipe_plan_inputs(connection, payload, editor_key):
    """Render plan inputs with the same category and quantity model as intake."""
    _weekly_recipe_editor_state(connection, payload, editor_key)
    section_key = f"nutrition_recipe_editor_section_{editor_key}"
    st.session_state.setdefault(section_key, "diet")
    section = st.segmented_control(
        _ui("分类", "Category"), ("diet", "supplement", "medication"),
        format_func=lambda value: {
            "diet": _ui("🍽 饮食", "🍽 Diet"),
            "supplement": _ui("💊 补剂", "💊 Supplements"),
            "medication": _ui("用药", "Medication"),
        }[value],
        selection_mode="single", key=section_key, label_visibility="collapsed", width="stretch",
    ) or "diet"
    if section == "diet":
        catalog_items = list_food_catalog(connection)
        by_display_name = {
            name: item for item in catalog_items
            for name in (item["canonical_name"], item["display_name_zh"], item["display_name_en"], _display_food(item))
            if name
        }
        recent_names = [
            _display_food(item.get("catalog")) if item.get("catalog") else item.get("custom_food_name")
            for item in recent_foods(connection)
        ]
        catalog_names = [_display_food(item) for item in catalog_items]
        options = [""] + list(dict.fromkeys(name for name in recent_names + catalog_names if name))
        row_ids_key = f"nutrition_recipe_food_rows_{editor_key}"
        columns = st.columns((2.0, 1.0, .8, .8))
        for column, label in zip(columns, (_ui("食物/饮品", "Food / Beverage"), TR("simple_nutrition.quantity"), TR("simple_nutrition.unit"), TR("simple_nutrition.actions"))):
            column.markdown(_cell(label), unsafe_allow_html=True)
        for row_id in list(st.session_state[row_ids_key]):
            row = st.columns((2.0, 1.0, .8, .8))
            name_key = f"nutrition_recipe_food_name_{editor_key}_{row_id}"
            quantity_key = f"nutrition_recipe_food_quantity_{editor_key}_{row_id}"
            unit_key = f"nutrition_recipe_food_unit_{editor_key}_{row_id}"
            name = row[0].selectbox(
                _ui("食物/饮品", "Food / Beverage"), options,
                key=name_key, label_visibility="collapsed", accept_new_options=True,
                placeholder=_ui("选择或输入食物/饮品", "Select or enter food or beverage"),
            ) or ""
            catalog = by_display_name.get(name)
            units = list(allowed_food_units(catalog))
            if st.session_state.get(unit_key) not in units:
                st.session_state[unit_key] = (catalog or {}).get("default_unit") or units[0]
            row[1].number_input(TR("simple_nutrition.quantity"), min_value=.01, step=.1, key=quantity_key, label_visibility="collapsed")
            row[2].selectbox(TR("simple_nutrition.unit"), units, key=unit_key, format_func=lambda value: TR(food_unit_label_key(value)), label_visibility="collapsed")
            if row[3].button(TR("simple_nutrition.delete_row"), key=f"nutrition_recipe_delete_food_{editor_key}_{row_id}", use_container_width=True):
                st.session_state[row_ids_key].remove(row_id)
                st.rerun()
        add_row = st.columns((2.0, 1.0, .8, .8))
        if add_row[0].button(
            _ui("添加食物/饮品", "Add Food / Beverage"),
            key=f"nutrition_recipe_add_food_{editor_key}",
            use_container_width=True,
        ):
            next_id = max(st.session_state[row_ids_key], default=0) + 1
            st.session_state[row_ids_key].append(next_id)
            st.session_state[f"nutrition_recipe_food_name_{editor_key}_{next_id}"] = ""
            st.session_state[f"nutrition_recipe_food_quantity_{editor_key}_{next_id}"] = None
            st.session_state[f"nutrition_recipe_food_unit_{editor_key}_{next_id}"] = "g"
            st.rerun()
    else:
        product_kind = "supplement" if section == "supplement" else "medication"
        products = [product for product in list_products(connection) if product.get("product_kind") == product_kind]
        by_name = {product["product_name"]: product for product in products if product.get("product_name")}
        options = [""] + list(dict.fromkeys([product["product_name"] for product in products if product.get("product_name")]))
        row_ids_key = f"nutrition_recipe_{product_kind}_rows_{editor_key}"
        columns = st.columns((2.0, 1.0, .8, .8))
        type_label = _ui("补剂类型", "Supplement Type") if product_kind == "supplement" else _ui("药物类型", "Medication Type")
        for column, label in zip(columns, (type_label, TR("supplement_products.quantity"), TR("supplement_products.unit"), TR("supplement_products.actions"))):
            column.markdown(_cell(label), unsafe_allow_html=True)
        for row_id in list(st.session_state[row_ids_key]):
            row = st.columns((2.0, 1.0, .8, .8))
            name_key = f"nutrition_recipe_{product_kind}_name_{editor_key}_{row_id}"
            quantity_key = f"nutrition_recipe_{product_kind}_quantity_{editor_key}_{row_id}"
            unit_key = f"nutrition_recipe_{product_kind}_unit_{editor_key}_{row_id}"
            name = row[0].selectbox(type_label, options, key=name_key, label_visibility="collapsed", accept_new_options=True, placeholder=_ui("选择或输入补剂类型" if product_kind == "supplement" else "选择或输入药物类型", "Select or enter supplement" if product_kind == "supplement" else "Select or enter medication")) or ""
            product = by_name.get(name)
            if st.session_state.get(unit_key) not in SUPPLEMENT_UNITS:
                st.session_state[unit_key] = (product or {}).get("default_intake_unit") or "g"
            row[1].number_input(TR("supplement_products.quantity"), min_value=.01, step=.1, key=quantity_key, label_visibility="collapsed")
            row[2].selectbox(TR("supplement_products.unit"), SUPPLEMENT_UNITS, key=unit_key, format_func=lambda value: TR(unit_label_key(value)), label_visibility="collapsed")
            if row[3].button(TR("simple_nutrition.delete_row"), key=f"nutrition_recipe_delete_{product_kind}_{editor_key}_{row_id}", use_container_width=True):
                st.session_state[row_ids_key].remove(row_id)
                st.rerun()
        add_row = st.columns((2.0, 1.0, .8, .8))
        if add_row[0].button(
            _ui("添加补剂", "Add Supplement") if product_kind == "supplement" else _ui("添加用药", "Add Medication"),
            key=f"nutrition_recipe_add_{product_kind}_{editor_key}",
            use_container_width=True,
        ):
            next_id = max(st.session_state[row_ids_key], default=0) + 1
            st.session_state[row_ids_key].append(next_id)
            st.session_state[f"nutrition_recipe_{product_kind}_name_{editor_key}_{next_id}"] = ""
            st.session_state[f"nutrition_recipe_{product_kind}_quantity_{editor_key}_{next_id}"] = None
            st.session_state[f"nutrition_recipe_{product_kind}_unit_{editor_key}_{next_id}"] = "g"
            st.rerun()
    return section


def _weekly_recipe_editor_payload_from_state(connection, payload, editor_key):
    """Collect all three plan categories, including inactive segmented sections."""
    catalog_items = list_food_catalog(connection)
    by_display_name = {
        name: item for item in catalog_items
        for name in (item["canonical_name"], item["display_name_zh"], item["display_name_en"], _display_food(item))
        if name
    }
    items = []
    for row_id in st.session_state.get(f"nutrition_recipe_food_rows_{editor_key}", []):
        name = str(st.session_state.get(f"nutrition_recipe_food_name_{editor_key}_{row_id}") or "").strip()
        quantity = st.session_state.get(f"nutrition_recipe_food_quantity_{editor_key}_{row_id}")
        if not name or quantity in (None, ""):
            continue
        catalog = by_display_name.get(name)
        items.append({
            "food_catalog_id": catalog["id"] if catalog else None,
            "custom_food_name": None if catalog else name,
            "item_type": "beverage" if catalog and "beverage" in catalog["category_tags"] else "food",
            "quantity": quantity,
            "unit": st.session_state.get(f"nutrition_recipe_food_unit_{editor_key}_{row_id}") or "g",
        })
    supplements = []
    for kind in ("supplement", "medication"):
        products = {
            product["product_name"]: product for product in list_products(connection)
            if product.get("product_name") and product.get("product_kind") == kind
        }
        for row_id in st.session_state.get(f"nutrition_recipe_{kind}_rows_{editor_key}", []):
            name = str(st.session_state.get(f"nutrition_recipe_{kind}_name_{editor_key}_{row_id}") or "").strip()
            quantity = st.session_state.get(f"nutrition_recipe_{kind}_quantity_{editor_key}_{row_id}")
            if not name or quantity in (None, ""):
                continue
            product = products.get(name)
            supplements.append({
                "supplement_product_id": product["id"] if product else None,
                "custom_product_name": None if product else name,
                "product_kind": kind,
                "quantity": quantity,
                "unit": st.session_state.get(f"nutrition_recipe_{kind}_unit_{editor_key}_{row_id}") or "g",
            })
    return {
        "version": 1, "items": items, "supplements": supplements,
        "notes": str(st.session_state.get(f"nutrition_recipe_notes_{editor_key}") or "").strip(),
        "legacy_title": payload.get("legacy_title") or "",
    }


def _render_weekly_recipe(connection, records):
    """Render the user-authored weekly nutrition cycle and its plan table.

    This intentionally mirrors the strength-plan hierarchy: a compact cycle
    directory leads to an editable plan table. Its contents are always saved
    separately from actual dietary records and are entered by the user.
    """
    cycles = _list_nutrition_plan_cycles(connection)
    cycle_options = [None] + [cycle["id"] for cycle in cycles]

    def _cycle_option_label(value):
        if value is None:
            return _ui("请选择或输入饮食周期", "Select or enter a nutrition cycle")
        matched_cycle = next((cycle for cycle in cycles if cycle["id"] == value), None)
        return matched_cycle["name"] if matched_cycle else str(value)
    requested_cycle = st.session_state.pop("nutrition_cycle_requested_selection", None)
    if requested_cycle in cycle_options:
        st.session_state["nutrition_cycle_filter"] = requested_cycle
    current_cycle = _current_nutrition_plan_cycle(connection)
    current_cycle_id = current_cycle["id"] if current_cycle else None
    selected_cycle_state = st.session_state.get("nutrition_cycle_filter")
    if current_cycle_id and selected_cycle_state in (None, ""):
        st.session_state["nutrition_cycle_filter"] = current_cycle_id
    elif selected_cycle_state not in cycle_options:
        st.session_state["nutrition_cycle_filter"] = current_cycle_id

    keep_plan_table_open = bool(
        st.session_state.pop("nutrition_weekly_recipe_keep_table_open", False)
    )
    cycle_open = (
        bool(st.session_state.get("nutrition_weekly_recipe_edit_slot"))
        or keep_plan_table_open
    )
    cycle_notice = st.session_state.pop("nutrition_weekly_recipe_cycle_notice", None)
    selected_cycle_record = None
    cycle_expander = st.expander(
        _ui("周期性饮食", "Cyclical Nutrition"), expanded=cycle_open,
    )
    with cycle_expander:
        if cycle_notice:
            st.success(cycle_notice)
        selected_cycle = st.selectbox(
            _ui("饮食周期", "Nutrition Cycle"), cycle_options,
            format_func=_cycle_option_label,
            key="nutrition_cycle_filter", label_visibility="hidden",
            accept_new_options=True,
            placeholder=_ui("请选择或输入饮食周期", "Select or enter a nutrition cycle"),
        )
        selected_cycle_record = next(
            (cycle for cycle in cycles if cycle["id"] == selected_cycle), None,
        )
        custom_cycle_name = (
            str(selected_cycle).strip()
            if selected_cycle not in cycle_options and str(selected_cycle or "").strip()
            else ""
        )
        if (
            custom_cycle_name
            and st.session_state.get("nutrition_cycle_custom_name_prefill") != custom_cycle_name
        ):
            # A newly typed selector value should seed the creation form once,
            # without overwriting later edits to the cycle name itself.
            st.session_state["nutrition_new_cycle_name"] = custom_cycle_name
            st.session_state["nutrition_cycle_custom_name_prefill"] = custom_cycle_name
        show_cycle_creator = (
            st.session_state.get("nutrition_show_create_cycle", False)
            or bool(custom_cycle_name)
        )
        if selected_cycle_record:
            cycle_start = date.fromisoformat(selected_cycle_record["start_date"])
            cycle_end = date.fromisoformat(selected_cycle_record["end_date"])
            duration_weeks = (cycle_end - cycle_start).days // 7 + 1
            _render_html('<span class="drc-recipe-cycle-settings-marker"></span>')
            edited_name = st.text_input(
                _ui("周期名称", "Cycle Name"),
                value=selected_cycle_record["name"],
                key=f"nutrition_cycle_name_{selected_cycle}",
            )
            cycle_columns = st.columns(3, vertical_alignment="top")
            edited_start = cycle_columns[0].date_input(
                _ui("开始日期", "Start Date"), value=cycle_start,
                key=f"nutrition_cycle_start_{selected_cycle}",
            )
            edited_duration_weeks = cycle_columns[1].number_input(
                _ui("持续周数", "Duration (weeks)"), min_value=1, max_value=52,
                value=duration_weeks, step=1, format="%d",
                key=f"nutrition_cycle_duration_weeks_{selected_cycle}",
            )
            edited_end = _cycle_end_date_for_weeks(edited_start, edited_duration_weeks)
            cycle_columns[2].text_input(
                _ui("结束日期", "End Date"),
                value=edited_end.strftime("%Y/%m/%d"),
                key=f"nutrition_cycle_end_{selected_cycle}_{edited_end.isoformat()}",
                disabled=True,
            )
            segment = _cycle_week_segment(selected_cycle_record)
            cycle_details_directory = st.expander(
                _ui("查看详情", "View Details"), expanded=cycle_open,
            )
            confirm_delete = st.checkbox(
                _ui("确认删除此周期及其计划内容", "Confirm deleting this cycle and its planned content"),
                key=f"nutrition_confirm_delete_cycle_{selected_cycle}",
            )
            actions = st.columns(4)
            if actions[0].button(
                _ui("删除周期", "Delete Cycle"),
                key="nutrition_delete_cycle", disabled=not confirm_delete,
            ):
                _delete_nutrition_plan_cycle(connection, selected_cycle)
                st.session_state.pop("nutrition_weekly_recipe_edit_slot", None)
                st.session_state["nutrition_weekly_recipe_cycle_notice"] = _ui(
                    "饮食周期及其计划内容已删除；实际饮食记录未受影响。",
                    "The nutrition cycle and its planned content were deleted; actual dietary records were unchanged.",
                )
                st.rerun()
            if actions[1].button(
                _ui("复制上周饮食内容", "Copy Previous Week's Meals"),
                key="nutrition_copy_previous_week",
            ):
                target_plan_id = _ensure_weekly_recipe_plan(
                    connection, segment["week_start"], cycle_id=selected_cycle,
                    title=selected_cycle_record["name"],
                )
                copied = _copy_previous_recipe_week(
                    connection, target_plan_id, segment["week_start"], selected_cycle,
                )
                st.session_state["nutrition_weekly_recipe_cycle_notice"] = _ui(
                    f"已复制上周饮食内容：新增 {copied} 项。" if copied else "上周没有可复制的饮食计划内容。",
                    f"Copied {copied} meal-plan item(s) from last week." if copied else "There is no meal-plan content to copy from last week.",
                )
                st.rerun()
            if actions[2].button(
                _ui("创建周期", "Create Cycle"), key="nutrition_open_cycle_creator",
            ):
                st.session_state["nutrition_show_create_cycle"] = True
                st.rerun()
            if actions[3].button(
                _ui("保存修改", "Save Changes"), key=f"nutrition_save_cycle_{selected_cycle}",
                type="primary",
            ):
                try:
                    saved_start, _ = _update_nutrition_plan_cycle(
                        connection, selected_cycle, edited_start, edited_duration_weeks,
                        name=edited_name,
                    )
                except ValueError as exc:
                    if str(exc) == "NUTRITION_CYCLE_NAME_REQUIRED":
                        st.error(_ui("请填写周期名称。", "Enter a cycle name."))
                    else:
                        st.error(str(exc))
                    return
                message = _ui("周期修改已保存。", "Cycle changes saved.")
                if saved_start != edited_start:
                    message += _ui(
                        f" 开始日期已按所在周的周一保存：{saved_start.strftime('%Y/%m/%d')}。",
                        f" The start date was saved as that week's Monday: {saved_start.strftime('%Y/%m/%d')}.",
                    )
                st.session_state["nutrition_weekly_recipe_cycle_notice"] = message
                st.rerun()
        else:
            st.info(_ui("请选择或创建一个饮食周期。", "Select or create a nutrition cycle."))
            if st.button(_ui("创建周期", "Create Cycle"), key="nutrition_open_cycle_creator_empty"):
                st.session_state["nutrition_show_create_cycle"] = True
                st.rerun()

        if show_cycle_creator:
            st.markdown(f'<div class="drc-cycle-section-title">{escape(_ui("创建周期", "Create Cycle"))}</div>', unsafe_allow_html=True)
            new_name = st.text_input(
                _ui("周期名称", "Cycle Name"),
                value=custom_cycle_name or _ui("适应期", "Adaptation Phase"),
                key="nutrition_new_cycle_name",
            )
            new_fields = st.columns(3, vertical_alignment="top")
            new_start = new_fields[0].date_input(
                _ui("开始日期", "Start Date"), value=date.today(), key="nutrition_new_cycle_start",
            )
            new_duration = new_fields[1].number_input(
                _ui("持续周数", "Duration (weeks)"), min_value=1, max_value=52, value=1,
                step=1, format="%d", key="nutrition_new_cycle_duration_weeks",
            )
            new_end = _cycle_end_date_for_weeks(new_start, new_duration)
            new_fields[2].text_input(
                _ui("结束日期", "End Date"),
                value=new_end.strftime("%Y/%m/%d"),
                key=f"nutrition_new_cycle_end_{new_end.isoformat()}",
                disabled=True,
            )
            if st.button(_ui("创建周期", "Create Cycle"), key="nutrition_create_cycle", type="primary"):
                try:
                    new_cycle_id = _create_nutrition_plan_cycle(
                        connection, new_name, new_start, new_duration,
                    )
                    st.session_state["nutrition_show_create_cycle"] = False
                    st.session_state["nutrition_cycle_requested_selection"] = new_cycle_id
                    st.session_state["nutrition_weekly_recipe_cycle_notice"] = _ui("饮食周期已创建。", "Nutrition cycle created.")
                    st.rerun()
                except ValueError:
                    st.error(_ui("请填写有效的周期名称和持续周数。", "Enter a valid cycle name and duration."))

        _render_html(
            '<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
            'color:var(--text-color);opacity:.62;font-size:.875rem;line-height:1.5;">'
            + escape(_ui(
                "计划内容由你手动填写；计划内容与实际饮食记录分开保存。",
                "Plan contents are entered manually and are stored separately from actual dietary records.",
            ))
            + "</div>",
        )

    if not selected_cycle_record:
        return
    # Match the strength-cycle hierarchy: the plan table is the content of
    # “View Details”, not an additional sibling or nested plan directory.
    cycle_details_directory.__enter__()
    try:
        segment = _nutrition_cycle_week_selector(
            selected_cycle_record,
            state_key=f"nutrition_cycle_week_{selected_cycle_record['id']}",
            container=cycle_details_directory,
        )
        monday = segment["week_start"]
        plan_id = _ensure_weekly_recipe_plan(
            connection, monday, cycle_id=selected_cycle_record["id"], title=selected_cycle_record["name"],
        )
        connection.commit()

        recipe_items = [
            dict(item) for item in connection.execute(
                """SELECT item_id, weekday, title, start_time, end_time, notes
                   FROM user_weekly_plan_items
                   WHERE plan_id=? AND category='meal' AND deleted_at IS NULL
                     AND notes LIKE ?
                   ORDER BY weekday, start_time, sort_order, created_at""",
                (plan_id, f"{WEEKLY_RECIPE_MANUAL_MARKER}:%"),
            ).fetchall()
        ]
        recipe_by_slot = {}
        for item in recipe_items:
            if _is_auto_generated_weekly_recipe_item(item):
                continue
            source, marker = _weekly_recipe_marker(item)
            if marker:
                slot = (int(item["weekday"]), marker)
                if source == "manual" or slot not in recipe_by_slot:
                    recipe_by_slot[slot] = item
        meal_types = (
            "breakfast", "morning_snack", "lunch", "afternoon_snack",
            "dinner", "training_fuel", "bedtime_fuel", "free_snack",
        )
        weekday_labels = (_ui("周一", "Mon"), _ui("周二", "Tue"), _ui("周三", "Wed"),
                          _ui("周四", "Thu"), _ui("周五", "Fri"), _ui("周六", "Sat"), _ui("周日", "Sun"))
        with st.container():
            _render_html('<span class="drc-recipe-edit-grid-marker"></span>')
            header = st.columns([1.15] + [1] * 7)
            _render_html(
                f'<div class="drc-recipe-plan-header">{escape(_ui("餐次/日期", "Meal / Date"))}</div>',
                header[0],
            )
            for column, day, weekday_label in zip(
                header[1:], (monday + timedelta(days=index) for index in range(7)), weekday_labels,
            ):
                date_header = (
                    f"{weekday_label} ({day.strftime('%-m/%-d')})"
                    if LANGUAGE == "en"
                    else f"{weekday_label}（{day.strftime('%-m/%-d')}）"
                )
                _render_html(
                    f'<div class="drc-recipe-plan-header">{escape(date_header)}</div>',
                    column,
                )
            for meal_type in meal_types:
                row = st.columns([1.15] + [1] * 7)
                _render_html(
                    f'<div class="drc-recipe-plan-label">{escape(_meal_name(meal_type))}</div>',
                    row[0],
                )
                for weekday, column in enumerate(row[1:]):
                    item = recipe_by_slot.get((weekday, meal_type))
                    source, _ = _weekly_recipe_marker(item or {})
                    title = str(item.get("title") or "") if item else ""
                    for prefix in (f"{_meal_name(meal_type)}：", f"{_meal_name(meal_type)}:"):
                        if title.startswith(prefix):
                            title = title[len(prefix):].strip()
                            break
                    state = source or "empty"
                    _render_html(
                        f'<span class="drc-recipe-edit-cell-marker drc-recipe-edit-cell-marker-{state}"></span>',
                        column,
                    )
                    # Keep each planned item visually separate in the table.
                    # This affects only the presentation; the persisted title,
                    # table geometry, and edit workflow remain unchanged.
                    button_text = (
                        _weekly_recipe_plan_cell_text(connection, item)
                        if item else _ui("＋ 添加", "+ Add")
                    )
                    if column.button(
                        button_text,
                        key=f"nutrition_weekly_recipe_cell_{weekday}_{meal_type}_{item.get('item_id') if item else 'new'}",
                        use_container_width=True,
                    ):
                        st.session_state["nutrition_weekly_recipe_edit_slot"] = {
                            "weekday": weekday,
                            "meal_type": meal_type,
                            "item_id": item.get("item_id") if item else None,
                        }
                        # The editor is deliberately rendered beneath the plan
                        # table.  Record a new focus request before rerunning
                        # so opening any cell lands the user directly there.
                        st.session_state["nutrition_weekly_recipe_editor_focus_nonce"] = (
                            int(st.session_state.get("nutrition_weekly_recipe_editor_focus_nonce", 0)) + 1
                        )
                        st.rerun()
        selected_slot = st.session_state.get("nutrition_weekly_recipe_edit_slot")
        if selected_slot:
            selected_weekday = int(selected_slot["weekday"])
            selected_meal_type = selected_slot["meal_type"]
            selected_item = recipe_by_slot.get((selected_weekday, selected_meal_type))
            editor_key = (
                f"{selected_cycle_record['id']}_{plan_id}_"
                f"{selected_item.get('item_id') if selected_item else f'{selected_weekday}_{selected_meal_type}'}"
            )
            editor_title = _ui("编辑饮食计划", "Edit Nutrition Plan")
            with st.expander(editor_title, expanded=True):
                _render_html('<span class="drc-recipe-editor-marker"></span>')
                st.caption(_ui(
                    f"{weekday_labels[selected_weekday]} · {_meal_name(selected_meal_type)}。请填写该餐次的计划内容。",
                    f"{weekday_labels[selected_weekday]} · {_meal_name(selected_meal_type)}. Enter the planned meal content.",
                ))
                payload = _weekly_recipe_payload(selected_item)
                item_title = str(selected_item.get("title") or "") if selected_item else ""
                for prefix in (f"{_meal_name(selected_meal_type)}：", f"{_meal_name(selected_meal_type)}:"):
                    if item_title.startswith(prefix):
                        item_title = item_title[len(prefix):].strip()
                        break
                if not payload.get("legacy_title"):
                    payload["legacy_title"] = item_title
                default_start = time.fromisoformat(str(selected_item.get("start_time") or "08:00")) if selected_item else time(8, 0)
                default_end = time.fromisoformat(str(selected_item.get("end_time") or "09:00")) if selected_item else time(9, 0)
                weekday_key = f"nutrition_recipe_weekday_{editor_key}"
                meal_type_key = f"nutrition_recipe_meal_type_{editor_key}"
                start_key = f"nutrition_recipe_start_{editor_key}"
                end_key = f"nutrition_recipe_end_{editor_key}"
                st.session_state.setdefault(weekday_key, selected_weekday)
                st.session_state.setdefault(meal_type_key, selected_meal_type)
                st.session_state.setdefault(start_key, default_start)
                st.session_state.setdefault(end_key, default_end)
                controls = st.columns((1, 1, 1.4, 1.4))
                for control in controls:
                    _render_html('<span class="drc-recipe-schedule-control-marker"></span>', control)
                edited_weekday = controls[0].selectbox(
                    _ui("星期", "Weekday"), range(7),
                    format_func=lambda value: weekday_labels[value], key=weekday_key,
                )
                edited_meal_type = controls[1].selectbox(
                    _ui("餐次", "Meal"), meal_types,
                    format_func=_meal_name, key=meal_type_key,
                )
                edited_start = controls[2].time_input(_ui("开始时间", "Start Time"), key=start_key)
                edited_end = controls[3].time_input(_ui("结束时间", "End Time"), key=end_key)
                _render_weekly_recipe_plan_inputs(connection, payload, editor_key)
                st.text_input(_ui("备注（可选）", "Notes (optional)"), key=f"nutrition_recipe_notes_{editor_key}")
                save_column, cancel_column = st.columns(2)
                save_clicked = save_column.button(
                    _ui("保存计划", "Save Plan"), key=f"nutrition_recipe_save_{editor_key}", type="primary",
                )
                cancel_clicked = cancel_column.button(
                    _ui("取消", "Cancel"), key=f"nutrition_recipe_cancel_{editor_key}",
                )
                if cancel_clicked:
                    st.session_state.pop("nutrition_weekly_recipe_edit_slot", None)
                    st.rerun()
                if save_clicked:
                    edited_payload = _weekly_recipe_editor_payload_from_state(
                        connection, payload, editor_key,
                    )
                    normalized_title = _weekly_recipe_payload_title(connection, edited_payload)
                    if not normalized_title:
                        st.warning(_ui("请至少添加一项食物、补剂或用药。", "Add at least one food, supplement, or medication."))
                    elif edited_end <= edited_start:
                        st.warning(_ui("结束时间需晚于开始时间。", "End time must be later than start time."))
                    else:
                        _save_weekly_recipe_item(
                            connection, plan_id, edited_weekday, normalized_title,
                            edited_start, edited_end,
                            notes=json.dumps(edited_payload, ensure_ascii=False, separators=(",", ":")),
                            marker=edited_meal_type, source="manual",
                            existing_item_id=selected_item.get("item_id") if selected_item else None,
                        )
                        connection.commit()
                        st.session_state["nutrition_weekly_recipe_keep_table_open"] = True
                        st.session_state.pop("nutrition_weekly_recipe_edit_slot", None)
                        st.rerun()
            editor_focus_nonce = int(st.session_state.get("nutrition_weekly_recipe_editor_focus_nonce", 0))
            last_editor_focus_nonce = int(
                st.session_state.get("nutrition_weekly_recipe_editor_last_scrolled_nonce", 0)
            )
            if editor_focus_nonce > last_editor_focus_nonce:
                render_interaction_focus(
                    components,
                    target_expander_label=editor_title,
                    nonce=editor_focus_nonce,
                    top_offset=80,
                )
                st.session_state["nutrition_weekly_recipe_editor_last_scrolled_nonce"] = editor_focus_nonce
        st.caption(_ui(
            "点选单元格即可填写或编辑计划内容；实际饮食仍以“编辑今日饮食数据”中保存的记录为准。",
            "Select any cell to enter or edit plan content; saved entries in Edit Today's Dietary Data remain the source of truth for actual intake.",
        ))
    finally:
        cycle_details_directory.__exit__(None, None, None)


def _personal_nutrition_baseline(records, day):
    baseline = calculate_personal_nutrition_baseline(records, day)
    st.subheader(_ui("个人营养基线", "Personal Nutrition Baseline"))
    if baseline["status"] != "ready":
        st.info(_ui(
            f"近 {baseline['window_days']} 天只有 {baseline['sample_days']} 个有记录的日期，至少需要 3 天后才建立个人基线。",
            f"Only {baseline['sample_days']} recorded days are available in the last {baseline['window_days']} days; at least 3 days are needed.",
        ))
        return
    st.caption(_ui(
        f"基于近 {baseline['window_days']} 天、{baseline['sample_days']} 个有记录日期的每日摄入中位数；不包含今天。",
        f"Daily intake medians from {baseline['sample_days']} recorded days in the last {baseline['window_days']} days; today is excluded.",
    ))
    labels = {
        "calories_kcal": _ui("热量（kcal）", "Calories (kcal)"),
        "protein_g": _ui("蛋白质（g）", "Protein (g)"),
        "carbohydrate_g": _ui("碳水化合物（g）", "Carbohydrate (g)"),
        "fat_g": _ui("脂肪（g）", "Fat (g)"),
        "fiber_g": _ui("膳食纤维（g）", "Fiber (g)"),
        "water_ml": _ui("水分（ml）", "Water (ml)"),
    }
    rows = [{
        labels[metric]: baseline["metrics"][metric]["median"]
        if baseline["metrics"][metric]["median"] is not None else TR("common.no_data")
        for metric in labels
    }]
    centered_dataframe(rows)


def _render_personal_nutrition_advice(connection, records, day):
    """Give one concise, multi-factor daily nutrition recommendation."""
    baseline = calculate_personal_nutrition_baseline(records, day)
    targets = recommended_nutrition_targets(connection)
    service = NutritionFeedbackService(records, day, LANGUAGE, targets=targets)
    today = service.today_summary()
    goals = get_personal_goals(connection) or {}
    body = latest_body_measurement(connection) or {}
    training_goal = goals.get("training_goal") or "maintenance"
    configured_adjustment = goals.get("daily_calorie_adjustment_kcal")
    st.subheader(_ui("营养建议", "Nutrition Advice"))

    messages = []
    balance = _daily_calorie_balance(connection, day, today.get("calories_kcal"))
    balance_message = _calorie_balance_advice(
        balance, training_goal, configured_adjustment,
    )
    if balance_message:
        messages.append(balance_message)
    else:
        goal_text = {
            "fat_loss": _ui(
                "训练目标（减脂期）：优先保证蛋白质、蔬菜和全谷物，避免用过度节食替代稳定的热量缺口。",
                "Training goal (fat loss): prioritise protein, vegetables, and whole grains; use a steady calorie gap rather than extreme restriction.",
            ),
            "muscle_gain": _ui(
                "训练目标（增肌期）：保证蛋白质，并在训练前后安排主食或水果支持恢复和适度热量盈余。",
                "Training goal (muscle gain): keep protein adequate and add carbohydrates around training to support recovery and a moderate surplus.",
            ),
            "maintenance": _ui(
                "训练目标（保持期）：保持蛋白质、主食、蔬菜/水果和水分的稳定搭配，并随训练量调整份量。",
                "Training goal (maintenance): keep protein, carbohydrates, vegetables/fruit, and fluids consistent, adjusting portions for training load.",
            ),
        }
        messages.append(goal_text[training_goal])

    nutrient_options = (
        ("protein_g", _ui("蛋白质", "Protein"), _ui("下一餐加入优质蛋白来源。", "Add a quality protein source at the next meal.")),
        ("fiber_g", _ui("膳食纤维", "Fibre"), _ui("下一餐加入蔬菜、水果或全谷物。", "Add vegetables, fruit, or whole grains at the next meal.")),
        ("water_ml", _ui("水分", "Water"), _ui("结合训练前后和餐间分次补水。", "Add fluids gradually around training and between meals.")),
    )
    for metric, label, action in nutrient_options:
        current = today.get(metric)
        target = targets.get(metric)
        personal = baseline["metrics"][metric]["median"] if baseline["status"] == "ready" else None
        if current is None:
            continue
        if target and target[0] is not None and current < target[0]:
            shortfall = _feedback_value(metric, target[0] - current)
            baseline_context = (
                _ui(f"，也低于个人典型值 {_feedback_value(metric, personal)}", f", and below your typical {_feedback_value(metric, personal)}")
                if personal is not None and current < personal * 0.8 else ""
            )
            messages.append(_ui(
                f"营养结构：{label}距离推荐下限还差 {shortfall}{baseline_context}。{action}",
                f"Nutrition mix: {label} is {shortfall} below the recommended minimum{baseline_context}. {action}",
            ))
            break
        if personal is not None and personal > 0 and current < personal * 0.8:
            messages.append(_ui(
                f"个人基线：今日{label}低于你的典型值 {_feedback_value(metric, personal)}。{action}",
                f"Personal baseline: today's {label} is below your typical {_feedback_value(metric, personal)}. {action}",
            ))
            break

    if baseline["status"] != "ready":
        messages.append(_ui(
            f"个人基线：当前已有 {baseline['sample_days']} 个记录日；继续记录至至少 3 天后，系统会进一步按你的实际习惯校准建议。",
            f"Personal baseline: {baseline['sample_days']} days are recorded; continue to at least 3 days so advice can calibrate to your actual habits.",
        ))
    elif len(messages) < 3:
        target_weight = goals.get("target_weight_kg")
        current_weight = body.get("weight_kg")
        if training_goal == "fat_loss" and current_weight and target_weight and current_weight > target_weight:
            messages.append(_ui(
                "身体情况：当前体重仍高于目标，保持规律训练和充足蛋白质，比进一步极端压低热量更利于长期减脂。",
                "Body context: current weight remains above target; regular training and adequate protein support sustainable fat loss better than further extreme restriction.",
            ))
        elif training_goal == "muscle_gain" and current_weight and target_weight and current_weight < target_weight:
            messages.append(_ui(
                "身体情况：当前体重仍低于目标，训练日可在正餐或训练后增加一份主食与蛋白质组合。",
                "Body context: current weight remains below target; add a carbohydrate-and-protein combination to a main or post-training meal on training days.",
            ))

    if not messages:
        messages.append(_ui(
            "继续完成当天饮食与训练记录，系统会结合个人基线、训练目标和能量平衡给出更具体的建议。",
            "Complete today's food and training logs for advice that combines your baseline, training goal, and energy balance.",
        ))
    st.info("\n\n".join(f"• {message}" for message in messages[:3]))


def main():
    st.title(TR("domain.nutrition.title")); st.caption(TR("domain.nutrition.intro"))
    # Nutrition owns the template schema extension, so apply pending migrations
    # before reading templates (existing databases receive template_type here).
    connection = connect(migrate=True)
    try:
        records = list_meal_records(connection, limit=200)
        today_value = date.today().isoformat()
        flash_key = st.session_state.pop("simple_nutrition_flash", None)
        with st.container():
            targets = recommended_nutrition_targets(connection)
            # The recurring plan guides the user before they review today's
            # totals, while remaining independent from actual meal records.
            _render_weekly_recipe(connection, records)
            # Keep the original daily nutrition data overview alongside the
            # compact nutrition cards; both use the same saved meal records.
            _today_nutrition_table(records, today_value)
            returned_to_nutrition = st.session_state.get("drc_previous_page") not in (None, "nutrition")
            deferred_next = st.session_state.get("simple_nutrition_advance_on_reentry")
            pending_selected = st.session_state.pop("simple_meal_selector_pending", None)
            pending_record = get_meal_record(connection, pending_selected) if pending_selected else None
            if deferred_next and returned_to_nutrition:
                deferred_date = date.fromisoformat(deferred_next["date"])
                st.session_state["simple_active_meal_type"] = _next_unrecorded_meal_type(
                    records, deferred_date, deferred_next["meal_type"]
                )
                st.session_state["simple_active_meal_date"] = deferred_date
                st.session_state.pop("simple_nutrition_advance_on_reentry", None)
            elif pending_record:
                # The save rerun stays on the meal that was just saved. The next
                # meal is selected only when the user returns from another page.
                st.session_state["simple_active_meal_type"] = pending_record["meal_type"]
                st.session_state["simple_active_meal_date"] = date.fromisoformat(pending_record["date"])

            st.session_state.setdefault(
                "simple_active_meal_type",
                _next_unrecorded_meal_type(records, date.today()),
            )
            st.session_state.setdefault("simple_active_meal_date", date.today())
            active_type = st.session_state["simple_active_meal_type"]
            active_date = st.session_state["simple_active_meal_date"]
            active_date_value = active_date.isoformat() if hasattr(active_date, "isoformat") else str(active_date)
            active_record_id = find_meal_id(connection, active_type, active_date_value)
            existing = get_meal_record(connection, active_record_id) if active_record_id else None
            with st.expander(_ui("编辑今日饮食数据", "Edit Today's Dietary Data"), expanded=False):
                meal_state = _meal_form(connection, existing, records, targets, flash_key)
            feedback_summary, resolved_targets = _render_current_nutrition_details(
                connection, records, meal_state, targets,
            )
            history_focus_nonce = st.session_state.get("nutrition_history_focus_nonce", 0)
            last_history_focus_nonce = st.session_state.get("nutrition_history_last_scrolled_nonce", 0)
            should_focus_history = history_focus_nonce > last_history_focus_nonce
            _historical_nutrition_situation(
                connection,
                records,
                auto_expand=should_focus_history,
                focus_nonce=history_focus_nonce,
            )
            if should_focus_history:
                st.session_state["nutrition_history_last_scrolled_nonce"] = history_focus_nonce
            _render_current_nutrition_advice(
                connection, feedback_summary, resolved_targets, meal_state,
            )
    finally:
        connection.close()
    st.caption(TR("safety.medical"))


if __name__ == "__main__":
    main()

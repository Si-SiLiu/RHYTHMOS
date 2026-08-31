"""OpenAI Vision-first OCR for one Kubios screenshot at a time.

The cloud route deliberately returns canonical text labels, not health
interpretation.  Existing local validation and the user's review remain the
authority before a measurement is persisted.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Callable, Mapping

import requests
from dotenv import load_dotenv
from PIL import Image

from .models import OCRResult, TextBlock
from .ocr_adapter import LocalOCRError, VisionOCRAdapter


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env.local"
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"
# The provider does not return token-level OCR confidences. This conservative
# score is calibrated for the user-confirmed, ten-sample standard Result
# layout; parser validation still lowers a field when its label, unit, or
# range does not validate.
STANDARD_TEMPLATE_OCR_CONFIDENCE = 0.97

_TRANSCRIPTION_PROMPT = """Transcribe the visible values from this Kubios HRV screenshot.
Return plain text only, one canonical label/value per line, with no Markdown,
commentary, diagnosis, or inferred values. Do not invent a date or time that
is not visibly shown. Use only these labels when their values are visible:
Mean HR, RMSSD, PNS index, SNS index, Physiological age, Mean RR, SDNN,
Poincaré SD1, Poincaré SD2, Stress index, Respiratory rate, LF power,
HF power, LF power n.u., HF power n.u., LF/HF ratio, Measurement quality,
Mood. Preserve units when visible."""

_CANONICAL_LABELS = {
    "mean_hr": "Mean HR",
    "rmssd": "RMSSD",
    "pns_index": "PNS index",
    "sns_index": "SNS index",
    "physiological_age": "Physiological age",
    "mean_rr_ms": "Mean RR",
    "sdnn": "SDNN",
    "poincare_sd1_ms": "Poincaré SD1",
    "poincare_sd2_ms": "Poincaré SD2",
    "stress_index": "Stress index",
    "respiratory_rate_bpm": "Respiratory rate",
    "lf_power_ms2": "LF power",
    "hf_power_ms2": "HF power",
    "lf_power_nu": "LF power n.u.",
    "hf_power_nu": "HF power n.u.",
    "lf_hf_ratio": "LF/HF ratio",
    "measurement_quality": "Measurement quality",
    "mood_code": "Mood",
}


class CloudOCRError(LocalOCRError):
    """Safe cloud OCR failure code; never includes provider response content."""


def _extract_output_text(payload: Mapping[str, Any]) -> str:
    text = payload.get("output_text")
    if isinstance(text, str) and text.strip():
        return text
    for item in payload.get("output", []):
        if not isinstance(item, Mapping):
            continue
        for content in item.get("content", []):
            if isinstance(content, Mapping) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    raise CloudOCRError("cloud_ocr_invalid_response")


class OpenAIVisionOCRAdapter:
    """Send one prepared screenshot to the Responses API for transcription."""

    engine = "openai_vision"
    uses_full_image_extraction = True

    def __init__(
        self,
        *,
        model: str | None = None,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 25.0,
        post: Callable[..., Any] | None = None,
    ):
        self.model = model or os.environ.get("KUBIOS_OCR_MODEL", DEFAULT_MODEL)
        self.endpoint = endpoint
        self.timeout = timeout
        self._post = post or requests.post

    @staticmethod
    def _api_key() -> str:
        load_dotenv(ENV_PATH, override=False)
        value = os.environ.get("OPENAI_API_KEY", "")
        if not isinstance(value, str) or not value.startswith("sk-") or len(value) < 16:
            raise CloudOCRError("cloud_ocr_unavailable")
        return value

    def readiness(self):
        try:
            self._api_key()
        except CloudOCRError:
            available = False
        else:
            available = True
        return {
            "ready": available,
            "engine": self.engine,
            "network_required": True,
            "model": self.model,
        }

    def _recognize_with_prompt(self, image_path, prompt):
        image_path = Path(image_path)
        if not image_path.is_file():
            raise CloudOCRError("image_not_found")
        key = self._api_key()
        try:
            with Image.open(image_path) as image:
                image_size = {"width": image.width, "height": image.height}
            encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        except (OSError, ValueError) as exc:
            raise CloudOCRError("cloud_ocr_image_read_failed") from exc

        request_body = {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": "low"},
            "max_output_tokens": 700,
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{encoded}",
                        "detail": "high",
                    },
                ],
            }],
        }
        try:
            response = self._post(
                self.endpoint,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=request_body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            text = _extract_output_text(response.json())
        except (requests.RequestException, ValueError, TypeError, CloudOCRError) as exc:
            if isinstance(exc, CloudOCRError):
                raise
            raise CloudOCRError("cloud_ocr_request_failed") from exc

        lines = [line.strip(" -*\t")[:500] for line in text.splitlines() if line.strip()]
        if not lines:
            raise CloudOCRError("cloud_ocr_empty_response")
        blocks = [
            TextBlock(line, STANDARD_TEMPLATE_OCR_CONFIDENCE, {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0})
            for line in lines
        ]
        return OCRResult(
            engine=self.engine,
            engine_version=self.model,
            image_size=image_size,
            text_blocks=blocks,
            raw_text="\n".join(lines),
        )

    def recognize(self, image_path):
        return self._recognize_with_prompt(image_path, _TRANSCRIPTION_PROMPT)

    def recognize_missing_fields(self, image_path, field_names):
        """Recheck only fields absent from the first transcription.

        This keeps the second request small and makes it less likely that a
        long, otherwise correct transcription drops a value near the bottom
        of a standard Kubios screenshot. Unknown names are deliberately
        ignored, so the prompt cannot be expanded by external input.
        """
        labels = [_CANONICAL_LABELS[name] for name in field_names if name in _CANONICAL_LABELS]
        if not labels:
            raise CloudOCRError("cloud_ocr_no_supported_fields")
        prompt = (
            "Recheck this Kubios HRV screenshot for only the following visible fields: "
            + ", ".join(labels)
            + ". Return plain text only, one canonical label/value per line. "
            "Do not infer, diagnose, or include any other field. Preserve visible units."
        )
        return self._recognize_with_prompt(image_path, prompt)


class PreferredVisionOCRAdapter:
    """Prefer cloud transcription and fall back to macOS Vision when offline."""

    engine = "openai_vision_with_local_fallback"

    def __init__(self, cloud_adapter=None, local_adapter=None):
        self.cloud = cloud_adapter or OpenAIVisionOCRAdapter()
        self.local = local_adapter or VisionOCRAdapter()

    def readiness(self):
        cloud = self.cloud.readiness()
        local = self.local.readiness()
        return {
            "ready": bool(cloud.get("ready") or local.get("ready")),
            "engine": self.engine,
            "network_required": bool(cloud.get("ready")),
            "cloud_ready": bool(cloud.get("ready")),
            "local_ready": bool(local.get("ready")),
        }

    def is_full_image_result(self, result: OCRResult) -> bool:
        return result.engine == self.cloud.engine

    def recognize(self, image_path):
        if self.cloud.readiness().get("ready"):
            try:
                return self.cloud.recognize(image_path)
            except CloudOCRError:
                # Preserve the working offline flow rather than blocking a
                # user from manually confirming a local result.
                pass
        return self.local.recognize(image_path)

    def recognize_missing_fields(self, image_path, field_names):
        """Use the API-only focused retry; local OCR remains the offline fallback."""
        if not self.cloud.readiness().get("ready"):
            raise CloudOCRError("cloud_ocr_unavailable")
        return self.cloud.recognize_missing_fields(image_path, field_names)

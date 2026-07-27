# Privacy and Local Data Safety

RHYTHMOS｜律衡 keeps health data, screenshots, OCR processing, reports,
and preferences on the local Mac. Kubios screenshots are processed with macOS
Vision and are not uploaded, not placed in AI Context, and not exposed to
Cloud AI. No API key is used for screenshot recognition.

Original screenshots are retained until the user explicitly deletes them.
Deletion requires a second confirmation and preserves confirmed Kubios health
records unless the user separately requests deletion of that record. Logs and
governance state exclude complete OCR text, complete local image paths,
credentials, raw Polar payloads, and unrelated screen content.

OCR output can be wrong. It must be reviewed before import and is never used to
infer a medical abnormality. RHYTHMOS｜律衡 is not a medical device.

The scheduler plist contains executable paths and calendar time only; it never
copies credentials or environment-variable contents. Scheduled sync remains
local and does not invoke Cloud AI. Manual health notes remain local and are
excluded from AI Context by default. Source resolution stores provenance, not a
second copy of raw payloads, and does not overwrite Polar or Kubios raw rows.

"""Strict, fail-safe configuration for the local daily sync scheduler."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import os
import re
import tempfile
import tomllib


BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config" / "scheduler.toml"
SYNC_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
SCHEDULED_SYNC_TIMES = ("12:00", "18:00", "23:00")
EXPECTED_KEYS = {
    "enabled",
    "sync_time",
    "timezone_mode",
    "catch_up_on_app_start",
    "prompt_before_catch_up",
    "max_catch_up_runs_per_day",
}


class SchedulerConfigError(ValueError):
    """Raised when scheduler configuration fails strict validation."""


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool = True
    sync_time: str = "23:00"
    timezone_mode: str = "system"
    catch_up_on_app_start: bool = True
    prompt_before_catch_up: bool = False
    max_catch_up_runs_per_day: int = 1

    @property
    def hour(self) -> int:
        return int(self.sync_time[:2])

    @property
    def minute(self) -> int:
        return int(self.sync_time[3:])

    @property
    def scheduled_times(self) -> tuple[str, ...]:
        """Fixed local refresh times; ``sync_time`` is retained for compatibility."""
        return SCHEDULED_SYNC_TIMES


@dataclass(frozen=True)
class SchedulerConfigLoad:
    config: SchedulerConfig
    used_fallback: bool
    error_code: str | None = None


DEFAULT_CONFIG = SchedulerConfig()


def validate_scheduler_config(values: object) -> SchedulerConfig:
    if not isinstance(values, dict):
        raise SchedulerConfigError("SCHEDULER_CONFIG_NOT_A_TABLE")
    if set(values) != EXPECTED_KEYS:
        raise SchedulerConfigError("SCHEDULER_CONFIG_FIELDS_INVALID")

    boolean_keys = (
        "enabled",
        "catch_up_on_app_start",
        "prompt_before_catch_up",
    )
    if any(type(values[key]) is not bool for key in boolean_keys):
        raise SchedulerConfigError("SCHEDULER_CONFIG_BOOLEAN_INVALID")
    sync_time = values["sync_time"]
    if not isinstance(sync_time, str) or not SYNC_TIME_RE.fullmatch(sync_time):
        raise SchedulerConfigError("SCHEDULER_SYNC_TIME_INVALID")
    if values["timezone_mode"] != "system":
        raise SchedulerConfigError("SCHEDULER_TIMEZONE_MODE_INVALID")
    maximum = values["max_catch_up_runs_per_day"]
    if type(maximum) is not int or maximum not in (0, 1):
        raise SchedulerConfigError("SCHEDULER_CATCH_UP_LIMIT_INVALID")
    return SchedulerConfig(**values)


def load_scheduler_config(path: Path | str = CONFIG_PATH) -> SchedulerConfigLoad:
    """Load config, returning defaults on damage without rewriting the source."""
    source = Path(path)
    try:
        with source.open("rb") as config_file:
            values = tomllib.load(config_file)
        config = validate_scheduler_config(values)
    except FileNotFoundError:
        return SchedulerConfigLoad(DEFAULT_CONFIG, True, "SCHEDULER_CONFIG_MISSING")
    except (OSError, tomllib.TOMLDecodeError, SchedulerConfigError):
        return SchedulerConfigLoad(DEFAULT_CONFIG, True, "SCHEDULER_CONFIG_INVALID")
    return SchedulerConfigLoad(config, False, None)


def _serialize(config: SchedulerConfig) -> str:
    values = asdict(config)
    return (
        f"enabled = {str(values['enabled']).lower()}\n"
        f"sync_time = \"{values['sync_time']}\"\n"
        f"timezone_mode = \"{values['timezone_mode']}\"\n"
        f"catch_up_on_app_start = {str(values['catch_up_on_app_start']).lower()}\n"
        f"prompt_before_catch_up = {str(values['prompt_before_catch_up']).lower()}\n"
        f"max_catch_up_runs_per_day = {values['max_catch_up_runs_per_day']}\n"
    )


def save_scheduler_config(
    config: SchedulerConfig | dict,
    path: Path | str = CONFIG_PATH,
) -> SchedulerConfig:
    """Validate and atomically persist scheduler settings."""
    if isinstance(config, SchedulerConfig):
        validated = validate_scheduler_config(asdict(config))
    else:
        validated = validate_scheduler_config(config)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as config_file:
            config_file.write(_serialize(validated))
            config_file.flush()
            os.fsync(config_file.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return validated

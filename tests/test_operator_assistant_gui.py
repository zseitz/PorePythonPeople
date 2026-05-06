import importlib.util
import sys
from pathlib import Path

from nanoporethon.operator_assistant_gui import (
    _activity_indicator_text,
    _activity_status_label,
    _classifier_health_check,
    _intent_badge_style,
    _resolve_repo_root,
)


def test_intent_badge_style_for_feature_request_is_explicit_and_green():
    text, color = _intent_badge_style("feature_request", 0.85)
    assert "Feature Request" in text
    assert "0.85" in text
    assert color == "#0a7d33"


def test_intent_badge_style_defaults_for_unknown_intent():
    text, color = _intent_badge_style("", 0.0)
    assert "Unknown" in text
    assert color == "#555555"


class _HealthyAdapter:
    def __init__(self, model: str, base_url: str):
        self.model = model
        self.base_url = base_url

    def chat(self, system_prompt: str, messages: list) -> str:
        return '{"intent": "feature_request", "confidence": 0.92, "reason": "ok"}'


class _ModelMissingAdapter:
    def __init__(self, model: str, base_url: str):
        pass

    def chat(self, system_prompt: str, messages: list) -> str:
        raise RuntimeError("model 'mistral:7b' not found")


class _ConnectionErrorAdapter:
    def __init__(self, model: str, base_url: str):
        pass

    def chat(self, system_prompt: str, messages: list) -> str:
        raise RuntimeError("connection refused")


class _MalformedAdapter:
    def __init__(self, model: str, base_url: str):
        pass

    def chat(self, system_prompt: str, messages: list) -> str:
        return "not json"


class _WrappedJsonAdapter:
    def __init__(self, model: str, base_url: str):
        self.model = model
        self.base_url = base_url

    def chat_json(self, system_prompt: str, messages: list) -> str:
        return 'Sure — here is the result: {"intent": "feature_request", "confidence": 0.9, "reason": "healthcheck"}'


def test_classifier_health_check_healthy():
    policy = {
        "assistant_scope": {
            "intent_classifier": {"enabled": True, "model": "mistral:7b", "base_url": "http://localhost:11434"}
        }
    }
    result = _classifier_health_check(policy, adapter_factory=_HealthyAdapter)
    assert result["ok"] == "true"
    assert result["status"] == "healthy"


def test_classifier_health_check_disabled_config():
    policy = {"assistant_scope": {"intent_classifier": {"enabled": False}}}
    result = _classifier_health_check(policy, adapter_factory=_HealthyAdapter)
    assert result["ok"] == "false"
    assert result["status"] == "config_error"


def test_classifier_health_check_model_missing():
    policy = {
        "assistant_scope": {
            "intent_classifier": {"enabled": True, "model": "mistral:7b", "base_url": "http://localhost:11434"}
        }
    }
    result = _classifier_health_check(policy, adapter_factory=_ModelMissingAdapter)
    assert result["ok"] == "false"
    assert result["status"] == "model_missing"


def test_classifier_health_check_connection_error():
    policy = {
        "assistant_scope": {
            "intent_classifier": {"enabled": True, "model": "mistral:7b", "base_url": "http://localhost:11434"}
        }
    }
    result = _classifier_health_check(policy, adapter_factory=_ConnectionErrorAdapter)
    assert result["ok"] == "false"
    assert result["status"] == "service_unreachable"


def test_classifier_health_check_malformed_output():
    policy = {
        "assistant_scope": {
            "intent_classifier": {"enabled": True, "model": "mistral:7b", "base_url": "http://localhost:11434"}
        }
    }
    result = _classifier_health_check(policy, adapter_factory=_MalformedAdapter)
    assert result["ok"] == "false"
    assert result["status"] == "malformed_output"


def test_classifier_health_check_extracts_wrapped_json_when_available():
    policy = {
        "assistant_scope": {
            "intent_classifier": {"enabled": True, "model": "mistral:7b", "base_url": "http://localhost:11434"}
        }
    }
    result = _classifier_health_check(policy, adapter_factory=_WrappedJsonAdapter)
    assert result["ok"] == "true"
    assert result["status"] == "healthy"


def test_activity_indicator_runtime_cycles_dots():
    text_1, color_1 = _activity_indicator_text(runtime_running=True, assistant_processing=False, dot_phase=0)
    text_2, color_2 = _activity_indicator_text(runtime_running=True, assistant_processing=False, dot_phase=1)
    text_3, color_3 = _activity_indicator_text(runtime_running=True, assistant_processing=False, dot_phase=2)

    assert text_1.endswith(".")
    assert text_2.endswith("..")
    assert text_3.endswith("...")
    assert color_1 == "#1f4aa8"
    assert color_2 == "#1f4aa8"
    assert color_3 == "#1f4aa8"


def test_activity_indicator_assistant_processing_and_idle():
    processing_text, processing_color = _activity_indicator_text(
        runtime_running=False,
        assistant_processing=True,
        dot_phase=1,
    )
    idle_text, idle_color = _activity_indicator_text(
        runtime_running=False,
        assistant_processing=False,
        dot_phase=2,
    )

    assert "assistant is processing" in processing_text
    assert processing_text.endswith("..")
    assert processing_color == "#6a3dad"
    assert idle_text == "Activity: idle"
    assert idle_color == "#666666"


def test_activity_status_label_includes_last_ui_tick():
    label = _activity_status_label("Activity: runtime execution in progress..", "13:47:22")
    assert label == "Activity: runtime execution in progress.. (last UI tick: 13:47:22)"


def test_operator_assistant_gui_direct_file_import_succeeds_without_repo_root_on_syspath():
    module_path = Path(__file__).resolve().parents[1] / "src" / "nanoporethon" / "operator_assistant_gui.py"
    module_name = "_tmp_operator_assistant_gui_direct_import"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None

    original_syspath = list(sys.path)
    try:
        repo_root = str(Path(__file__).resolve().parents[1])
        sys.path = [p for p in sys.path if p and p != repo_root]
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path = original_syspath
        sys.modules.pop(module_name, None)

    assert hasattr(module, "run_gui")


def test_resolve_repo_root_finds_policy_from_non_repo_cwd(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    resolved = _resolve_repo_root(tmp_path, module_file=repo_root / "src" / "nanoporethon" / "operator_assistant_gui.py")
    assert resolved == repo_root

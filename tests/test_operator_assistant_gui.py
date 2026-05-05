from nanoporethon.operator_assistant_gui import _classifier_health_check, _intent_badge_style


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

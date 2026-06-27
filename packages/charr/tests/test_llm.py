"""Tests for the LLM seam: image encoding, message building, response parsing, and the HTTP client."""

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

import pytest
import requests
from charr.config import Config, LlmSettings
from charr.llm import (
  CheckResponse,
  LlmError,
  OpenAiCompatClient,
  build_messages,
  encode_image_data_url,
  parse_chat_completion,
)
from charr.models import Rule, Verdict
from charr.rules import select_enabled_rules


def _completion(content: str) -> dict[str, object]:
  return {"choices": [{"message": {"content": content}}]}


def _all_pass_json(rules: Sequence[Rule]) -> str:
  return json.dumps({"results": [{"rule_id": rule.id, "verdict": "pass", "rationale": "ok"} for rule in rules]})


def _user_text_and_image_url(messages: list[dict[str, object]]) -> tuple[str, str]:
  content = messages[1]["content"]
  assert isinstance(content, list)
  text_part, image_part = content[0], content[1]
  assert isinstance(text_part, dict)
  assert isinstance(image_part, dict)
  text = text_part["text"]
  image_url = image_part["image_url"]
  assert isinstance(text, str)
  assert isinstance(image_url, dict)
  url = image_url["url"]
  assert isinstance(url, str)
  return text, url


class _FakeResponse:
  def __init__(self, payload: object, *, status: int = 200) -> None:
    self._payload = payload
    self.status_code = status
    self.text = json.dumps(payload)

  def json(self) -> object:
    return self._payload


class _FakeSession:
  def __init__(self, payload: object, captured: dict[str, object]) -> None:
    self._payload = payload
    self._captured = captured

  def post(self, url: str, *, json: object, headers: dict[str, str], timeout: float) -> _FakeResponse:
    self._captured.update(url=url, body=json, headers=headers, timeout=timeout)
    return _FakeResponse(self._payload)


class _ErrorSession:
  def post(self, *_args: object, **_kwargs: object) -> _FakeResponse:
    return _FakeResponse({"error": "'response_format.type' must be 'json_schema' or 'text'"}, status=400)


class _RaisingSession:
  def post(self, *_args: object, **_kwargs: object) -> _FakeResponse:
    msg = "connection refused"
    raise requests.ConnectionError(msg)


def test_encode_image_data_url_uses_the_right_mime_for_each_supported_suffix(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  cases = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
  for suffix, mime in cases.items():
    image = make_image(tmp_path / f"chart{suffix}")
    assert encode_image_data_url(image).startswith(f"data:{mime};base64,")


def test_encode_image_data_url_raises_on_an_unsupported_suffix(tmp_path: Path) -> None:
  tiff = tmp_path / "x.tiff"
  tiff.write_bytes(b"II*\x00")
  with pytest.raises(LlmError):
    encode_image_data_url(tiff)


def test_build_messages_includes_every_enabled_rule_id_and_a_base64_image_data_url(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  rules = select_enabled_rules([], [])
  image = make_image(tmp_path / "c.png")
  text, url = _user_text_and_image_url(build_messages(image, rules, Config()))
  for rule in rules:
    assert rule.id in text
  assert url.startswith("data:image/png;base64,")


def test_build_messages_interpolates_palette_and_fonts_from_config(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  rules = select_enabled_rules(["palette-compliance", "font-compliance"], [])
  image = make_image(tmp_path / "c.png")
  config = Config(palette=["#abcdef"], fonts=["Inter"])
  text, _ = _user_text_and_image_url(build_messages(image, rules, config))
  assert "#abcdef" in text
  assert "Inter" in text


def test_parse_chat_completion_validates_results_from_message_content() -> None:
  payload = _completion(json.dumps({"results": [{"rule_id": "has-title", "verdict": "fail", "rationale": "none"}]}))
  parsed = parse_chat_completion(payload)
  assert parsed.results[0].verdict is Verdict.FAIL


def test_parse_chat_completion_raises_on_non_json_or_schema_mismatch_content() -> None:
  with pytest.raises(LlmError):
    parse_chat_completion(_completion("not json at all"))
  with pytest.raises(LlmError):
    parse_chat_completion(_completion(json.dumps({"unexpected": []})))


def test_parse_chat_completion_raises_when_choices_are_missing() -> None:
  with pytest.raises(LlmError):
    parse_chat_completion({})


def test_openai_compat_client_posts_to_chat_completions_and_parses_results_with_a_fake_session(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  rules = select_enabled_rules([], [])
  image = make_image(tmp_path / "c.png")
  captured: dict[str, object] = {}
  session = cast("requests.Session", _FakeSession(_completion(_all_pass_json(rules)), captured))
  client = OpenAiCompatClient(LlmSettings(base_url="http://host/v1", api_key=None, model="vlm"), session=session)
  result = client.check_image(image=image, rules=rules, config=Config())
  assert isinstance(result, CheckResponse)
  assert [verdict.rule_id for verdict in result.results] == [rule.id for rule in rules]
  assert str(captured["url"]).endswith("/chat/completions")
  body = captured["body"]
  assert isinstance(body, dict)
  assert body["model"] == "vlm"
  response_format = body["response_format"]
  assert isinstance(response_format, dict)
  assert response_format["type"] == "json_schema"


def test_openai_compat_client_sends_authorization_header_only_when_api_key_present(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  rules = select_enabled_rules(["has-title"], [])
  image = make_image(tmp_path / "c.png")
  payload = _completion(_all_pass_json(rules))

  anon: dict[str, object] = {}
  anon_session = cast("requests.Session", _FakeSession(payload, anon))
  OpenAiCompatClient(
    LlmSettings(base_url="http://host/v1", api_key=None, model="m"),
    session=anon_session,
  ).check_image(image=image, rules=rules, config=Config())
  assert "Authorization" not in cast("dict[str, str]", anon["headers"])

  keyed: dict[str, object] = {}
  keyed_session = cast("requests.Session", _FakeSession(payload, keyed))
  OpenAiCompatClient(
    LlmSettings(base_url="http://host/v1", api_key="secret", model="m"),
    session=keyed_session,
  ).check_image(image=image, rules=rules, config=Config())
  assert cast("dict[str, str]", keyed["headers"])["Authorization"] == "Bearer secret"


def test_openai_compat_client_wraps_transport_errors_as_llm_error(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  rules = select_enabled_rules(["has-title"], [])
  image = make_image(tmp_path / "c.png")
  session = cast("requests.Session", _RaisingSession())
  client = OpenAiCompatClient(LlmSettings(base_url="http://host/v1", api_key=None, model="m"), session=session)
  with pytest.raises(LlmError):
    client.check_image(image=image, rules=rules, config=Config())


def test_openai_compat_client_surfaces_the_error_body_on_an_http_error(
  tmp_path: Path,
  make_image: Callable[[Path], Path],
) -> None:
  rules = select_enabled_rules(["has-title"], [])
  image = make_image(tmp_path / "c.png")
  session = cast("requests.Session", _ErrorSession())
  client = OpenAiCompatClient(LlmSettings(base_url="http://host/v1", api_key=None, model="m"), session=session)
  with pytest.raises(LlmError, match="json_schema"):
    client.check_image(image=image, rules=rules, config=Config())

"""The LLM backend seam: build one OpenAI-compatible request per image and validate the structured response.

This is the only module that performs HTTP. ``checker`` depends on the ``LlmClient`` Protocol (not the concrete
client), and the concrete client takes an injected ``requests.Session``, so tests can drive both without a network. The
"all enabled rules in a single call per image" strategy lives entirely here and is never exposed to callers.
"""

import base64
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

import requests
from pydantic import BaseModel

from charr.config import Config, LlmSettings
from charr.models import IMAGE_MIME_BY_SUFFIX, CharrError, Rule, RuleVerdict

DEFAULT_TIMEOUT_SECONDS = 120.0

_SYSTEM_PROMPT = (
  "You are Charr, a strict checker for chart images. Judge only what is visible in the image. For each rule, decide "
  "pass, fail, or not_applicable, and give a one-sentence rationale. Respond with a single JSON object and nothing "
  'else, matching exactly: {"results": [{"rule_id": "<id>", "verdict": "pass|fail|not_applicable", "rationale": '
  '"<one sentence>"}]}. Include exactly one entry per requested rule, using the rule_id given.'
)


class LlmError(CharrError):
  """Raised when the backend is unreachable, errors, or returns a response that does not match the expected schema."""


class CheckResponse(BaseModel):
  """The structured payload required back from the model: one verdict per requested rule."""

  results: list[RuleVerdict]


class LlmClient(Protocol):
  """Abstraction over a vision LLM that checks one image against a set of rules."""

  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:
    """Return one verdict per rule for ``image``.

    Implementations may hit the network; tests supply a fake.

    :param image: The chart image to evaluate.
    :param rules: The rules to check, in the order to request and report them.
    :param config: The active configuration (palette, fonts, and so on).
    :return: The model's verdicts, one per requested rule.
    """
    ...


def encode_image_data_url(image: Path) -> str:
  """Encode ``image`` as a ``data:`` URL with a MIME type derived from its suffix.

  :param image: Path to a supported image file (suffix must be in ``IMAGE_MIME_BY_SUFFIX``).
  :return: A ``data:<mime>;base64,...`` URL string.
  :raises LlmError: If the file suffix is not a supported image type.
  """
  mime = IMAGE_MIME_BY_SUFFIX.get(image.suffix.lower())
  if mime is None:
    msg = f"unsupported image type: {image}"
    raise LlmError(msg)
  encoded = base64.b64encode(image.read_bytes()).decode("ascii")
  return f"data:{mime};base64,{encoded}"


def build_messages(image: Path, rules: Sequence[Rule], config: Config) -> list[dict[str, object]]:
  """Build the OpenAI-compatible ``messages`` array: a system prompt and a user turn with the rules plus the image.

  :param image: The chart image to embed as a base64 data URL.
  :param rules: The enabled rules to describe to the model.
  :param config: The active configuration, used to fill palette/font placeholders.
  :return: The ``messages`` list for the chat-completions request.
  """
  return [
    {"role": "system", "content": _SYSTEM_PROMPT},
    {
      "role": "user",
      "content": [
        {"type": "text", "text": _rules_block(rules, config)},
        {"type": "image_url", "image_url": {"url": encode_image_data_url(image)}},
      ],
    },
  ]


def parse_chat_completion(raw: Mapping[str, object]) -> CheckResponse:
  """Pull the assistant message out of a chat-completion response and validate it against ``CheckResponse``.

  :param raw: The decoded JSON body of a chat-completions response.
  :return: The validated per-rule verdicts.
  :raises LlmError: If the response has no text content or does not match the expected schema.
  """
  choices = raw.get("choices")
  if not isinstance(choices, list) or not choices:
    msg = "LLM response contained no choices"
    raise LlmError(msg)
  message = choices[0].get("message") if isinstance(choices[0], dict) else None
  content = message.get("content") if isinstance(message, dict) else None
  if not isinstance(content, str):
    msg = "LLM response choice had no text content"
    raise LlmError(msg)
  try:
    return CheckResponse.model_validate_json(content)
  except ValueError as exc:
    msg = f"model did not return the expected JSON schema: {exc}"
    raise LlmError(msg) from exc


class OpenAiCompatClient:
  """Concrete ``LlmClient`` over an OpenAI-compatible ``/chat/completions`` endpoint.

  ``settings.base_url`` is expected to point at the API root including any version prefix (e.g.
  ``http://localhost:11434/v1``); ``/chat/completions`` is appended.
  """

  def __init__(
    self,
    settings: LlmSettings,
    *,
    session: requests.Session,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
  ) -> None:
    """Store the endpoint settings, the injected HTTP session, and the per-request timeout.

    :param settings: Endpoint and credentials for the backend.
    :param session: HTTP session used for the request (injected so tests can fake it).
    :param timeout: Per-request timeout in seconds.
    """
    self._settings = settings
    self._session = session
    self._timeout = timeout

  def check_image(self, *, image: Path, rules: Sequence[Rule], config: Config) -> CheckResponse:
    """Send all ``rules`` for ``image`` in one request and return the validated per-rule verdicts.

    :param image: The chart image to evaluate.
    :param rules: The rules to check in a single call.
    :param config: The active configuration.
    :return: The model's verdicts, one per requested rule.
    :raises LlmError: If the backend is unreachable, errors, or returns an unparseable response.
    """
    payload: dict[str, object] = {
      "model": self._settings.model,
      "temperature": 0,
      "response_format": {"type": "json_object"},
      "messages": build_messages(image, rules, config),
    }
    headers = {"Content-Type": "application/json"}
    if self._settings.api_key:
      headers["Authorization"] = f"Bearer {self._settings.api_key}"
    url = f"{self._settings.base_url}/chat/completions"
    try:
      response = self._session.post(url, json=payload, headers=headers, timeout=self._timeout)
      response.raise_for_status()
      raw = response.json()
    except requests.RequestException as exc:
      msg = f"LLM request to {url} failed: {exc}"
      raise LlmError(msg) from exc
    if not isinstance(raw, dict):
      msg = "LLM response was not a JSON object"
      raise LlmError(msg)
    return parse_chat_completion(raw)


def _rules_block(rules: Sequence[Rule], config: Config) -> str:
  palette = ", ".join(config.palette) if config.palette else "(none configured)"
  fonts = ", ".join(config.fonts) if config.fonts else "(none configured)"
  lines = ["Evaluate the chart against each rule below. Return exactly one result per rule, using the given rule_id:"]
  lines.extend(f"- {rule.id}: {rule.prompt.format(palette=palette, fonts=fonts)}" for rule in rules)
  return "\n".join(lines)

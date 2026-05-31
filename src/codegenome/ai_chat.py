"""Local AI chat helpers for the live graph UI."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "api_style": "openai",
        "requires_api_key": True,
        "models_url": "https://api.openai.com/v1/models",
        "chat_url": "https://api.openai.com/v1/chat/completions",
    },
    "google": {
        "label": "Google Gemini",
        "api_style": "google",
        "requires_api_key": True,
        "models_url": "https://generativelanguage.googleapis.com/v1beta/models",
        "chat_url": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    },
    "groq": {
        "label": "Groq",
        "api_style": "openai",
        "requires_api_key": True,
        "models_url": "https://api.groq.com/openai/v1/models",
        "chat_url": "https://api.groq.com/openai/v1/chat/completions",
    },
    "ollama": {
        "label": "Ollama",
        "api_style": "ollama",
        "requires_api_key": False,
        "models_url": "http://127.0.0.1:11434/api/tags",
        "chat_url": "http://127.0.0.1:11434/api/chat",
    },
}

CONFIG_FILENAME = "ai-chat.json"
MAX_CONTEXT_NODES = 16
MAX_CONTEXT_EDGES = 32
MAX_NEIGHBORS = 12
MAX_CONTEXT_CHARS = 8_000
MAX_CONTEXT_VALUE_CHARS = 180
MAX_RESPONSE_TOKENS = 900
DEFAULT_CONTEXT_SIZE = "small"
CONTEXT_PROFILES = {
    "full": {"nodes": 40, "edges": 96, "neighbors": 24, "chars": 16_000, "value_chars": 240},
    "medium": {"nodes": 16, "edges": 32, "neighbors": 12, "chars": 8_000, "value_chars": 180},
    "small": {"nodes": 8, "edges": 16, "neighbors": 6, "chars": 4_000, "value_chars": 140},
    "minimal": {"nodes": 4, "edges": 8, "neighbors": 3, "chars": 1_800, "value_chars": 100},
}
DEFAULT_HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "CodeGenome/0.1 (+https://github.com/watcher-dev/codegenome)",
}


@dataclass(frozen=True)
class ProviderRequest:
    """Validated provider request fields from the browser."""

    provider: str
    api_key: str = ""


class AIChatError(RuntimeError):
    """Raised when a provider or local AI chat operation fails."""


def settings_payload(genome_dir: Path) -> dict[str, Any]:
    """Return public AI chat settings without exposing saved API keys."""
    config = _read_config(genome_dir)
    api_keys = config.get("api_keys", {})
    if not isinstance(api_keys, dict):
        api_keys = {}

    return {
        "providers": [
            {
                "id": provider_id,
                "label": meta["label"],
                "requires_api_key": bool(meta.get("requires_api_key", True)),
            }
            for provider_id, meta in PROVIDERS.items()
        ],
        "saved": {
            provider_id: bool(api_keys.get(provider_id))
            for provider_id in PROVIDERS
        },
        "default_provider": config.get("default_provider") or "openai",
    }


def load_models(
    genome_dir: Path,
    provider: str,
    api_key: str | None = None,
    *,
    save_api_key: bool = False,
) -> list[dict[str, str]]:
    """Fetch available model ids for a provider."""
    request = _provider_request(genome_dir, provider, api_key)

    if request.provider == "google":
        url = f"{PROVIDERS[request.provider]['models_url']}?key={urllib.parse.quote(request.api_key)}"
        payload = _request_json(url, headers={})
        models = [
            model.get("name", "").removeprefix("models/")
            for model in payload.get("models", [])
            if "generateContent" in model.get("supportedGenerationMethods", [])
        ]
    elif request.provider == "ollama":
        payload = _request_json(PROVIDERS[request.provider]["models_url"], headers={})
        models = [
            model.get("model") or model.get("name", "")
            for model in payload.get("models", [])
        ]
    else:
        payload = _request_json(
            PROVIDERS[request.provider]["models_url"],
            headers=_provider_headers(request.provider, request.api_key),
        )
        models = [model.get("id", "") for model in payload.get("data", [])]

    cleaned = sorted({model for model in models if model})
    if not cleaned:
        raise AIChatError("No chat-capable models were returned by the provider.")

    if save_api_key and PROVIDERS[request.provider].get("requires_api_key", True):
        save_provider_key(genome_dir, request.provider, request.api_key)

    return [{"id": model, "label": model} for model in cleaned]


def chat_completion(
    genome_dir: Path,
    graph_json_path: Path,
    provider: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str | None = None,
    selected_node_id: str | None = None,
    context_size: str | None = None,
    *,
    save_api_key: bool = False,
) -> str:
    """Ask a provider to answer against the current CodeGenome graph."""
    request = _provider_request(genome_dir, provider, api_key)
    if not isinstance(messages, list):
        raise AIChatError("Chat messages must be an array.")
    clean_messages = _clean_messages(messages)
    if not clean_messages:
        raise AIChatError("Send a question before starting chat.")
    if not model:
        raise AIChatError("Choose a model before starting chat.")

    graph_context = build_graph_context(
        graph_json_path,
        selected_node_id=selected_node_id,
        context_size=context_size,
    )
    system_prompt = (
        "You are CodeGenome's live graph assistant. Answer using the supplied local "
        "CodeGenome connectome graph context. Prefer concrete files, symbols, dependency "
        "directions, risks, and next inspection steps. If the graph context is insufficient, "
        "say what is missing instead of guessing."
    )

    api_style = str(PROVIDERS[request.provider].get("api_style", request.provider))

    if api_style == "openai":
        payload = {
            "model": model,
            "max_tokens": MAX_RESPONSE_TOKENS,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": graph_context},
                *clean_messages,
            ],
        }
        response = _request_json(
            PROVIDERS[request.provider]["chat_url"],
            method="POST",
            headers=_provider_headers(request.provider, request.api_key),
            payload=payload,
            timeout=90,
        )
        answer = response["choices"][0]["message"]["content"]
    elif api_style == "google":
        url = PROVIDERS[request.provider]["chat_url"].format(
            model=urllib.parse.quote(model, safe="")
        )
        url = f"{url}?key={urllib.parse.quote(request.api_key)}"
        prompt = "\n\n".join(
            [
                system_prompt,
                graph_context,
                *_format_dialog_messages(clean_messages),
            ]
        )
        response = _request_json(
            url,
            method="POST",
            headers={"Content-Type": "application/json"},
            payload={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": MAX_RESPONSE_TOKENS},
            },
            timeout=90,
        )
        parts = response["candidates"][0]["content"].get("parts", [])
        answer = "".join(part.get("text", "") for part in parts)
    elif api_style == "ollama":
        payload = {
            "model": model,
            "stream": False,
            "options": {"num_predict": MAX_RESPONSE_TOKENS},
            "messages": [
                {"role": "system", "content": f"{system_prompt}\n\n{graph_context}"},
                *clean_messages,
            ],
        }
        response = _request_json(
            PROVIDERS[request.provider]["chat_url"],
            method="POST",
            headers={"Content-Type": "application/json"},
            payload=payload,
            timeout=90,
        )
        answer = response.get("message", {}).get("content", "")
    else:
        raise AIChatError(f"Unsupported provider: {provider}")

    if save_api_key and PROVIDERS[request.provider].get("requires_api_key", True):
        save_provider_key(genome_dir, request.provider, request.api_key)

    return answer.strip()


def build_graph_context(
    graph_json_path: Path,
    selected_node_id: str | None = None,
    context_size: str | None = None,
) -> str:
    """Build a compact text context from `.genome/graph.json`."""
    profile = _context_profile(context_size)
    try:
        graph = json.loads(graph_json_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AIChatError("No .genome graph JSON exists yet. Run codegenome analyze first.") from exc
    except json.JSONDecodeError as exc:
        raise AIChatError("The .genome graph JSON could not be parsed.") from exc

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    metadata = graph.get("metadata", {})
    stats = metadata.get("statistics", {}) if isinstance(metadata, dict) else {}

    node_by_id = {str(node.get("id", "")): node for node in nodes if node.get("id")}
    in_counts: dict[str, int] = {}
    out_counts: dict[str, int] = {}
    for edge in edges:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        out_counts[source] = out_counts.get(source, 0) + 1
        in_counts[target] = in_counts.get(target, 0) + 1

    ranked = sorted(
        node_by_id.values(),
        key=lambda node: (
            bool(node.get("is_bridge")),
            int(node.get("complexity") or 0),
            int(node.get("churn") or 0),
            in_counts.get(str(node.get("id")), 0) + out_counts.get(str(node.get("id")), 0),
        ),
        reverse=True,
    )

    lines = [
        "Current local CodeGenome connectome graph:",
        f"- context profile: {profile['name']}",
        f"- graph path: {graph_json_path.as_posix()}",
        "- statistics: "
        + json.dumps(
            stats
            or {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "file_count": sum(1 for node in nodes if node.get("node_type") == "file"),
                "symbol_count": sum(1 for node in nodes if node.get("node_type") == "symbol"),
            },
            sort_keys=True,
        ),
        "",
        "Important nodes:",
    ]
    for node in ranked[: int(profile["nodes"])]:
        lines.append(
            "- "
            + json.dumps(
                _compact_node_context(node, in_counts, out_counts, int(profile["value_chars"])),
                sort_keys=True,
            )
        )

    if selected_node_id and selected_node_id in node_by_id:
        selected = node_by_id[selected_node_id]
        neighbors = _neighbors_for_context(
            edges,
            node_by_id,
            selected_node_id,
            max_neighbors=int(profile["neighbors"]),
            value_chars=int(profile["value_chars"]),
        )
        lines.extend(
            [
                "",
                "Selected node:",
                json.dumps(
                    _compact_node_context(
                        selected,
                        in_counts,
                        out_counts,
                        int(profile["value_chars"]),
                    ),
                    sort_keys=True,
                ),
                "Selected node neighborhood:",
                json.dumps(neighbors, sort_keys=True),
            ]
        )

    lines.append("")
    lines.append("Representative edges:")
    for edge in edges[: int(profile["edges"])]:
        lines.append(
            "- "
            + json.dumps(
                {
                    "source": _truncate_context_value(edge.get("source"), int(profile["value_chars"])),
                    "target": _truncate_context_value(edge.get("target"), int(profile["value_chars"])),
                    "edge_type": edge.get("edge_type"),
                },
                sort_keys=True,
            )
        )

    context = _fit_context_lines(lines, int(profile["chars"]))
    if len(context) < len("\n".join(lines)):
        context += "\n\n[Graph context truncated to fit provider request limits.]"
    return context


def save_provider_key(genome_dir: Path, provider: str, api_key: str) -> None:
    """Persist an API key in `.genome/ai-chat.json`."""
    if provider not in PROVIDERS:
        raise AIChatError(f"Unsupported provider: {provider}")
    if not api_key:
        raise AIChatError("API key is required before it can be saved.")

    config = _read_config(genome_dir)
    api_keys = config.get("api_keys")
    if not isinstance(api_keys, dict):
        api_keys = {}
    api_keys[provider] = api_key
    config.update({"version": 1, "default_provider": provider, "api_keys": api_keys})
    _write_config(genome_dir, config)


def _provider_request(
    genome_dir: Path,
    provider: str,
    api_key: str | None,
) -> ProviderRequest:
    if provider not in PROVIDERS:
        raise AIChatError(f"Unsupported provider: {provider}")

    requires_api_key = PROVIDERS[provider].get("requires_api_key", True)
    resolved_key = (api_key or "").strip()
    if requires_api_key and not resolved_key:
        config = _read_config(genome_dir)
        api_keys = config.get("api_keys", {})
        if isinstance(api_keys, dict):
            resolved_key = str(api_keys.get(provider, "")).strip()

    if requires_api_key and not resolved_key:
        raise AIChatError("Enter an API key or save one for this provider first.")
    return ProviderRequest(provider=provider, api_key=resolved_key)


def _provider_headers(provider: str, api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = None
    headers = {**DEFAULT_HTTP_HEADERS, **headers}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", **headers}

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        detail = _provider_error_detail(body) or exc.reason
        raise AIChatError(f"Provider request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise AIChatError(f"Provider request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise AIChatError("Provider returned a response that was not JSON.") from exc


def _provider_error_detail(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body[:300]
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error)
    if isinstance(error, str):
        return error
    return body[:300]


def _clean_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    clean = []
    for message in messages[-12:]:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = str(message.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            clean.append({"role": role, "content": content})
    return clean


def _format_dialog_messages(messages: list[dict[str, str]]) -> list[str]:
    return [f"{message['role'].title()}: {message['content']}" for message in messages]


def _context_profile(context_size: str | None) -> dict[str, str | int]:
    name = str(context_size or DEFAULT_CONTEXT_SIZE).strip().lower()
    if name == "media":
        name = "medium"
    if name not in CONTEXT_PROFILES:
        name = DEFAULT_CONTEXT_SIZE
    return {"name": name, **CONTEXT_PROFILES[name]}


def _compact_node_context(
    node: dict[str, Any],
    in_counts: dict[str, int],
    out_counts: dict[str, int],
    value_chars: int = MAX_CONTEXT_VALUE_CHARS,
) -> dict[str, Any]:
    node_id = str(node.get("id", ""))
    return {
        "id": _truncate_context_value(node_id, value_chars),
        "name": _truncate_context_value(node.get("name"), value_chars),
        "type": node.get("node_type"),
        "file_path": _truncate_context_value(node.get("file_path"), value_chars),
        "qualified_name": _truncate_context_value(node.get("qualified_name"), value_chars),
        "complexity": node.get("complexity"),
        "churn": node.get("churn"),
        "is_bridge": node.get("is_bridge"),
        "incoming": in_counts.get(node_id, 0),
        "outgoing": out_counts.get(node_id, 0),
    }


def _truncate_context_value(value: Any, max_chars: int = MAX_CONTEXT_VALUE_CHARS) -> Any:
    if not isinstance(value, str) or len(value) <= max_chars:
        return value
    return value[: max_chars - 16] + "...[truncated]"


def _fit_context_lines(lines: list[str], max_chars: int) -> str:
    kept: list[str] = []
    total = 0
    for line in lines:
        line_length = len(line) + (1 if kept else 0)
        if total + line_length > max_chars:
            break
        kept.append(line)
        total += line_length
    return "\n".join(kept)


def _neighbors_for_context(
    edges: list[dict[str, Any]],
    node_by_id: dict[str, dict[str, Any]],
    selected_node_id: str,
    *,
    max_neighbors: int = MAX_NEIGHBORS,
    value_chars: int = MAX_CONTEXT_VALUE_CHARS,
) -> list[dict[str, Any]]:
    neighbors = []
    for edge in edges:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source != selected_node_id and target != selected_node_id:
            continue
        neighbor_id = target if source == selected_node_id else source
        neighbor = node_by_id.get(neighbor_id, {})
        neighbors.append(
            {
                "direction": "outgoing" if source == selected_node_id else "incoming",
                "edge_type": edge.get("edge_type"),
                "id": _truncate_context_value(neighbor_id, value_chars),
                "name": _truncate_context_value(neighbor.get("name"), value_chars),
                "type": neighbor.get("node_type"),
                "file_path": _truncate_context_value(neighbor.get("file_path"), value_chars),
                "qualified_name": _truncate_context_value(neighbor.get("qualified_name"), value_chars),
            }
        )
        if len(neighbors) >= max_neighbors:
            break
    return neighbors


def _read_config(genome_dir: Path) -> dict[str, Any]:
    path = genome_dir / CONFIG_FILENAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def _write_config(genome_dir: Path, config: dict[str, Any]) -> None:
    genome_dir.mkdir(parents=True, exist_ok=True)
    path = genome_dir / CONFIG_FILENAME
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass
    temp_path.replace(path)

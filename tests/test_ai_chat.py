import json
from pathlib import Path

from codegenome import ai_chat
from codegenome.ai_chat import build_graph_context, save_provider_key, settings_payload


def test_settings_payload_reports_saved_keys_without_exposing_values(tmp_path: Path) -> None:
    genome_dir = tmp_path / ".genome"
    save_provider_key(genome_dir, "openai", "sk-test")

    payload = settings_payload(genome_dir)

    assert payload["saved"]["openai"] is True
    assert "sk-test" not in json.dumps(payload)


def test_settings_payload_includes_new_chat_providers(tmp_path: Path) -> None:
    payload = settings_payload(tmp_path / ".genome")

    providers = {provider["id"]: provider for provider in payload["providers"]}

    assert list(providers) == ["openai", "google", "groq", "ollama", "ollama_cloud"]
    assert providers["openai"]["requires_api_key"] is True
    assert providers["google"]["requires_api_key"] is True
    assert providers["groq"]["requires_api_key"] is True
    assert providers["ollama"]["requires_api_key"] is False
    assert providers["ollama_cloud"]["requires_api_key"] is True
    assert "default_base_url" not in providers["ollama"]


def test_build_graph_context_includes_selected_node_neighborhood(tmp_path: Path) -> None:
    graph_path = tmp_path / ".genome" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(
        json.dumps(
            {
                "metadata": {"statistics": {"node_count": 2, "edge_count": 1}},
                "nodes": [
                    {"id": "a.py", "node_type": "file", "name": "a.py", "is_bridge": True},
                    {"id": "b.py", "node_type": "file", "name": "b.py"},
                ],
                "edges": [{"source": "a.py", "target": "b.py", "edge_type": "imports"}],
            }
        ),
        encoding="utf-8",
    )

    context = build_graph_context(graph_path, selected_node_id="a.py")

    assert "Selected node:" in context
    assert '"id": "a.py"' in context
    assert '"direction": "outgoing"' in context


def test_build_graph_context_caps_large_payloads(tmp_path: Path) -> None:
    graph_path = tmp_path / ".genome" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": f"file_{index}.py",
                        "node_type": "file",
                        "name": f"file_{index}.py",
                        "file_path": "src/" + ("very_long_path/" * 40) + f"file_{index}.py",
                        "qualified_name": "module." + ("very_long_symbol." * 40) + str(index),
                        "source": "x" * 5000,
                    }
                    for index in range(200)
                ],
                "edges": [
                    {
                        "source": f"file_{index}.py",
                        "target": f"file_{index + 1}.py",
                        "edge_type": "imports",
                    }
                    for index in range(199)
                ],
            }
        ),
        encoding="utf-8",
    )

    context = build_graph_context(graph_path, selected_node_id="file_0.py")

    assert len(context) <= ai_chat.MAX_CONTEXT_CHARS + 80
    assert "Import edges:" in context
    assert "...[truncated]" in context


def test_build_graph_context_profiles_change_budget(tmp_path: Path) -> None:
    graph_path = tmp_path / ".genome" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": f"file_{index}.py",
                        "node_type": "file",
                        "name": f"file_{index}.py",
                        "file_path": f"src/package/file_{index}.py",
                    }
                    for index in range(50)
                ],
                "edges": [
                    {
                        "source": f"file_{index}.py",
                        "target": f"file_{index + 1}.py",
                        "edge_type": "imports",
                    }
                    for index in range(49)
                ],
            }
        ),
        encoding="utf-8",
    )

    minimal = build_graph_context(graph_path, context_size="minimal")
    full = build_graph_context(graph_path, context_size="full")

    assert "- context profile: minimal" in minimal
    assert "- context profile: full" in full
    assert len(full) > len(minimal)


def test_build_graph_context_max_profile_includes_more_import_edges(tmp_path: Path) -> None:
    graph_path = tmp_path / ".genome" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(
        json.dumps(
            {
                "nodes": [
                    {"id": f"file_{index}.py", "node_type": "file", "name": f"file_{index}.py"}
                    for index in range(30)
                ],
                "edges": [
                    {
                        "source": f"file_{index}.py",
                        "target": f"import:file_{index}.py:1:dep_{index}",
                        "edge_type": "imports",
                    }
                    for index in range(30)
                ],
            }
        ),
        encoding="utf-8",
    )

    minimal = build_graph_context(graph_path, context_size="minimal")
    max_context = build_graph_context(graph_path, context_size="max")

    assert "- context profile: max" in max_context
    assert "Import edges:" in max_context
    assert max_context.count('"edge_type": "imports"') > minimal.count('"edge_type": "imports"')


def test_load_models_supports_keyless_ollama(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"models": [{"name": "llama3.2:latest"}, {"model": "codellama:latest"}]}

    monkeypatch.setattr(ai_chat, "_request_json", fake_request_json)

    models = ai_chat.load_models(tmp_path / ".genome", "ollama")

    assert calls[0][0] == "http://127.0.0.1:11434/api/tags"
    assert models == [
        {"id": "codellama:latest", "label": "codellama:latest"},
        {"id": "llama3.2:latest", "label": "llama3.2:latest"},
    ]


def test_load_models_supports_ollama_cloud(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"models": [{"model": "gpt-oss:120b"}]}

    monkeypatch.setattr(ai_chat, "_request_json", fake_request_json)

    models = ai_chat.load_models(tmp_path / ".genome", "ollama_cloud", "ollama-key")

    assert calls[0][0] == "https://ollama.com/api/tags"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer ollama-key"
    assert models == [{"id": "gpt-oss:120b", "label": "gpt-oss:120b"}]


def test_load_models_supports_groq(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"data": [{"id": "llama-3.3-70b-versatile"}]}

    monkeypatch.setattr(ai_chat, "_request_json", fake_request_json)

    models = ai_chat.load_models(tmp_path / ".genome", "groq", "gsk-test")

    assert calls[0][0] == "https://api.groq.com/openai/v1/models"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer gsk-test"
    assert models == [
        {"id": "llama-3.3-70b-versatile", "label": "llama-3.3-70b-versatile"}
    ]


def test_request_json_adds_provider_friendly_headers(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(ai_chat.urllib.request, "urlopen", fake_urlopen)

    ai_chat._request_json(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": "Bearer gsk-test"},
    )

    assert captured["headers"]["User-agent"].startswith("CodeGenome/")
    assert captured["headers"]["Accept"] == "application/json"
    assert captured["headers"]["Authorization"] == "Bearer gsk-test"


def test_chat_completion_supports_ollama_payload(monkeypatch, tmp_path: Path) -> None:
    graph_path = tmp_path / ".genome" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"message": {"content": "Local answer"}}

    monkeypatch.setattr(ai_chat, "_request_json", fake_request_json)

    answer = ai_chat.chat_completion(
        tmp_path / ".genome",
        graph_path,
        "ollama",
        "llama3.2:latest",
        [{"role": "user", "content": "What changed?"}],
    )

    assert answer == "Local answer"
    assert calls[0][0] == "http://127.0.0.1:11434/api/chat"
    assert calls[0][1]["payload"]["stream"] is False
    assert calls[0][1]["payload"]["options"]["num_predict"] == ai_chat.MAX_RESPONSE_TOKENS


def test_chat_completion_supports_ollama_cloud_auth(monkeypatch, tmp_path: Path) -> None:
    graph_path = tmp_path / ".genome" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"message": {"content": "Cloud answer"}}

    monkeypatch.setattr(ai_chat, "_request_json", fake_request_json)

    answer = ai_chat.chat_completion(
        tmp_path / ".genome",
        graph_path,
        "ollama_cloud",
        "gpt-oss:120b",
        [{"role": "user", "content": "What changed?"}],
        "ollama-key",
    )

    assert answer == "Cloud answer"
    assert calls[0][0] == "https://ollama.com/api/chat"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer ollama-key"
    assert calls[0][1]["payload"]["stream"] is False


def test_chat_completion_caps_openai_compatible_output(monkeypatch, tmp_path: Path) -> None:
    graph_path = tmp_path / ".genome" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"choices": [{"message": {"content": "Answer"}}]}

    monkeypatch.setattr(ai_chat, "_request_json", fake_request_json)

    answer = ai_chat.chat_completion(
        tmp_path / ".genome",
        graph_path,
        "groq",
        "llama-3.3-70b-versatile",
        [{"role": "user", "content": "Which files should split?"}],
        "gsk-test",
    )

    assert answer == "Answer"
    assert calls[0][1]["payload"]["max_tokens"] == ai_chat.MAX_RESPONSE_TOKENS
    assert "- context profile: small" in calls[0][1]["payload"]["messages"][1]["content"]


def test_chat_completion_uses_requested_context_profile(monkeypatch, tmp_path: Path) -> None:
    graph_path = tmp_path / ".genome" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    calls = []

    def fake_request_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"choices": [{"message": {"content": "Answer"}}]}

    monkeypatch.setattr(ai_chat, "_request_json", fake_request_json)

    ai_chat.chat_completion(
        tmp_path / ".genome",
        graph_path,
        "openai",
        "gpt-4o-mini",
        [{"role": "user", "content": "Use more context"}],
        "sk-test",
        context_size="full",
    )

    context = calls[0][1]["payload"]["messages"][1]["content"]
    assert "- context profile: full" in context

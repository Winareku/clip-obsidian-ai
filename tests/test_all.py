"""
tests/test_all.py
-----------------
Unit & integration tests for clip-obsidian-ai.

Run with:  python -m pytest tests/ -v
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Make the project root importable ─────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))


# ══════════════════════════════════════════════════════════════════════════════
# Config Manager Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestConfigManager:
    def test_load_config_returns_app_config(self):
        from config_manager import load_config, AppConfig
        cfg = load_config()
        assert isinstance(cfg, AppConfig)

    def test_default_llm_values(self):
        from config_manager import LLMConfig
        cfg = LLMConfig()
        assert cfg.provider == "ollama"
        assert cfg.timeout == 120
        assert cfg.max_input_chars == 12000

    def test_load_format_template_missing_file(self):
        from config_manager import load_format_template, AppConfig
        cfg = AppConfig()
        cfg.format_file = Path("/nonexistent/format.md")
        result = load_format_template(cfg)
        assert result == ""

    def test_load_format_template_reads_file(self, tmp_path):
        from config_manager import load_format_template, AppConfig
        fmt_file = tmp_path / "format.md"
        fmt_file.write_text("# System Prompt\nBe concise.")
        cfg = AppConfig()
        cfg.format_file = fmt_file
        result = load_format_template(cfg)
        assert "System Prompt" in result


# ══════════════════════════════════════════════════════════════════════════════
# Extractor Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestTXTExtractor:
    def test_extracts_utf8(self, tmp_path):
        from extractors import TXTExtractor
        f = tmp_path / "test.txt"
        f.write_text("Hello, world!\nLine 2.", encoding="utf-8")
        extractor = TXTExtractor()
        result = extractor.extract_text(str(f))
        assert "Hello, world!" in result
        assert "Line 2." in result

    def test_extracts_latin1(self, tmp_path):
        from extractors import TXTExtractor
        f = tmp_path / "test.txt"
        f.write_bytes("Ñoño".encode("latin-1"))
        extractor = TXTExtractor()
        result = extractor.extract_text(str(f))
        assert len(result) > 0  # Should not crash

    def test_empty_file(self, tmp_path):
        from extractors import TXTExtractor
        f = tmp_path / "empty.txt"
        f.write_text("")
        extractor = TXTExtractor()
        assert extractor.extract_text(str(f)) == ""


class TestExtractorFactory:
    def test_unsupported_extension_returns_empty(self, tmp_path):
        from extractors import ExtractorFactory
        f = tmp_path / "file.xyz"
        f.write_text("content")
        result = ExtractorFactory.extract(str(f))
        assert result == ""

    def test_txt_routed_correctly(self, tmp_path):
        from extractors import ExtractorFactory, TXTExtractor
        f = tmp_path / "file.txt"
        f.write_text("test content")
        extractor = ExtractorFactory.get_extractor(str(f))
        assert isinstance(extractor, TXTExtractor)

    def test_md_routed_to_txt_extractor(self, tmp_path):
        from extractors import ExtractorFactory, TXTExtractor
        f = tmp_path / "notes.md"
        f.write_text("# Title\nContent")
        extractor = ExtractorFactory.get_extractor(str(f))
        assert isinstance(extractor, TXTExtractor)

    def test_register_custom_extractor(self):
        from extractors import ExtractorFactory, TXTExtractor
        ExtractorFactory.register(".rst", TXTExtractor)
        assert ".rst" in ExtractorFactory.supported_extensions()

    def test_safe_extract_returns_empty_on_error(self, tmp_path):
        from extractors import BaseExtractor

        class BrokenExtractor(BaseExtractor):
            def extract_text(self, file_path: str) -> str:
                raise RuntimeError("Simulated failure")

        extractor = BrokenExtractor()
        result = extractor._safe_extract("/any/path.txt")
        assert result == ""

    def test_pdf_extractor_exists(self):
        from extractors import PDFExtractor
        assert PDFExtractor is not None

    def test_pptx_extractor_exists(self):
        from extractors import PPTXExtractor
        assert PPTXExtractor is not None

    def test_docx_extractor_exists(self):
        from extractors import DocxExtractor
        assert DocxExtractor is not None


# ══════════════════════════════════════════════════════════════════════════════
# Adapter Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestNullUIAdapter:
    def test_always_confirms(self):
        from adapters import NullUIAdapter
        adapter = NullUIAdapter()
        assert adapter.confirm("msg", "yes", "no") is True


class TestNullNotifierAdapter:
    def test_does_not_crash(self):
        from adapters import NullNotifierAdapter
        adapter = NullNotifierAdapter()
        adapter.notify("title", "body")  # Should not raise


class TestOllamaAdapter:
    def test_build_payload_includes_system(self):
        from adapters import OllamaAdapter
        adapter = OllamaAdapter(model="test")
        payload = adapter._build_payload("user msg", "system msg")
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"

    def test_build_payload_skips_empty_system(self):
        from adapters import OllamaAdapter
        adapter = OllamaAdapter(model="test")
        payload = adapter._build_payload("user msg", "")
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

    def test_parse_response_success(self):
        import json
        from adapters import OllamaAdapter
        raw = json.dumps({"message": {"role": "assistant", "content": "  Hello!  "}})
        result = OllamaAdapter._parse_response(raw)
        assert result == "Hello!"

    def test_parse_response_invalid_raises(self):
        from adapters import OllamaAdapter
        with pytest.raises(ValueError):
            OllamaAdapter._parse_response("not json")

    def test_load_system_prompt_from_file(self, tmp_path):
        from adapters import OllamaAdapter
        fmt = tmp_path / "format.md"
        fmt.write_text("Be a helpful assistant.")
        adapter = OllamaAdapter(model="test", format_file=fmt)
        result = adapter._load_system_prompt("fallback")
        assert result == "Be a helpful assistant."

    def test_load_system_prompt_falls_back(self):
        from adapters import OllamaAdapter
        adapter = OllamaAdapter(model="test", format_file=Path("/nonexistent"))
        result = adapter._load_system_prompt("fallback text")
        assert result == "fallback text"

    def test_generate_calls_ollama(self):
        """Mock the HTTP call and verify the response is parsed correctly."""
        import json
        from adapters import OllamaAdapter
        from unittest.mock import patch, MagicMock

        fake_response_body = json.dumps({
            "message": {"role": "assistant", "content": "Mocked result"}
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = fake_response_body

        adapter = OllamaAdapter(model="llama3.2")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = adapter.generate("test prompt", "system")

        assert result == "Mocked result"


class TestAdapterFactory:
    def test_build_ui_returns_null_when_no_backend(self):
        from adapters import AdapterFactory, NullUIAdapter
        with patch("shutil.which", return_value=None):
            ui = AdapterFactory.build_ui("auto", prompt="p", confirm="y", cancel="n")
        assert isinstance(ui, NullUIAdapter)

    def test_build_notifier_disabled(self):
        from adapters import AdapterFactory, NullNotifierAdapter
        notifier = AdapterFactory.build_notifier(
            enabled=False, backend="notify-send", app_name="test", timeout_ms=3000
        )
        assert isinstance(notifier, NullNotifierAdapter)

    def test_build_llm_unknown_provider_raises(self):
        from adapters import AdapterFactory
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            AdapterFactory.build_llm("gpt-99", "model", "http://x", 30)

    def test_build_llm_mock_provider(self):
        from adapters import AdapterFactory, MockLLMAdapter
        llm = AdapterFactory.build_llm("mock", "any-model", "http://x", 30)
        assert isinstance(llm, MockLLMAdapter)

    def test_build_llm_mock_model(self):
        from adapters import AdapterFactory, MockLLMAdapter
        llm = AdapterFactory.build_llm("ollama", "mock", "http://x", 30)
        assert isinstance(llm, MockLLMAdapter)


class TestMockLLMAdapter:
    def test_generate_returns_mocked_markdown(self):
        from adapters import MockLLMAdapter
        adapter = MockLLMAdapter()
        res = adapter.generate("Hello computer")
        assert "Resumen de IA Simulado" in res
        assert "Hello computer..." in res


class TestGeminiAdapter:
    def test_generate_calls_gemini_api(self):
        import json
        from adapters import GeminiAdapter
        from unittest.mock import patch, MagicMock

        fake_response_body = json.dumps({
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Gemini generated text"}
                        ]
                    }
                }
            ]
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = fake_response_body

        adapter = GeminiAdapter(api_key="fake_key", model="gemini-1.5-flash")

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = adapter.generate("Hello Gemini", "System prompt")
            
            mock_urlopen.assert_called_once()
            args, kwargs = mock_urlopen.call_args
            req = args[0]
            assert req.full_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=fake_key"
            assert req.method == "POST"
            
            payload = json.loads(req.data.decode("utf-8"))
            assert payload["contents"][0]["parts"][0]["text"] == "Hello Gemini"
            assert payload["systemInstruction"]["parts"][0]["text"] == "System prompt"

        assert result == "Gemini generated text"


class TestResilientLLM:
    def test_build_resilient_llm_chooses_ollama_if_online(self):
        from adapters import AdapterFactory, OllamaAdapter
        from config_manager import AppConfig
        from unittest.mock import patch, MagicMock

        config = AppConfig()
        config.llm.provider = "auto"
        config.llm.host = "http://localhost:11434"

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.status = 200

        with patch("urllib.request.urlopen", return_value=mock_resp):
            llm = AdapterFactory.build_resilient_llm(config)

        assert isinstance(llm, OllamaAdapter)

    def test_build_resilient_llm_falls_back_to_gemini(self):
        from adapters import AdapterFactory, GeminiAdapter
        from config_manager import AppConfig
        from unittest.mock import patch

        config = AppConfig()
        config.llm.provider = "auto"
        config.llm.api_key = "test_key"
        config.llm.host = "http://localhost:11434"

        with patch("urllib.request.urlopen", side_effect=Exception("Ollama down")):
            llm = AdapterFactory.build_resilient_llm(config)

        assert isinstance(llm, GeminiAdapter)
        assert llm._api_key == "test_key"

    def test_build_resilient_llm_falls_back_to_mock_if_no_key_and_ollama_down(self):
        from adapters import AdapterFactory, MockLLMAdapter
        from config_manager import AppConfig
        from unittest.mock import patch

        config = AppConfig()
        config.llm.provider = "auto"
        config.llm.api_key = ""
        config.llm.host = "http://localhost:11434"

        with patch("urllib.request.urlopen", side_effect=Exception("Ollama down")):
            llm = AdapterFactory.build_resilient_llm(config)

        assert isinstance(llm, MockLLMAdapter)


# ══════════════════════════════════════════════════════════════════════════════
# Clip Mode Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestClipMode:
    def _make_mode(self, clipboard_text="Test content.", confirm=True, llm_result="## Result"):
        from modes.clip_mode import ClipMode
        from config_manager import load_config

        cfg = load_config()
        clipboard = MagicMock()
        clipboard.read.return_value = clipboard_text
        ui = MagicMock()
        ui.confirm.return_value = confirm
        llm = MagicMock()
        llm.generate.return_value = llm_result
        notifier = MagicMock()

        mode = ClipMode(cfg, clipboard, ui, llm, notifier)
        return mode, clipboard, ui, llm, notifier

    def test_empty_clipboard_returns_1(self):
        mode, *_ = self._make_mode(clipboard_text="")
        assert mode.run() == 1

    def test_user_cancels_returns_1(self):
        mode, *_ = self._make_mode(confirm=False)
        assert mode.run() == 1

    def test_success_writes_to_clipboard(self):
        mode, clipboard, ui, llm, notifier = self._make_mode()
        result = mode.run()
        assert result == 0
        clipboard.write.assert_called_once_with("## Result")

    def test_llm_error_returns_2(self):
        mode, clipboard, ui, llm, notifier = self._make_mode()
        llm.generate.side_effect = ConnectionError("Ollama down")
        assert mode.run() == 2

    def test_preview_truncated(self):
        from modes.clip_mode import ClipMode
        from config_manager import load_config
        cfg = load_config()
        cfg.ui.preview_chars = 10
        mode = ClipMode(cfg, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        preview = mode._build_preview("A" * 50)
        assert "…" in preview
        assert len(preview) < 50 + 20  # short + suffix

    def test_input_truncated_at_limit(self):
        from modes.clip_mode import ClipMode
        from config_manager import load_config
        cfg = load_config()
        cfg.llm.max_input_chars = 10
        mode = ClipMode(cfg, MagicMock(), MagicMock(), MagicMock(), MagicMock())
        result = mode._maybe_truncate("A" * 100)
        assert len(result) == 10


# ══════════════════════════════════════════════════════════════════════════════
# Dir Mode Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDirMode:
    def test_no_files_returns_1(self, tmp_path):
        from modes.dir_mode import DirMode
        from config_manager import load_config
        cfg = load_config()
        llm = MagicMock()
        mode = DirMode(cfg, llm)
        result = mode.run(target_dir=tmp_path)
        assert result == 1

    def test_processes_txt_file(self, tmp_path):
        from modes.dir_mode import DirMode
        from config_manager import load_config
        cfg = load_config()

        (tmp_path / "notes.txt").write_text("Hello world content here.")
        llm = MagicMock()
        llm.generate.return_value = "## Summary\nGreat notes."

        mode = DirMode(cfg, llm)
        result = mode.run(target_dir=tmp_path)

        assert result == 0
        output = tmp_path / cfg.dir_mode.output_filename
        assert output.exists()
        assert "Summary" in output.read_text()

    def test_output_has_metadata_header(self, tmp_path):
        from modes.dir_mode import DirMode
        from config_manager import load_config
        cfg = load_config()

        (tmp_path / "doc.txt").write_text("Some text.")
        llm = MagicMock()
        llm.generate.return_value = "# Notes"

        DirMode(cfg, llm).run(target_dir=tmp_path)
        content = (tmp_path / cfg.dir_mode.output_filename).read_text()
        assert "generado:" in content
        assert "clip-obsidian-ai" in content

    def test_llm_failure_returns_2(self, tmp_path):
        from modes.dir_mode import DirMode
        from config_manager import load_config
        cfg = load_config()

        (tmp_path / "doc.txt").write_text("content")
        llm = MagicMock()
        llm.generate.side_effect = ConnectionError("No Ollama")

        mode = DirMode(cfg, llm)
        result = mode.run(target_dir=tmp_path)
        assert result == 2

    def test_output_file_excluded_from_scan(self, tmp_path):
        from modes.dir_mode import DirMode
        from config_manager import load_config
        cfg = load_config()

        # Create output file from a previous run
        (tmp_path / cfg.dir_mode.output_filename).write_text("# Old notes")
        (tmp_path / "real_doc.txt").write_text("Actual content")
        llm = MagicMock()
        llm.generate.return_value = "# New notes"

        mode = DirMode(cfg, llm)
        files = mode._discover_files(tmp_path, set(cfg.dir_mode.supported_extensions))

        names = [f.name for f in files]
        assert cfg.dir_mode.output_filename not in names
        assert "real_doc.txt" in names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

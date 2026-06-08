from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_local_frontend_dev_server_uses_5174() -> None:
    vite_config = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")

    assert "port: 5174" in vite_config
    assert "strictPort: true" in vite_config


def test_backend_cors_allows_local_frontend_5174() -> None:
    backend_main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")

    assert "http://localhost:5174" in backend_main
    assert "http://127.0.0.1:5174" in backend_main
    assert "http://localhost:5173" not in backend_main


def test_local_startup_docs_limit_reload_to_backend_and_src() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    startup_doc = (ROOT / "启动.txt").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    safe_reload = "--reload --reload-dir backend --reload-dir src"

    assert safe_reload in readme
    assert safe_reload in startup_doc
    assert safe_reload in contributing
    assert "http://localhost:5174" in readme
    assert "http://localhost:5174" in startup_doc
    assert "http://localhost:5173" not in readme
    assert "http://localhost:5173" not in startup_doc

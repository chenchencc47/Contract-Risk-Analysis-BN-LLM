from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_backend_dockerfile_runs_backend_main_on_9527() -> None:
    dockerfile_path = ROOT / "backend" / "Dockerfile"

    assert dockerfile_path.exists()

    content = dockerfile_path.read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in content
    assert 'CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "9527"]' in content
    assert "COPY backend /app/backend" in content
    assert "COPY src /app/src" in content


def test_frontend_dockerfile_builds_vite_and_serves_with_nginx() -> None:
    dockerfile_path = ROOT / "frontend" / "Dockerfile"

    assert dockerfile_path.exists()

    content = dockerfile_path.read_text(encoding="utf-8")

    assert "FROM node:20-alpine AS build" in content
    assert "RUN npm ci" in content
    assert "RUN npm run build" in content
    assert "FROM nginx:1.27-alpine" in content
    assert "COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf" in content


def test_docker_compose_configures_frontend_backend_mysql() -> None:
    compose_path = ROOT / "docker-compose.yml"

    assert compose_path.exists()

    content = compose_path.read_text(encoding="utf-8")

    assert "frontend:" in content
    assert "backend:" in content
    assert "mysql:" in content
    assert "9527:9527" in content
    assert "80:80" in content
    assert "3306:3306" in content
    assert "./frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" in content
    assert "./docker/mysql/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" in content


def test_frontend_nginx_proxies_api_to_backend() -> None:
    nginx_path = ROOT / "frontend" / "nginx.conf"

    assert nginx_path.exists()

    content = nginx_path.read_text(encoding="utf-8")

    assert "location /api/" in content
    assert "proxy_pass http://backend:9527;" in content
    assert "try_files $uri /index.html;" in content


def test_mysql_init_sql_creates_required_tables() -> None:
    init_sql_path = ROOT / "docker" / "mysql" / "init.sql"

    assert init_sql_path.exists()

    content = init_sql_path.read_text(encoding="utf-8")

    for table_name in (
        "contracts",
        "reports",
        "report_risks",
        "report_counterfactuals",
        "company_redlines",
        "bn_feedback",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in content

    assert "UNIQUE KEY uk_contract_name (contract_name)" in content
    assert "UNIQUE KEY uk_report_version (contract_id, review_party, report_version)" in content
    assert "UNIQUE KEY uk_company_redline (contract_type, rule_id)" in content

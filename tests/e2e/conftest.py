"""Фикстуры для e2e-тестов: проверяет, что docker compose стек поднят, иначе skip."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest

try:
    import requests  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]


BASE_URL = os.environ.get("VKR_E2E_BASE_URL", "http://localhost")
HEALTH_TIMEOUT = float(os.environ.get("VKR_E2E_HEALTH_TIMEOUT", "5"))


def pytest_collection_modifyitems(config, items):
    """Все тесты в этой папке — с маркером e2e."""
    e2e_root = Path(__file__).parent.resolve()
    for item in items:
        item_path = Path(str(getattr(item, "path", item.fspath))).resolve()
        if item_path.parent == e2e_root:
            item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def live_stack(base_url):
    """Проверяет доступность стека. Если не поднят — skip всех e2e тестов."""
    if requests is None:
        pytest.skip("requests не установлен")
    try:
        # /api/v1/auth/me без токена → 401 (значит API работает)
        r = requests.get(f"{base_url}/api/v1/auth/me", timeout=HEALTH_TIMEOUT)
        if r.status_code not in (401, 403):
            pytest.skip(f"стек ответил {r.status_code}, ожидался 401/403 на /auth/me")
    except Exception as exc:
        pytest.skip(f"стек не доступен на {base_url}: {exc}")
    return base_url


@pytest.fixture(scope="module")
def student_session(live_stack):
    """Регистрирует свежего студента, логинит, возвращает (email, headers, user_id)."""
    email = f"e2e-{uuid.uuid4().hex[:10]}@example.com"
    password = "Passw0rd!Strong"

    r = requests.post(f"{live_stack}/api/v1/auth/register", json={
        "email": email,
        "full_name": "E2E Тестовый Студент",
        "password": password,
    }, timeout=10)
    if r.status_code == 429:
        pytest.skip("rate-limit на /register — подождите минуту между запусками")
    assert r.status_code in (200, 201), f"register: {r.status_code} {r.text}"
    user = r.json()

    r = requests.post(f"{live_stack}/api/v1/auth/login", json={
        "email": email, "password": password,
    }, timeout=10)
    if r.status_code == 429:
        pytest.skip("rate-limit на /login")
    assert r.status_code == 200, f"login: {r.status_code} {r.text}"
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    return {"email": email, "user_id": user["id"], "headers": headers, "tokens": tokens}


@pytest.fixture
def all_violations_docx() -> Path:
    p = Path(__file__).parent.parent / "fixtures" / "all_violations.docx"
    if not p.is_file():
        pytest.skip(f"fixture {p} отсутствует")
    return p


def wait_for_document_completion(
    base_url: str,
    headers: dict,
    document_id: str,
    *,
    timeout: float = 60.0,
    poll_interval: float = 1.0,
) -> dict:
    """Поллит /status пока статус не станет completed/failed либо не выйдет таймаут."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(f"{base_url}/api/v1/documents/{document_id}/status",
                         headers=headers, timeout=10)
        if r.status_code != 200:
            time.sleep(poll_interval)
            continue
        data = r.json()
        status = data.get("status")
        if status in ("done", "completed", "ready", "failed", "error"):
            return data
        time.sleep(poll_interval)
    raise TimeoutError(f"document {document_id} не пришёл в completed за {timeout}s")

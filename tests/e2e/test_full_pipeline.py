"""E2E: загрузка → обработка → скачивание → правка → ревью.

Требует поднятого docker compose стека (api/worker/postgres/redis/minio/nginx).
По умолчанию обращается к http://localhost (см. VKR_E2E_BASE_URL).
Если стек не поднят — все тесты пропускаются (см. conftest.live_stack).
Запуск: pytest -m e2e tests/e2e/
"""

from __future__ import annotations

import io
import zipfile

import pytest

requests = pytest.importorskip("requests")

from tests.e2e.conftest import wait_for_document_completion  # noqa: E402


def test_register_and_login_roundtrip(student_session, live_stack):
    """Регистрация → логин → /me возвращает того же пользователя."""
    r = requests.get(f"{live_stack}/api/v1/auth/me", headers=student_session["headers"], timeout=10)
    assert r.status_code == 200
    me = r.json()
    assert me["id"] == student_session["user_id"]
    assert me["email"] == student_session["email"]
    assert me["role"] == "student"


def test_upload_processes_and_returns_violations(
    student_session, live_stack, all_violations_docx,
):
    """Загрузка all_violations.docx → ожидание completed → есть нарушения по типам."""
    with open(all_violations_docx, "rb") as fh:
        files = {"file": (all_violations_docx.name, fh,
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        r = requests.post(f"{live_stack}/api/v1/documents/upload",
                          headers=student_session["headers"], files=files, timeout=30)
    assert r.status_code in (200, 201), f"upload: {r.status_code} {r.text}"
    document_id = r.json()["document"]["id"]

    final_status = wait_for_document_completion(
        live_stack, student_session["headers"], document_id, timeout=120.0,
    )
    assert final_status["status"] in ("done", "completed", "ready"), final_status

    r = requests.get(f"{live_stack}/api/v1/violations/{document_id}",
                     headers=student_session["headers"], timeout=10)
    assert r.status_code == 200, r.text
    violations = r.json()
    assert len(violations) > 0, "ожидались нарушения в all_violations.docx"

    types = {v["type"] for v in violations}
    expected_categories = {"citation_separator_missing", "bibliography_entries_unrecognised"}
    assert types & expected_categories, f"не нашлись ожидаемые типы: {types}"


def test_download_processed_docx_is_valid_zip(
    student_session, live_stack, all_violations_docx,
):
    """После обработки processed.docx можно скачать и это валидный ZIP с word/document.xml."""
    with open(all_violations_docx, "rb") as fh:
        files = {"file": (all_violations_docx.name, fh,
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        r = requests.post(f"{live_stack}/api/v1/documents/upload",
                          headers=student_session["headers"], files=files, timeout=30)
    document_id = r.json()["document"]["id"]

    wait_for_document_completion(
        live_stack, student_session["headers"], document_id, timeout=180.0,
    )

    r = requests.get(f"{live_stack}/api/v1/documents/{document_id}/download/processed",
                     headers=student_session["headers"], timeout=30)
    assert r.status_code == 200
    assert len(r.content) > 1000, "processed.docx подозрительно мал"

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
        assert "word/document.xml" in names, f"не похож на .docx: {names[:5]}"


def test_unauthorized_access_returns_401(live_stack):
    """Без токена /documents возвращает 401."""
    r = requests.get(f"{live_stack}/api/v1/documents/", timeout=10)
    assert r.status_code in (401, 403)


def test_jwt_invalid_token_rejected(live_stack):
    """Битый JWT отбивается со статусом 401."""
    r = requests.get(f"{live_stack}/api/v1/auth/me",
                     headers={"Authorization": "Bearer not-a-real-token"}, timeout=10)
    assert r.status_code == 401


def test_logout_invalidates_token(live_stack):
    """После logout прежний access-токен не работает (попадает в blacklist Redis).

    Использует собственную регистрацию — иначе сломает session-scoped student_session.
    """
    import uuid
    email = f"e2e-logout-{uuid.uuid4().hex[:10]}@example.com"
    password = "Passw0rd!Strong"
    r = requests.post(f"{live_stack}/api/v1/auth/register", json={
        "email": email, "full_name": "Logout Test", "password": password,
    }, timeout=10)
    if r.status_code == 429:
        pytest.skip("rate limit на /register, пропускаем")
    assert r.status_code in (200, 201)
    r = requests.post(f"{live_stack}/api/v1/auth/login", json={
        "email": email, "password": password,
    }, timeout=10)
    assert r.status_code == 200
    tokens = r.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    r = requests.post(f"{live_stack}/api/v1/auth/logout",
                      headers=headers, json={"refresh_token": tokens["refresh_token"]}, timeout=10)
    assert r.status_code == 204
    r = requests.get(f"{live_stack}/api/v1/auth/me", headers=headers, timeout=10)
    assert r.status_code == 401, "токен должен быть отозван после logout"


def test_delete_document_removes_it_from_list(student_session, live_stack, all_violations_docx):
    """После DELETE документ исчезает из GET /documents."""
    with open(all_violations_docx, "rb") as fh:
        files = {"file": ("delete-me.docx", fh,
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        r = requests.post(f"{live_stack}/api/v1/documents/upload",
                          headers=student_session["headers"], files=files, timeout=30)
    document_id = r.json()["document"]["id"]
    wait_for_document_completion(
        live_stack, student_session["headers"], document_id, timeout=180.0,
    )

    r = requests.delete(f"{live_stack}/api/v1/documents/{document_id}",
                        headers=student_session["headers"], timeout=10)
    assert r.status_code == 204

    r = requests.get(f"{live_stack}/api/v1/documents/{document_id}",
                     headers=student_session["headers"], timeout=10)
    assert r.status_code == 404

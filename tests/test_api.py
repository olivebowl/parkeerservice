"""Tests for the portal client."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import aiohttp
import pytest
from aioresponses import aioresponses
from custom_components.parkeerservice.api import (
    AuthError,
    ParkeerserviceClient,
    ParkeerserviceError,
    normalize_plate,
)
from yarl import URL

HOST = "https://park.example"
SESSIONS_URL = f"{HOST}/Customer/SessionsOverview/GetParkingSessions/"
LOGIN_PAGE = '<input name="__RequestVerificationToken" type="hidden" value="tok123" />'
PLAN_PAGE = (
    r"planSession.init('{\"customerId\":567,\"permitList\":[{\"id\":123,"
    r"\"permitProductId\":99,\"permitProduct\":\"Bewonersvergunning 1e\"}]}"
    "');"
)
SESSIONS = {
    "data": [{"id": 1, "lp": "AB-123-C", "isActive": True, "timeEndUtc": "2026-01-01T10:00:00"}]
}


@pytest.fixture
async def client() -> AsyncGenerator[ParkeerserviceClient]:
    async with aiohttp.ClientSession() as http:
        yield ParkeerserviceClient(http, HOST + "/", "me@x.nl", "p&ss")


def mock_login(m: aioresponses, plan_page: str = PLAN_PAGE) -> None:
    m.get(HOST, body=LOGIN_PAGE)
    m.post(HOST, body="ok")
    m.get(f"{HOST}/Customer/PlanSession", body=plan_page)


def test_normalize_plate() -> None:
    assert normalize_plate("ab-123 c") == "AB123C"


async def test_login(client: ParkeerserviceClient) -> None:
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        (call,) = m.requests[("POST", URL(HOST))]
    assert "__RequestVerificationToken=tok123" in call.kwargs["data"]
    assert "Password=p%26ss" in call.kwargs["data"]
    assert client.customer_id == 567
    assert [(p.id, p.product_id, p.name) for p in client.permits] == [
        (123, 99, "Bewonersvergunning 1e")
    ]


async def test_login_missing_token(client: ParkeerserviceClient) -> None:
    with aioresponses() as m:
        m.get(HOST, body="nothing here")
        with pytest.raises(ParkeerserviceError, match="token"):
            await client.login()


async def test_login_wrong_password(client: ParkeerserviceClient) -> None:
    with aioresponses() as m:
        mock_login(m, plan_page="login page again")
        with pytest.raises(AuthError):
            await client.login()


async def test_login_bad_permits(client: ParkeerserviceClient) -> None:
    with aioresponses() as m:
        mock_login(m, plan_page=r"\"customerId\":1 planSession.init('{\"nope\":1}');")
        with pytest.raises(ParkeerserviceError, match="permits"):
            await client.login()


async def test_get_sessions(client: ParkeerserviceClient) -> None:
    with aioresponses() as m:
        m.post(SESSIONS_URL, payload=SESSIONS)
        sessions = await client.get_sessions()
    assert len(sessions) == 1
    assert sessions[0].plate == "AB123C"
    assert sessions[0].active
    assert sessions[0].end == datetime(2026, 1, 1, 10, tzinfo=UTC)


async def test_get_sessions_expired(client: ParkeerserviceClient) -> None:
    with aioresponses() as m:
        m.post(SESSIONS_URL, body="<html>login</html>", content_type="text/html")
        with pytest.raises(AuthError):
            await client.get_sessions()


async def test_get_sessions_malformed(client: ParkeerserviceClient) -> None:
    with aioresponses() as m:
        m.post(SESSIONS_URL, payload={"data": [{"id": 1}]})
        with pytest.raises(ParkeerserviceError, match="sessions"):
            await client.get_sessions()


async def test_http_error(client: ParkeerserviceClient) -> None:
    with aioresponses() as m:
        m.post(SESSIONS_URL, status=500)
        m.post(f"{HOST}/Customer/SessionsOverview/StopParkingSession", status=500, body="bad")
        with pytest.raises(ParkeerserviceError, match="500"):
            await client.get_sessions()
        with pytest.raises(ParkeerserviceError, match="500"):
            await client.stop(1)


async def test_connection_error(client: ParkeerserviceClient) -> None:
    with aioresponses() as m:
        m.post(
            f"{HOST}/Customer/SessionsOverview/StopParkingSession",
            exception=aiohttp.ClientConnectionError("boom"),
        )
        m.post(SESSIONS_URL, exception=aiohttp.ClientConnectionError("boom"))
        with pytest.raises(ParkeerserviceError, match="boom"):
            await client.stop(1)
        with pytest.raises(ParkeerserviceError, match="boom"):
            await client.get_sessions()


async def test_start_and_stop(client: ParkeerserviceClient) -> None:
    start_url = f"{HOST}/Customer/PlanSession/StartParkingSession"
    stop_url = f"{HOST}/Customer/SessionsOverview/StopParkingSession"
    with aioresponses() as m:
        mock_login(m)
        await client.login()
        m.post(start_url, body="ok")
        m.post(stop_url, body="ok")
        end = datetime(2026, 1, 1, 22, tzinfo=UTC)
        await client.start("ab-123-c", "Bewonersvergunning 1e", end)
        await client.stop(7)
        (start_call,) = m.requests[("POST", URL(start_url))]
        (stop_call,) = m.requests[("POST", URL(stop_url))]
    body = start_call.kwargs["json"]
    assert body["lp"] == "AB123C"
    assert body["permitId"] == 123
    assert body["timeEnd"] == "2026-01-01T22:00:00+00:00"
    assert stop_call.kwargs["json"] == {"parkingSessionId": 7}


async def test_start_unknown_permit(client: ParkeerserviceClient) -> None:
    with pytest.raises(ParkeerserviceError, match="not found"):
        await client.start("AB123C", "nope", datetime.now(UTC))

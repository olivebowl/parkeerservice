"""Minimal async client for the parkeerservice web portal."""

from __future__ import annotations

import json
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

import aiohttp

if TYPE_CHECKING:
    from aiohttp import ClientResponse


class ParkeerserviceError(Exception):
    """Something went wrong talking to the service."""


class AuthError(ParkeerserviceError):
    """Login failed or the login session has expired."""


_TOKEN_RE: Final = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')
_CUSTOMER_RE: Final = re.compile(r'\\+"customerId\\+":\s*(\d+)')
_PERMITS_RE: Final = re.compile(r"planSession\.init\('([^']*)'\)")
_PLATE_SEPARATORS_RE: Final = re.compile(r"[\s-]")
_TIME_FORMAT: Final = "%Y-%m-%dT%H:%M:%S"

type _Request = AbstractAsyncContextManager[ClientResponse]


@dataclass(frozen=True)
class Permit:
    """A parking permit assigned to the account.

    Attributes:
        id: Id set by the portal for this permit.
        product_id: Id of the permit product, e.g. residents or visitors.
        name: Human readable permit name, as shown in the portal.
    """

    id: int
    product_id: int
    name: str


@dataclass(frozen=True)
class Session:
    """A parking session as reported by the portal.

    Attributes:
        id: Id of the session.
        plate: Normalized license plate the session belongs to.
        active: Whether the session is currently running.
        end: Time at which the session ends.
    """

    id: int
    plate: str
    active: bool
    end: datetime


def normalize_plate(plate: str) -> str:
    """Normalize a license plate for comparison.

    Args:
        plate: License plate as typed by a user, e.g. `ab-123-c`.

    Returns:
        The plate uppercased without spaces or dashes, e.g. `AB123C`.
    """
    return _PLATE_SEPARATORS_RE.sub("", plate).upper()


class ParkeerserviceClient:
    """Logs in once and keeps the cookie session.

    Call `login` again when `AuthError` is raised to refresh an expired session.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        email: str,
        password: str,
    ) -> None:
        """Initialize the client.

        Args:
            session: HTTP session with its own cookie jar.
            endpoint: Portal url, e.g. `https://parkstart-LOCATION.parkpermit.eu`.
            email: Email used to log in.
            password: Password used to log in.
        """
        self._http = session
        self._endpoint = endpoint.rstrip("/")
        self._email = email
        self._password = password
        self.customer_id: int | None = None
        self.permits: list[Permit] = []

    async def login(self) -> None:
        """Log in and load the customer id and permits.

        Raises:
            AuthError: If the credentials are rejected.
            ParkeerserviceError: If the portal cannot be reached or parsed.
        """
        self._http.cookie_jar.clear()
        page = await self._text(self._http.get(self._endpoint))
        token = _TOKEN_RE.search(page)
        if not token:
            msg = "Verification token not found on login page"
            raise ParkeerserviceError(msg)
        body = (
            f"__RequestVerificationToken={token.group(1)}"
            f"&Email={quote(self._email, safe='')}&Password={quote(self._password, safe='')}"
        )
        await self._text(
            self._http.post(
                self._endpoint,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        )
        page = await self._text(self._http.get(f"{self._endpoint}/Customer/PlanSession"))
        customer = _CUSTOMER_RE.search(page)
        permits = _PERMITS_RE.search(page)
        if not customer or not permits:
            # the portal answers a wrong password with the login page again
            msg = "Login failed, check email and password"
            raise AuthError(msg)
        self.customer_id = int(customer.group(1))
        try:
            permit_list = json.loads(permits.group(1).replace("\\", ""))["permitList"]
            self.permits = [
                Permit(p["id"], p["permitProductId"], p["permitProduct"]) for p in permit_list
            ]
        except (ValueError, KeyError, TypeError) as err:
            msg = f"Could not parse permits: {err}"
            raise ParkeerserviceError(msg) from err

    async def get_sessions(self) -> list[Session]:
        """Fetch the parking sessions of the account.

        Returns:
            All sessions reported by the portal, active or not.

        Raises:
            AuthError: If the login session has expired.
            ParkeerserviceError: If the request fails or the response is malformed.
        """
        endpoint = self._endpoint
        data = await self._json(
            self._http.post(
                f"{endpoint}/Customer/SessionsOverview/GetParkingSessions/",
                data=f"cstId={self.customer_id}",
                headers={
                    "Referer": f"{endpoint}/Customer/SessionsOverview/Index/",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
            )
        )
        try:
            return [
                Session(
                    id=int(e["id"]),
                    plate=normalize_plate(e["lp"]),
                    active=bool(e["isActive"]),
                    end=datetime.strptime(e["timeEndUtc"], _TIME_FORMAT).replace(tzinfo=UTC),
                )
                for e in data.get("data", [])
            ]
        except (ValueError, KeyError, TypeError) as err:
            msg = f"Could not parse sessions: {err}"
            raise ParkeerserviceError(msg) from err

    async def start(self, plate: str, permit_name: str, end: datetime) -> None:
        """Start a parking session.

        Args:
            plate: License plate to park.
            permit_name: Exact name of the permit to use.
            end: Time at which the session should end (timezone aware).

        Raises:
            AuthError: If the login session has expired.
            ParkeerserviceError: If the permit is unknown or the request fails.
        """
        permit = next((p for p in self.permits if p.name == permit_name), None)
        if permit is None:
            names = ", ".join(p.name for p in self.permits)
            msg = f"Permit '{permit_name}' not found, available: {names}"
            raise ParkeerserviceError(msg)
        endpoint = self._endpoint
        await self._text(
            self._http.post(
                f"{endpoint}/Customer/PlanSession/StartParkingSession",
                json={
                    "parkingSessionId": 0,
                    "permitId": permit.id,
                    "lp": normalize_plate(plate),
                    "startedForUser": self.customer_id,
                    "timeStart": datetime.now(UTC).isoformat(),
                    "timeEnd": end.astimezone(UTC).isoformat(),
                },
                headers={
                    "Referer": f"{endpoint}/Customer/PlanSession",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        )

    async def stop(self, session_id: int) -> None:
        """Stop a parking session.

        Args:
            session_id: Id of the session, see `Session.id`.

        Raises:
            AuthError: If the login session has expired.
            ParkeerserviceError: If the request fails.
        """
        endpoint = self._endpoint
        await self._text(
            self._http.post(
                f"{endpoint}/Customer/SessionsOverview/StopParkingSession",
                json={"parkingSessionId": session_id},
                headers={"Referer": f"{endpoint}/Customer/SessionsOverview/Index/"},
            )
        )

    @staticmethod
    async def _text(request: _Request) -> str:
        try:
            async with request as response:
                text = await response.text()
                if not response.ok:
                    msg = f"HTTP {response.status}: {text[:200]}"
                    raise ParkeerserviceError(msg)
                return text
        except aiohttp.ClientError as err:
            raise ParkeerserviceError(str(err)) from err

    @staticmethod
    async def _json(request: _Request) -> dict[str, Any]:
        try:
            async with request as response:
                if not response.ok:
                    msg = f"HTTP {response.status}"
                    raise ParkeerserviceError(msg)
                if "json" not in response.headers.get("Content-Type", ""):
                    # expired cookie session: the portal redirects to the login page
                    msg = "Session expired"
                    raise AuthError(msg)
                data: dict[str, Any] = await response.json()
                return data
        except aiohttp.ClientError as err:
            raise ParkeerserviceError(str(err)) from err

"""Minimal OpenFGA HTTP client (T12, spec 03 §3, ADR-014).

Deliberately thin — check / write / delete / read over ``httpx`` against the
FGA HTTP API, with the two idempotency affordances the outbox dispatcher
needs: writing a tuple that already exists and deleting one that does not are
both treated as success, so retries after partial failures converge.
"""

from __future__ import annotations

from typing import Any, Iterator

import httpx

from aegis.config import get_settings

Tuple3 = dict[str, str]  # {"user": ..., "relation": ..., "object": ...}


class FGAError(RuntimeError):
    """The FGA API rejected a request or is unreachable."""


class FGAClient:
    def __init__(
        self,
        api_url: str | None = None,
        store_id: str | None = None,
        model_id: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 5.0,
    ) -> None:
        settings = get_settings()
        self.api_url = (api_url or settings.fga_api_url).rstrip("/")
        self.store_id = store_id or settings.fga_store_id
        self.model_id = model_id or settings.fga_model_id
        if not self.store_id:
            raise FGAError(
                "FGA_STORE_ID is not configured — run `make bootstrap` "
                "(it writes infra/.runtime.env)"
            )
        self._client = client or httpx.Client(base_url=self.api_url, timeout=timeout)

    def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        try:
            return self._client.post(f"/stores/{self.store_id}{path}", json=payload)
        except httpx.HTTPError as exc:
            raise FGAError(f"FGA unreachable at {self.api_url}: {exc}") from exc

    def check(self, user: str, relation: str, object_: str) -> bool:
        payload: dict[str, Any] = {
            "tuple_key": {"user": user, "relation": relation, "object": object_}
        }
        if self.model_id:
            payload["authorization_model_id"] = self.model_id
        response = self._post("/check", payload)
        if response.status_code != 200:
            raise FGAError(f"FGA check failed ({response.status_code}): {response.text}")
        return bool(response.json().get("allowed"))

    def exists(self, tuple_: Tuple3) -> bool:
        response = self._post("/read", {"tuple_key": tuple_, "page_size": 1})
        if response.status_code != 200:
            raise FGAError(f"FGA read failed ({response.status_code}): {response.text}")
        return bool(response.json().get("tuples"))

    def _mutate(self, op: str, tuple_: Tuple3) -> None:
        key = "writes" if op == "write" else "deletes"
        payload: dict[str, Any] = {key: {"tuple_keys": [tuple_]}}
        if self.model_id:
            payload["authorization_model_id"] = self.model_id
        response = self._post("/write", payload)
        if response.status_code == 200:
            return
        # Idempotency: FGA 400s on duplicate writes / missing deletes.  If the
        # store already reflects the intent, the retry has converged.
        if response.status_code == 400:
            present = self.exists(tuple_)
            if (op == "write" and present) or (op == "delete" and not present):
                return
        raise FGAError(f"FGA {op} failed ({response.status_code}): {response.text}")

    def write(self, tuple_: Tuple3) -> None:
        self._mutate("write", tuple_)

    def delete(self, tuple_: Tuple3) -> None:
        self._mutate("delete", tuple_)

    def read_all(self) -> Iterator[Tuple3]:
        """Every tuple in the store (used by `aegis authz rebuild`)."""
        token: str | None = None
        while True:
            payload: dict[str, Any] = {"page_size": 100}
            if token:
                payload["continuation_token"] = token
            response = self._post("/read", payload)
            if response.status_code != 200:
                raise FGAError(f"FGA read failed ({response.status_code}): {response.text}")
            body = response.json()
            for item in body.get("tuples", []):
                key = item["key"]
                yield {
                    "user": key["user"],
                    "relation": key["relation"],
                    "object": key["object"],
                }
            token = body.get("continuation_token")
            if not token:
                return

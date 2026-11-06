"""HTTP client for the mastime.ir (MAS) REST API.

The API is a JSON-over-HTTP backend used by the SPA at https://mastime.ir.
Authentication is a bearer token obtained from POST /api/auth/login or
POST /api/public/{token}/speaker/enter (speaker session).

Endpoint map (discovered from the site's JS bundle):
  Auth        /api/auth/*           register, login, me, profile, change-password,
                                    recover-password, recovery-code, logout
  Rooms       /api/rooms            list / create
              /api/rooms/{id}       get / update / delete
              /api/rooms/{id}/reset-all
  Timer       /api/rooms/{id}/timer/state, /timer/action
  Speakers    /api/rooms/{id}/speakers[/{sid}] (+ reorder, rotate-code, unfreeze)
  Files       /api/rooms/{id}/files[/{fid}] (+ review)
  Recording   /api/rooms/{id}/recording/status, start, chunk, finish
  Reactions   /api/rooms/{id}/reactions/toggle
  Report      /api/rooms/{id}/report/pdf
  Public      /api/public/{token}/...   state, reactions, report/pdf, files,
                                        speaker/enter, heartbeat, leave, files,
                                        recording/*
  Admin       /api/admin/stats, users, rooms, audit-logs
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

API_BASE_DEFAULT = "https://mastime.ir"


class MastimeAPIError(Exception):
    """Raised for non-2xx API responses; carries status and server message."""

    def __init__(self, status: int, message: str, data: Any = None):
        super().__init__(f"mastime API error {status}: {message}")
        self.status = status
        self.message = message
        self.data = data


class MastimeClient:
    """Thin, stateful wrapper around the mastime.ir HTTP API.

    Keeps the owner session token (from login) and an optional speaker
    session token (from public speaker/enter) in memory for the lifetime of
    the MCP server process. Set MASTIME_API_BASE to override the base URL.
    """

    def __init__(self, base_url: str = API_BASE_DEFAULT, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout, follow_redirects=True)
        self.session_token: Optional[str] = None
        self.speaker_token: Optional[str] = None

    # ------------------------------------------------------------------ auth
    def _headers(self, speaker: bool = False) -> Dict[str, str]:
        token = self.speaker_token if speaker else self.session_token
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        speaker: bool = False,
        raw: bool = False,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        try:
            resp = self._client.request(
                method,
                path,
                json=json,
                data=data,
                files=files,
                params=params,
                headers={**self._headers(speaker), **(headers or {})},
            )
        except httpx.HTTPError as exc:
            raise MastimeAPIError(0, f"network error: {exc}") from exc

        if raw:
            if resp.status_code >= 400:
                raise self._error(resp)
            return resp

        if resp.status_code >= 400:
            raise self._error(resp)

        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    @staticmethod
    def _error(resp: httpx.Response) -> MastimeAPIError:
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            msg = payload.get("message") or payload.get("error") or resp.text[:200]
        else:
            msg = (resp.text or "")[:200]
        return MastimeAPIError(resp.status_code, str(msg), payload)

    # ---------------------------------------------------------------- public
    def login(self, username: str, password: str) -> Dict[str, Any]:
        body = self._request("POST", "/api/auth/login", json={"username": username, "password": password})
        self.session_token = body.get("session_token")
        return body

    def register(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = self._request("POST", "/api/auth/register", json=payload)
        # Registration may auto-login; pick up a token if present.
        self.session_token = self.session_token or body.get("session_token")
        return body

    def me(self) -> Dict[str, Any]:
        return self._request("GET", "/api/auth/me")

    def logout(self) -> Any:
        try:
            return self._request("POST", "/api/auth/logout")
        finally:
            self.session_token = None

    def update_profile(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/auth/profile", json=payload)

    def change_password(self, current_password: str, new_password: str) -> Any:
        return self._request(
            "POST", "/api/auth/change-password",
            json={"current_password": current_password, "new_password": new_password},
        )

    def recover_password(self, username: str, recovery_code: str, new_password: str) -> Any:
        return self._request(
            "POST", "/api/auth/recover-password",
            json={"username": username, "recovery_code": recovery_code, "new_password": new_password},
        )

    def recovery_code(self, current_password: str) -> Dict[str, Any]:
        return self._request(
            "POST", "/api/auth/recovery-code", json={"current_password": current_password}
        )

    # ---------------------------------------------------------------- rooms
    def list_rooms(self) -> Dict[str, Any]:
        return self._request("GET", "/api/rooms")

    def create_room(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/api/rooms", json=payload)

    def get_room(self, room_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/rooms/{room_id}")

    def update_room(self, room_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", f"/api/rooms/{room_id}", json=payload)

    def delete_room(self, room_id: str) -> Any:
        return self._request("DELETE", f"/api/rooms/{room_id}")

    def reset_room(self, room_id: str) -> Any:
        return self._request("POST", f"/api/rooms/{room_id}/reset-all")

    # --------------------------------------------------------------- timer
    def timer_state(self, room_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/rooms/{room_id}/timer/state")

    def timer_action(self, room_id: str, action: str, speaker_id: Optional[str] = None,
                     expected_version: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"action": action}
        if speaker_id is not None:
            payload["speaker_id"] = speaker_id
        if expected_version is not None:
            payload["expected_version"] = expected_version
        return self._request("POST", f"/api/rooms/{room_id}/timer/action", json=payload)

    # ------------------------------------------------------------ speakers
    def add_speaker(self, room_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"/api/rooms/{room_id}/speakers", json=payload)

    def update_speaker(self, room_id: str, speaker_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", f"/api/rooms/{room_id}/speakers/{speaker_id}", json=payload)

    def delete_speaker(self, room_id: str, speaker_id: str,
                       save_recording: Optional[bool] = None) -> Any:
        params = {"save_recording": str(save_recording).lower()} if save_recording is not None else None
        return self._request("DELETE", f"/api/rooms/{room_id}/speakers/{speaker_id}",
                             params=params)

    def reorder_speakers(self, room_id: str, speaker_ids: list) -> Any:
        return self._request("POST", f"/api/rooms/{room_id}/speakers/reorder",
                             json={"speaker_ids": list(speaker_ids)})

    def rotate_speaker_code(self, room_id: str, speaker_id: str) -> Any:
        return self._request("POST", f"/api/rooms/{room_id}/speakers/{speaker_id}/rotate-code")

    def unfreeze_speaker(self, room_id: str, speaker_id: str) -> Any:
        return self._request("POST", f"/api/rooms/{room_id}/speakers/{speaker_id}/unfreeze")

    # --------------------------------------------------------------- files
    def list_files(self, room_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/rooms/{room_id}/files")

    def upload_file(self, room_id: str, file_path: str | Path,
                    upload_type: Optional[str] = None,
                    speaker_id: Optional[str] = None) -> Dict[str, Any]:
        path = Path(file_path)
        data = {}
        if upload_type:
            data["upload_type"] = upload_type
        if speaker_id:
            data["speaker_id"] = speaker_id
        with path.open("rb") as fh:
            files = {"file": (path.name, fh, "application/octet-stream")}
            return self._request("POST", f"/api/rooms/{room_id}/files", data=data, files=files)

    def download_file(self, room_id: str, file_id: str, destination: Optional[str | Path] = None) -> Dict[str, Any]:
        resp = self._request("GET", f"/api/rooms/{room_id}/files/{file_id}/download", raw=True)
        dest = Path(destination) if destination else Path(str(file_id))
        dest.write_bytes(resp.content)
        return {"saved_to": str(dest), "size_bytes": len(resp.content), "file_id": file_id}

    def delete_file(self, room_id: str, file_id: str) -> Any:
        return self._request("DELETE", f"/api/rooms/{room_id}/files/{file_id}")

    def review_file(self, room_id: str, file_id: str, approved: bool) -> Any:
        return self._request("POST", f"/api/rooms/{room_id}/files/{file_id}/review",
                             json={"approved": bool(approved)})

    # ----------------------------------------------------------- recording
    def recording_status(self, room_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/rooms/{room_id}/recording/status")

    def start_recording(self, room_id: str, mime_type: str = "audio/webm") -> Dict[str, Any]:
        return self._request("POST", f"/api/rooms/{room_id}/recording/start",
                             json={"mime_type": mime_type})

    def push_recording_chunk(self, room_id: str, session_id: str,
                             data: bytes, mime_type: str = "audio/webm") -> Any:
        # Binary payloads are sent base64-encoded as JSON (the frontend sends
        # raw Blob bodies; this wrapper keeps the stream JSON-friendly).
        import base64
        return self._request("POST", f"/api/rooms/{room_id}/recording/chunk",
                             json={"session_id": session_id,
                                   "mime_type": mime_type,
                                   "data": base64.b64encode(data).decode("ascii")})

    def finish_recording(self, room_id: str, save: bool = True) -> Any:
        return self._request("POST", f"/api/rooms/{room_id}/recording/finish",
                             json={"save": bool(save)})

    # ----------------------------------------------------------- reactions
    def toggle_reactions(self, room_id: str) -> Dict[str, Any]:
        return self._request("POST", f"/api/rooms/{room_id}/reactions/toggle")

    def room_report_pdf(self, room_id: str, destination: Optional[str | Path] = None) -> Dict[str, Any]:
        resp = self._request("GET", f"/api/rooms/{room_id}/report/pdf", raw=True)
        dest = Path(destination) if destination else Path(f"report-{room_id}.pdf")
        dest.write_bytes(resp.content)
        return {"saved_to": str(dest), "size_bytes": len(resp.content)}

    # --------------------------------------------------------------- public
    def public_state(self, token: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/public/{token}/state")

    def public_reactions(self, token: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/public/{token}/reactions")

    def public_report_pdf(self, token: str, destination: Optional[str | Path] = None) -> Dict[str, Any]:
        resp = self._request("GET", f"/api/public/{token}/report/pdf", raw=True)
        dest = Path(destination) if destination else Path(f"public-report-{token}.pdf")
        dest.write_bytes(resp.content)
        return {"saved_to": str(dest), "size_bytes": len(resp.content)}

    def public_download_file(self, token: str, file_id: str,
                             destination: Optional[str | Path] = None) -> Dict[str, Any]:
        resp = self._request("GET", f"/api/public/{token}/files/{file_id}", raw=True)
        dest = Path(destination) if destination else Path(str(file_id))
        dest.write_bytes(resp.content)
        return {"saved_to": str(dest), "size_bytes": len(resp.content), "file_id": file_id}

    def speaker_enter(self, token: str, code: str) -> Dict[str, Any]:
        body = self._request("POST", f"/api/public/{token}/speaker/enter", json={"code": code})
        self.speaker_token = body.get("session_token") or self.speaker_token
        return body

    def speaker_heartbeat(self, token: str) -> Any:
        return self._request("POST", f"/api/public/{token}/speaker/heartbeat", speaker=True)

    def speaker_leave(self, token: str) -> Any:
        try:
            return self._request("POST", f"/api/public/{token}/speaker/leave", speaker=True)
        finally:
            self.speaker_token = None

    def speaker_files(self, token: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/public/{token}/speaker/files", speaker=True)

    def speaker_upload_file(self, token: str, file_path: str | Path) -> Dict[str, Any]:
        path = Path(file_path)
        with path.open("rb") as fh:
            files = {"file": (path.name, fh, "application/octet-stream")}
            return self._request("POST", f"/api/public/{token}/speaker/files",
                                 files=files, speaker=True)

    def speaker_start_recording(self, token: str, mime_type: str = "audio/webm") -> Dict[str, Any]:
        return self._request("POST", f"/api/public/{token}/speaker/recording/start",
                             json={"mime_type": mime_type}, speaker=True)

    def speaker_finish_recording(self, token: str, save: bool = True) -> Any:
        return self._request("POST", f"/api/public/{token}/speaker/recording/finish",
                             json={"save": bool(save)}, speaker=True)

    # --------------------------------------------------------------- admin
    def admin_stats(self) -> Dict[str, Any]:
        return self._request("GET", "/api/admin/stats")

    def admin_users(self) -> Dict[str, Any]:
        return self._request("GET", "/api/admin/users")

    def admin_toggle_user(self, user_id: str, active: bool) -> Any:
        return self._request("POST", f"/api/admin/users/{user_id}/toggle-active",
                             json={"active": bool(active)})

    def admin_rooms(self) -> Dict[str, Any]:
        return self._request("GET", "/api/admin/rooms")

    def admin_audit_logs(self) -> Dict[str, Any]:
        return self._request("GET", "/api/admin/audit-logs")


def make_client() -> MastimeClient:
    return MastimeClient(base_url=os.environ.get("MASTIME_API_BASE", API_BASE_DEFAULT))

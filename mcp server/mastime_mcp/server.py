"""MCP server for mastime.ir — MAS (مــاس) smart time management & speech broadcasting.

Exposes the site's REST API as MCP tools. Run with:

    python -m mastime_mcp.server        # stdio transport (default)
    python mastime_mcp/server.py --transport http --port 8000
"""

from __future__ import annotations

import argparse
from typing import Optional

from fastmcp import FastMCP

from .api import MastimeClient, MastimeAPIError, make_client

mcp = FastMCP("mastime", instructions=(
    "MCP server for mastime.ir (MAS — مــاس), a smart speech time-management and "
    "broadcasting platform. Use the login tool first to get an owner session; "
    "speaker/enter stores a speaker session. All *_owner tools send the bearer token "
    "automatically. PDF/file downloads are saved locally and the saved path is returned."
))

client: MastimeClient = make_client()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _guard(msg: MastimeAPIError) -> dict:
    return {"ok": False, "status": msg.status, "error": msg.message}


def _result(payload: object) -> dict:
    return {"ok": True, "data": payload}


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@mcp.tool(description="Log in to mastime.ir with username/password. Stores the session token for all subsequent owner tools. Returns user + session_token.")
def mastime_login(username: str, password: str) -> dict:
    try:
        return _result(client.login(username, password))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Register a new account on mastime.ir. Returns the user and a one-time recovery_code (keep it safe — it is the only way to recover the account).")
def mastime_register(account_name: str = "", username: str = "", password: str = "",
                     job: str = "", age: Optional[int] = None) -> dict:
    import json
    payload = {"account_name": account_name}
    if username:
        payload["username"] = username
    if password:
        payload["password"] = password
    if job:
        payload["job"] = job
    if age is not None:
        payload["age"] = age
    try:
        return _result(client.register(payload))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Get the currently logged-in user profile.")
def mastime_me() -> dict:
    try:
        return _result(client.me())
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Log out; clears the stored session token.")
def mastime_logout() -> dict:
    try:
        return _result(client.logout())
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Update the profile of the logged-in user (account_name, job, age).")
def mastime_update_profile(account_name: Optional[str] = None, job: Optional[str] = None,
                           age: Optional[int] = None) -> dict:
    payload = {}
    if account_name is not None:
        payload["account_name"] = account_name
    if job is not None:
        payload["job"] = job
    if age is not None:
        payload["age"] = age
    try:
        return _result(client.update_profile(payload))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Change the logged-in user's password (requires current password).")
def mastime_change_password(current_password: str, new_password: str) -> dict:
    try:
        return _result(client.change_password(current_password, new_password))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Regenerate the one-time account recovery code (requires current password).")
def mastime_generate_recovery_code(current_password: str) -> dict:
    try:
        return _result(client.recovery_code(current_password))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Recover a lost password using the username and the one-time recovery code.")
def mastime_recover_password(username: str, recovery_code: str, new_password: str) -> dict:
    try:
        return _result(client.recover_password(username, recovery_code, new_password))
    except MastimeAPIError as e:
        return _guard(e)


# --------------------------------------------------------------------------- #
# Rooms
# --------------------------------------------------------------------------- #
@mcp.tool(description="List all rooms owned by the logged-in user.")
def mastime_list_rooms() -> dict:
    try:
        return _result(client.list_rooms())
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description=(
    "Create a new speech room. name is required. timing_mode: 'global' (one countdown for all "
    "speakers — global_seconds) or 'per_speaker'. order_mode: 'manual' (default) or auto. "
    "capacity = number of seats/viewer slots. speaker_mode_enabled enables the 4-char speaker code panel. "
    "recording_enabled / live_files_enabled / public_enabled toggle room features."))
def mastime_create_room(
    name: str,
    description: str = "",
    capacity: int = 10,
    recording_enabled: bool = True,
    live_files_enabled: bool = True,
    public_enabled: bool = True,
    speaker_mode_enabled: bool = False,
    reactions_enabled: bool = True,
    timing_mode: str = "global",
    global_seconds: int = 300,
    order_mode: str = "manual",
) -> dict:
    payload = {
        "name": name,
        "description": description,
        "capacity": capacity,
        "recording_enabled": bool(recording_enabled),
        "live_files_enabled": bool(live_files_enabled),
        "public_enabled": bool(public_enabled),
        "speaker_mode_enabled": bool(speaker_mode_enabled),
        "reactions_enabled": bool(reactions_enabled),
        "timing_mode": timing_mode,
        "global_seconds": global_seconds,
        "order_mode": order_mode,
    }
    try:
        return _result(client.create_room(payload))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Get full details of a room (speakers, files, timer state, settings).")
def mastime_get_room(room_id: str) -> dict:
    try:
        return _result(client.get_room(room_id))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Update room settings: only the provided fields change — the tool fetches the current room first and merges. Set confirm_shrink=true when reducing capacity below current viewers.")
def mastime_update_room(
    room_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    capacity: Optional[int] = None,
    recording_enabled: Optional[bool] = None,
    live_files_enabled: Optional[bool] = None,
    public_enabled: Optional[bool] = None,
    speaker_mode_enabled: Optional[bool] = None,
    reactions_enabled: Optional[bool] = None,
    timing_mode: Optional[str] = None,
    global_seconds: Optional[int] = None,
    order_mode: Optional[str] = None,
    confirm_shrink: Optional[bool] = None,
) -> dict:
    changes = {k: v for k, v in locals().items()
               if k not in ("room_id",) and v is not None}
    try:
        current = client.get_room(room_id).get("room", {})
        payload = {**current, **changes}
        return _result(client.update_room(room_id, payload))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Permanently delete a room and all its data.")
def mastime_delete_room(room_id: str) -> dict:
    try:
        return _result(client.delete_room(room_id))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Reset a room: clear all speakers and timer state while keeping room settings.")
def mastime_reset_room(room_id: str) -> dict:
    try:
        return _result(client.reset_room(room_id))
    except MastimeAPIError as e:
        return _guard(e)


# --------------------------------------------------------------------------- #
# Timer
# --------------------------------------------------------------------------- #
@mcp.tool(description="Get the live timer state of a room (running, current speaker, elapsed, version, ...).")
def mastime_get_timer_state(room_id: str) -> dict:
    try:
        return _result(client.timer_state(room_id))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description=(
    "Send a timer command. Actions: start, pause, resume, goto (switch to speaker_id), finish, "
    "continue_overtime, finish_overtime, reset. speaker_id is required for goto/start; "
    "expected_version (from timer state) is used for optimistic concurrency."))
def mastime_timer_action(room_id: str, action: str,
                         speaker_id: Optional[str] = None,
                         expected_version: Optional[int] = None) -> dict:
    try:
        return _result(client.timer_action(room_id, action, speaker_id, expected_version))
    except MastimeAPIError as e:
        return _guard(e)


# --------------------------------------------------------------------------- #
# Speakers
# --------------------------------------------------------------------------- #
@mcp.tool(description="Add a speaker to a room. gender: 'male'/'female'/'other' (or free text). speaking_seconds is the time slot length; age is optional.")
def mastime_add_speaker(room_id: str, name: str,
                        gender: Optional[str] = None,
                        age: Optional[int] = None,
                        description: Optional[str] = None,
                        speaking_seconds: Optional[int] = None) -> dict:
    payload = {"name": name}
    if gender is not None:
        payload["gender"] = gender
    if age is not None:
        payload["age"] = age
    if description is not None:
        payload["description"] = description
    if speaking_seconds is not None:
        payload["speaking_seconds"] = speaking_seconds
    try:
        return _result(client.add_speaker(room_id, payload))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Update a speaker's profile (name, gender, age, description, speaking_seconds). Uses the same fields as the site's edit-speaker dialog.")
def mastime_update_speaker(room_id: str, speaker_id: str,
                           name: Optional[str] = None,
                           gender: Optional[str] = None,
                           age: Optional[int] = None,
                           description: Optional[str] = None,
                           speaking_seconds: Optional[int] = None) -> dict:
    payload = {k: v for k, v in locals().items()
               if k not in ("room_id", "speaker_id") and v is not None}
    try:
        return _result(client.update_speaker(room_id, speaker_id, payload))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Remove a speaker from a room. If the speaker is currently recording, set save_recording=true to keep the recording or false to discard it.")
def mastime_delete_speaker(room_id: str, speaker_id: str,
                           save_recording: Optional[bool] = None) -> dict:
    try:
        return _result(client.delete_speaker(room_id, speaker_id, save_recording))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Reorder speakers by passing the full ordered list of speaker ids (speaker_ids).")
def mastime_reorder_speakers(room_id: str, speaker_ids: list[str]) -> dict:
    try:
        return _result(client.reorder_speakers(room_id, speaker_ids))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Invalidate a speaker's 4-char entry code and generate a fresh one.")
def mastime_rotate_speaker_code(room_id: str, speaker_id: str) -> dict:
    try:
        return _result(client.rotate_speaker_code(room_id, speaker_id))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Unfreeze a speaker (e.g. after a skipped/overrun turn).")
def mastime_unfreeze_speaker(room_id: str, speaker_id: str) -> dict:
    try:
        return _result(client.unfreeze_speaker(room_id, speaker_id))
    except MastimeAPIError as e:
        return _guard(e)


# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #
@mcp.tool(description="List files of a room (common + speaker-uploaded).")
def mastime_list_files(room_id: str) -> dict:
    try:
        return _result(client.list_files(room_id))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Upload a file to a room. upload_type: 'common' or 'speaker'; speaker_id is required if upload_type='speaker'. file_path is a local path.")
def mastime_upload_file(room_id: str, file_path: str,
                        upload_type: Optional[str] = "common",
                        speaker_id: Optional[str] = None) -> dict:
    try:
        return _result(client.upload_file(room_id, file_path, upload_type, speaker_id))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Download a room file to disk; returns the saved path. destination is an optional local path.")
def mastime_download_file(room_id: str, file_id: str,
                          destination: Optional[str] = None) -> dict:
    try:
        return _result(client.download_file(room_id, file_id, destination))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Delete a file from a room.")
def mastime_delete_file(room_id: str, file_id: str) -> dict:
    try:
        return _result(client.delete_file(room_id, file_id))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Review an uploaded file: approved=true makes it public to viewers, approved=false rejects it.")
def mastime_review_file(room_id: str, file_id: str, approved: bool) -> dict:
    try:
        return _result(client.review_file(room_id, file_id, approved))
    except MastimeAPIError as e:
        return _guard(e)


# --------------------------------------------------------------------------- #
# Recording
# --------------------------------------------------------------------------- #
@mcp.tool(description="Get recording status of a room ({active: bool, ...}).")
def mastime_recording_status(room_id: str) -> dict:
    try:
        return _result(client.recording_status(room_id))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Start an automatic recording session for a room. Returns a session_id used for chunk uploads.")
def mastime_start_recording(room_id: str, mime_type: str = "audio/webm") -> dict:
    try:
        return _result(client.start_recording(room_id, mime_type))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Push an audio chunk (base64) to an ongoing recording session.")
def mastime_push_recording_chunk(room_id: str, session_id: str,
                                 data_base64: str,
                                 mime_type: str = "audio/webm") -> dict:
    import base64
    try:
        data = base64.b64decode(data_base64)
        return _result(client.push_recording_chunk(room_id, session_id, data, mime_type))
    except (ValueError, MastimeAPIError) as e:
        if isinstance(e, MastimeAPIError):
            return _guard(e)
        return {"ok": False, "error": "invalid base64 data"}


@mcp.tool(description="Finish the recording session. save=true stores it as an audio file in the room.")
def mastime_finish_recording(room_id: str, save: bool = True) -> dict:
    try:
        return _result(client.finish_recording(room_id, save))
    except MastimeAPIError as e:
        return _guard(e)


# --------------------------------------------------------------------------- #
# Reactions & report
# --------------------------------------------------------------------------- #
@mcp.tool(description="Toggle the audience reaction (clap) feature of a room on/off. Returns {reactions_enabled}.")
def mastime_toggle_reactions(room_id: str) -> dict:
    try:
        return _result(client.toggle_reactions(room_id))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Generate and download the official event report PDF of a room; returns the saved path.")
def mastime_download_report_pdf(room_id: str, destination: Optional[str] = None) -> dict:
    try:
        return _result(client.room_report_pdf(room_id, destination))
    except MastimeAPIError as e:
        return _guard(e)


# --------------------------------------------------------------------------- #
# Public (viewer / speaker) tools
# --------------------------------------------------------------------------- #
@mcp.tool(description="Get the public view state of a room by its share token (no login needed): current speaker, timer, settings.")
def mastime_public_state(token: str) -> dict:
    try:
        return _result(client.public_state(token))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Get the public reaction counters of a room by its share token.")
def mastime_public_reactions(token: str) -> dict:
    try:
        return _result(client.public_reactions(token))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Download the public report PDF of a room by share token; returns the saved path.")
def mastime_public_download_report_pdf(token: str, destination: Optional[str] = None) -> dict:
    try:
        return _result(client.public_report_pdf(token, destination))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Download a publicly available room file by share token; returns the saved path.")
def mastime_public_download_file(token: str, file_id: str,
                                 destination: Optional[str] = None) -> dict:
    try:
        return _result(client.public_download_file(token, file_id, destination))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Enter the speaker panel of a room with the 4-char speaker code. Stores the speaker session used by the other speaker_* tools.")
def mastime_speaker_enter(token: str, code: str) -> dict:
    try:
        return _result(client.speaker_enter(token, code))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Send a speaker heartbeat to keep the speaker session alive (called periodically by the panel).")
def mastime_speaker_heartbeat(token: str) -> dict:
    try:
        return _result(client.speaker_heartbeat(token))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Leave the speaker panel and clear the stored speaker session.")
def mastime_speaker_leave(token: str) -> dict:
    try:
        return _result(client.speaker_leave(token))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="List files uploaded by the current speaker (pending review).")
def mastime_speaker_list_files(token: str) -> dict:
    try:
        return _result(client.speaker_files(token))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Upload a file as the speaker; it stays hidden from viewers until the owner approves it.")
def mastime_speaker_upload_file(token: str, file_path: str) -> dict:
    try:
        return _result(client.speaker_upload_file(token, file_path))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Start recording from the speaker's device (returns a session_id).")
def mastime_speaker_start_recording(token: str, mime_type: str = "audio/webm") -> dict:
    try:
        return _result(client.speaker_start_recording(token, mime_type))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Finish the speaker's device recording; save=true stores it with the room.")
def mastime_speaker_finish_recording(token: str, save: bool = True) -> dict:
    try:
        return _result(client.speaker_finish_recording(token, save))
    except MastimeAPIError as e:
        return _guard(e)


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #
@mcp.tool(description="Admin: platform-wide statistics (users, rooms, activity). Requires an admin account.")
def mastime_admin_stats() -> dict:
    try:
        return _result(client.admin_stats())
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Admin: list all platform users. Requires an admin account.")
def mastime_admin_list_users() -> dict:
    try:
        return _result(client.admin_users())
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Admin: activate/deactivate a user account. Requires an admin account.")
def mastime_admin_toggle_user(user_id: str, active: bool) -> dict:
    try:
        return _result(client.admin_toggle_user(user_id, active))
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Admin: list all rooms across the platform. Requires an admin account.")
def mastime_admin_list_rooms() -> dict:
    try:
        return _result(client.admin_rooms())
    except MastimeAPIError as e:
        return _guard(e)


@mcp.tool(description="Admin: fetch audit log entries. Requires an admin account.")
def mastime_admin_audit_logs() -> dict:
    try:
        return _result(client.admin_audit_logs())
    except MastimeAPIError as e:
        return _guard(e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mastime MCP server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.transport == "http":
        mcp.run(transport="http", host="127.0.0.1", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

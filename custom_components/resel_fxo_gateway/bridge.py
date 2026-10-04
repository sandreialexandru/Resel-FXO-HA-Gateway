"""TCP audio bridge between Home Assistant and the ESP32 audio_tcp component.

Protocol (see components/audio_tcp):
  1. client sends one ASCII line:  "AUDIO1 <token>\n"  (just "AUDIO1\n" if no token)
  2. ESP -> client: raw PCM 16 kHz / 16 bit / mono from the line microphone (only while listening)
  3. client -> ESP: raw PCM for the speaker (accepted only while the ESP is in "talk" mode)

The ESP accepts a single client at a time, so the bridge only keeps the connection open
while at least one listener (a card in a browser) is subscribed.
This module has no Home Assistant dependency so it can be tested on its own.
"""
from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass

from .const import READ_CHUNK

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0
RECONNECT_DELAY = 2.0
IDLE_CLOSE_DELAY = 5.0  # keep the link for a few seconds after the last listener leaves


def hello_line(token: str) -> bytes:
    """First line the ESP expects."""
    return (f"AUDIO1 {token}" if token else "AUDIO1").encode() + b"\n"


def _enable_keepalive(writer: asyncio.StreamWriter) -> None:
    """Detect a rebooted/unplugged ESP instead of waiting forever."""
    sock = writer.get_extra_info("socket")
    if sock is None:
        return
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        for name, value in (("TCP_KEEPIDLE", 10), ("TCP_KEEPINTVL", 5), ("TCP_KEEPCNT", 3)):
            opt = getattr(socket, name, None)
            if opt is not None:
                sock.setsockopt(socket.IPPROTO_TCP, opt, value)
    except OSError:
        pass


async def validate_connection(host: str, port: int, token: str) -> str | None:
    """Return None if OK, "cannot_connect" or "invalid_auth" otherwise.

    The ESP closes the connection right after the hello line when the token is wrong,
    and keeps it open when it is right.
    """
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), CONNECT_TIMEOUT)
    except (OSError, asyncio.TimeoutError):
        return "cannot_connect"
    try:
        writer.write(hello_line(token))
        await writer.drain()
        try:
            data = await asyncio.wait_for(reader.read(1), 1.0)
        except asyncio.TimeoutError:
            return None  # still open after 1 s: authenticated, just no audio right now
        if data == b"":
            return "invalid_auth"
        return None  # got audio bytes
    except OSError:
        return "cannot_connect"
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass


@dataclass(eq=False)
class Listener:
    """A subscriber (one card in one browser)."""

    on_audio: Callable[[bytes], None]
    on_status: Callable[[bool], None]


class AudioBridge:
    """Keeps one TCP connection to the ESP while there are listeners."""

    def __init__(self, host: str, port: int, token: str) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.connected = False
        self._listeners: set[Listener] = set()
        self._task: asyncio.Task | None = None
        self._close_handle: asyncio.TimerHandle | None = None
        self._writer: asyncio.StreamWriter | None = None

    # -- listeners ---------------------------------------------------------
    def add_listener(self, listener: Listener) -> None:
        self._listeners.add(listener)
        if self._close_handle is not None:
            self._close_handle.cancel()
            self._close_handle = None
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._run())
        listener.on_status(self.connected)

    def remove_listener(self, listener: Listener) -> None:
        self._listeners.discard(listener)
        if not self._listeners and self._task is not None and self._close_handle is None:
            loop = asyncio.get_running_loop()
            self._close_handle = loop.call_later(IDLE_CLOSE_DELAY, self._close_if_idle)

    def _close_if_idle(self) -> None:
        self._close_handle = None
        if not self._listeners:
            self._stop_task()

    def _stop_task(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def async_close(self) -> None:
        """Called on unload."""
        self._listeners.clear()
        if self._close_handle is not None:
            self._close_handle.cancel()
            self._close_handle = None
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def _notify_status(self, connected: bool) -> None:
        self.connected = connected
        for listener in list(self._listeners):
            try:
                listener.on_status(connected)
            except Exception:  # noqa: BLE001 - a broken listener must not stop the bridge
                _LOGGER.exception("Status listener failed")

    # -- audio out (client -> ESP) ----------------------------------------
    async def send(self, data: bytes) -> None:
        writer = self._writer
        if writer is None or not self.connected:
            return
        try:
            writer.write(data)
            await asyncio.wait_for(writer.drain(), 1.0)
        except (OSError, asyncio.TimeoutError):
            _LOGGER.debug("Sending audio to %s failed", self.host)

    # -- connection loop ----------------------------------------------------
    async def _run(self) -> None:
        while True:
            writer: asyncio.StreamWriter | None = None
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
                )
                _enable_keepalive(writer)
                writer.write(hello_line(self.token))
                await writer.drain()
                self._writer = writer
                self._notify_status(True)
                _LOGGER.debug("Audio link to %s:%s up", self.host, self.port)
                carry = b""
                while True:
                    data = await reader.read(READ_CHUNK)
                    if not data:
                        break
                    # keep whole 16-bit samples: a TCP read can end in the middle of one
                    data = carry + data
                    if len(data) % 2:
                        carry, data = data[-1:], data[:-1]
                    else:
                        carry = b""
                    if not data:
                        continue
                    for listener in list(self._listeners):
                        try:
                            listener.on_audio(data)
                        except Exception:  # noqa: BLE001
                            _LOGGER.exception("Audio listener failed")
            except asyncio.CancelledError:
                raise
            except (OSError, asyncio.TimeoutError) as err:
                _LOGGER.debug("Audio link to %s:%s error: %s", self.host, self.port, err)
            finally:
                self._writer = None
                if self.connected:
                    self._notify_status(False)
                if writer is not None:
                    writer.close()
            await asyncio.sleep(RECONNECT_DELAY)

"""Regression test for the serial frame reader (pc_side_py).

Run from the repo root:
    .\\pc_side_py\\venv\\Scripts\\python.exe test\\test_rx_framing.py

The ESP32 emits one frame per line:  rawX,rawY,button\\n
The reader must never combine the tail of one frame with the head of the next,
and a backlog of frames must never replay as pointer movement.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PC_SIDE = os.path.join(REPO, "pc_side_py")
sys.path.insert(0, PC_SIDE)
os.chdir(PC_SIDE)  # the controller loads config.json by relative path

import pyautogui

# The engine drives the real mouse; stub it out for the test.
MOVES = []
pyautogui.moveRel = lambda x, y=None, **k: MOVES.append((x, y))
pyautogui.click = lambda *a, **k: None
pyautogui.scroll = lambda *a, **k: None
pyautogui.press = lambda *a, **k: None
pyautogui.hotkey = lambda *a, **k: None

from controller import JoystickController


class FakeSerial:
    """Models pyserial on Windows.

    Bytes arrive in bursts over time (a USB-UART frame arrives in several
    pieces). A purge (`reset_input_buffer`) only discards what has already
    arrived - whatever is still in flight lands in the buffer afterwards.
    """

    def __init__(self):
        self.inflight = []
        self.arrived = bytearray()

    def deliver(self, chunk):
        self.inflight.append(chunk)

    def _pump(self):
        if self.inflight:
            self.arrived.extend(self.inflight.pop(0))

    @property
    def in_waiting(self):
        self._pump()
        return len(self.arrived)

    def read(self, size=1):
        data = bytes(self.arrived[:size])
        del self.arrived[:size]
        return data

    def readline(self):
        idx = self.arrived.find(b"\n")
        if idx >= 0:
            line = bytes(self.arrived[: idx + 1])
            del self.arrived[: idx + 1]
            return line
        line = bytes(self.arrived)
        self.arrived.clear()
        return line

    def reset_input_buffer(self):
        self.arrived.clear()

    def write(self, data):
        return len(data)


def make_controller(port):
    ctrl = JoystickController(port)
    ctrl.CENTER_X = 2048
    ctrl.CENTER_Y = 2048
    ctrl.current_mode_idx = 0
    return ctrl


def collect(port, chunks, updates_per_chunk=2):
    """Feed chunks into the engine and record the raw_x of every applied frame."""
    ctrl = make_controller(port)
    seen = []
    for chunk in chunks:
        port.deliver(chunk)
        for _ in range(updates_per_chunk):
            before = (ctrl.latest_telemetry["raw_x"], ctrl.latest_telemetry["raw_y"])
            ctrl.update()
            after = (ctrl.latest_telemetry["raw_x"], ctrl.latest_telemetry["raw_y"])
            if after != before:
                seen.append(after[0])
    return seen


def test_frame_split_across_reads_is_reassembled():
    """A frame arriving in pieces must be joined, not parsed as a broken frame."""
    port = FakeSerial()
    seen = collect(port, [b"2000,1968,1\n", b"20", b"06,1973,1\n"])
    assert seen == [2000, 2006], f"expected [2000, 2006], got {seen}"


def test_non_numeric_garbage_is_ignored():
    """ESP32 boot chatter must not be applied as input."""
    port = FakeSerial()
    seen = collect(port, [b"ets Jul 29 2019 12:21:46\n", b"2000,1968,1\n"])
    assert seen == [2000], f"expected [2000], got {seen}"


def test_partial_frame_is_not_applied_until_complete():
    """Half a frame must not reach the modes."""
    port = FakeSerial()
    ctrl = make_controller(port)
    port.deliver(b"2000,196")
    ctrl.update()
    assert ctrl.latest_telemetry["raw_x"] == 2048, "partial frame was applied"
    port.deliver(b"8,1\n")
    ctrl.update()
    assert ctrl.latest_telemetry["raw_x"] == 2000, "completed frame was not applied"


def test_backlog_does_not_replay_as_pointer_movement():
    """A backlog of frames must move the pointer once (the newest), not N times."""
    port = FakeSerial()
    ctrl = make_controller(port)
    ctrl.config["mouse"]["deadzone"] = 150
    MOVES.clear()
    # 50 frames pile up in one batch, stick pushed to raw 3000 (dx = 952)
    port.deliver(b"".join(b"3000,2048,1\n" for _ in range(50)))
    ctrl.update()
    assert len(MOVES) == 1, f"expected 1 pointer move for a 50 frame backlog, got {len(MOVES)}"
    # and it must be the newest frame's delta, not the sum of the backlog
    expected = 952 * ctrl.config["mouse"]["base_speed"]
    assert abs(MOVES[0][1] - expected) < 0.5, f"unexpected move {MOVES[0]}, expected ~{expected}"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL  {name}: {e}")
    print("\nFAILED" if failures else "\nALL TESTS PASSED")
    sys.exit(1 if failures else 0)

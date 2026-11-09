import ctypes
import threading
from ctypes import wintypes


_KERNEL32 = None


def _kernel32():
    global _KERNEL32
    if _KERNEL32 is None:
        _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _KERNEL32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        _KERNEL32.CreateMutexW.restype = wintypes.HANDLE
        _KERNEL32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        _KERNEL32.CreateEventW.restype = wintypes.HANDLE
        _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    return _KERNEL32


class SingleInstance:
    def __init__(self, name: str = "Local\\VantagEdgeAgent"):
        self.name = name
        self._handle = None
        self._event_handle = None
        self.requested = threading.Event()
        self._listening = False

    def acquire(self) -> bool:
        self._handle = _kernel32().CreateMutexW(None, False, self.name)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:
            self.release()
            return False
        self._event_handle = _kernel32().CreateEventW(None, False, False, self.name + "ShowWindow")
        if not self._event_handle:
            self.release()
            raise ctypes.WinError(ctypes.get_last_error())
        return True

    def listen_for_show_requests(self) -> None:
        self._listening = True
        while self._listening:
            result = _kernel32().WaitForSingleObject(self._event_handle, 250)
            if result == 0:
                self.requested.set()

    def notify_existing(self) -> None:
        event = _kernel32().CreateEventW(None, False, False, self.name + "ShowWindow")
        if event:
            _kernel32().SetEvent(event)
            _kernel32().CloseHandle(event)

    def release(self) -> None:
        self._listening = False
        for attribute in ("_handle", "_event_handle"):
            handle = getattr(self, attribute)
            if handle:
                _kernel32().CloseHandle(handle)
                setattr(self, attribute, None)


def show_existing_window(title: str = "Vantag Edge Agent", name: str = "Local\\VantagEdgeAgent") -> None:
    SingleInstance(name).notify_existing()

from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _transform(raw: bytes, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Offline credential protection requires Windows DPAPI")
    buffer = ctypes.create_string_buffer(raw, len(raw))
    source = DataBlob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = DataBlob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(DataBlob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DataBlob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def protect(value: str) -> str:
    return base64.b64encode(_transform(value.encode("utf-8"), False)).decode("ascii")


def unprotect(value: str) -> str:
    return _transform(base64.b64decode(value, validate=True), True).decode("utf-8")

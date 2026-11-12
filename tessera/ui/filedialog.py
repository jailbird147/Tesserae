"""A native Windows "open file" dialog, without pulling in tkinter.

Tessera ships as a single packaged app with tkinter excluded, so the common
Windows dialog is called directly through ctypes.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

OFN_FILEMUSTEXIST = 0x00001000
OFN_PATHMUSTEXIST = 0x00000800
OFN_EXPLORER = 0x00080000
OFN_NOCHANGEDIR = 0x00000008

FILTER = (
    "Word lists (*.txt;*.dic;*.list;*.words)\0*.txt;*.dic;*.list;*.words\0"
    "All files (*.*)\0*.*\0\0"
)


class _OpenFileName(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM),
        ("lpfnHook", wintypes.LPVOID),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", wintypes.LPVOID),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


def _browse(title: str, initial: str) -> str:
    buffer = ctypes.create_unicode_buffer(1024)
    if initial:
        buffer.value = initial
    dialog = _OpenFileName()
    dialog.lStructSize = ctypes.sizeof(_OpenFileName)
    dialog.lpstrFilter = FILTER
    dialog.lpstrFile = buffer
    dialog.nMaxFile = len(buffer)
    dialog.lpstrTitle = title
    dialog.lpstrDefExt = "txt"
    dialog.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_EXPLORER | OFN_NOCHANGEDIR
    if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(dialog)):
        return buffer.value
    return ""


def open_word_list(title: str = "Choose a word list") -> str:
    """Return the chosen path, or "" if the player cancelled or it is unavailable."""
    if os.name != "nt" or os.environ.get("TESSERA_HEADLESS"):
        return ""
    try:
        return _browse(title, "")
    except Exception:
        return ""

"""
macOS Desktop Automation Tools Package.
"""

from nexusai.tools.macos.active_window import GetActiveWindowTool
from nexusai.tools.macos.notify import NotifyTool, send_macos_notification
from nexusai.tools.macos.open_app import OpenAppTool
from nexusai.tools.macos.raw_applescript import RawAppleScriptTool

__all__ = [
    "OpenAppTool",
    "GetActiveWindowTool",
    "RawAppleScriptTool",
    "NotifyTool",
    "send_macos_notification",
]

#!/usr/bin/env python3
import sys
from urllib.parse import urlencode
import xbmc
import xbmcgui
import xbmcaddon
from xbmc import executebuiltin


_URL = sys.argv[0]
HANDLE = int(sys.argv[1])
ADDON = xbmcaddon.Addon()

ID = ADDON.getAddonInfo("id")
NAME = ADDON.getAddonInfo("name")
ADDON_PATH = ADDON.getAddonInfo("path")


def get_setting(name, default=None):
    value = ADDON.getSetting(name)
    if not value:
        return default

    if value == "true":
        return True
    elif value == "false":
        return False
    else:
        return value


def addon_settings():
    return xbmc.executebuiltin("Addon.OpenSettings(%s)" % ID)


def get_int_setting(setting):
    return int(get_setting(setting))


def log(x):
    xbmc.log("[JACKEWLARR] " + str(x), xbmc.LOGINFO)


def get_url(**kwargs):
    return "{}?{}".format(_URL, urlencode(kwargs))


def set_art(list_item, artwork_url):
    if artwork_url:
        list_item.setArt({"poster": artwork_url, "thumb": artwork_url})


def slugify(text):
    return (
        text.lower()
        .replace(" ", "-")
        .replace(",", "")
        .replace("!", "")
        .replace("+", "")
    )


def compat(line1, line2, line3):
    message = line1
    if line2:
        message += "\n" + line2
    if line3:
        message += "\n" + line3
    return message


def notify(message, image=None):
    dialog = xbmcgui.Dialog().notification(NAME, message, icon=image, sound=False)
    del dialog


def dialog_ok(heading, line1, line2="", line3=""):
    return xbmcgui.Dialog().ok(heading, compat(line1=line1, line2=line2, line3=line3))


def execute_builtin(command, block=False):
    return executebuiltin(command, block)


def hide_busy_dialog():
    execute_builtin("Dialog.Close(busydialognocancel)")
    execute_builtin("Dialog.Close(busydialog)")


def bytes_to_human_readable(size, unit="B"):
    units = {"B": 0, "KB": 1, "MB": 2, "GB": 3, "TB": 4, "PB": 5}

    while size >= 1024 and unit != "PB":
        size /= 1024
        unit = list(units.keys())[list(units.values()).index(units[unit] + 1)]

    return f"{size:.2f} {unit}"
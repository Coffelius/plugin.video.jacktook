from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta
import hashlib
import json
import os
import re
import unicodedata
import requests

from lib.api.fanart.fanarttv import FanartTv
from lib.api.jacktook.kodi import kodilog
from lib.api.trakt.trakt_api import clear_cache
from lib.db.bookmark_db import bookmark_db
from lib.api.tvdbapi.tvdbapi import TVDBAPI
from lib.db.cached import cache
from lib.db.main_db import main_db
from lib.api.tmdbv3api.objs.find import Find
from lib.api.tmdbv3api.objs.genre import Genre
from lib.api.tmdbv3api.objs.movie import Movie
from lib.api.tmdbv3api.objs.search import Search
from lib.api.tmdbv3api.objs.season import Season
from lib.api.tmdbv3api.objs.tv import TV

from lib.torf._magnet import Magnet
from lib.fanart import search_api_fanart
from lib.utils.kodi_utils import (
    ADDON_HANDLE,
    ADDON_PATH,
    MOVIES_TYPE,
    SHOWS_TYPE,
    build_url,
    container_refresh,
    get_jacktorr_setting,
    get_setting,
    set_property,
    translation,
)
from lib.utils.settings import get_cache_expiration, is_cache_enabled

from lib.api.tmdbv3api.objs.discover import Discover
from lib.api.tmdbv3api.objs.trending import Trending

from lib.utils.settings import get_int_setting

from lib.utils.torrentio_utils import filter_by_torrentio_provider
from xbmcgui import ListItem, Dialog
from xbmcgui import DialogProgressBG
from xbmcplugin import addDirectoryItem, setContent, endOfDirectory
from xbmc import getSupportedMedia
from zipfile import ZipFile


PROVIDER_COLOR_MIN_BRIGHTNESS = 50

URL_REGEX = r"^(?!\/)(rtmps?:\/\/|mms:\/\/|rtsp:\/\/|https?:\/\/|ftp:\/\/)?([^\/:]+:[^\/@]+@)?(www\.)?(?=[^\/:\s]+\.[^\/:\s]+)([^\/:\s]+\.[^\/:\s]+)(:\d+)?(\/[^#\s]*[\s\S]*)?(\?[^#\s]*)?(#.*)?$"

USER_AGENT_HEADER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
}

TMDB_POSTER_URL = "http://image.tmdb.org/t/p/w780"
TMDB_BACKDROP_URL = "http://image.tmdb.org/t/p/w1280"

dialog_update = {"count": -1, "percent": 50}

video_extensions = (
    ".001",
    ".3g2",
    ".3gp",
    ".asf",
    ".asx",
    ".avc",
    ".avi",
    ".avs",
    ".bdm",
    ".bdmv",
    ".bin",
    ".bivx",
    ".dat",
    ".divx",
    ".dv",
    ".dvr-ms",
    ".evo",
    ".f4v",
    ".fli",
    ".flv",
    ".h264",
    ".img",
    ".iso",
    ".m2t",
    ".m2ts",
    ".m2v",
    ".m3u8",
    ".m4v",
    ".mk3d",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mpl",
    ".mpls",
    ".mts",
    ".nrg",
    ".nuv",
    ".ogm",
    ".ogv",
    ".pva",
    ".qt",
    ".rcv",
    ".rec",
    ".rmvb",
    ".sdp",
    ".svq3",
    ".tp",
    ".trp",
    ".ts",
    ".ty",
    ".udf",
    ".vc1",
    ".vdr",
    ".viv",
    ".vob",
    ".vp3",
    ".webm",
    ".wmv",
    ".xvid",
)


class Enum:
    @classmethod
    def values(cls):
        return [value for name, value in vars(cls).items() if not name.startswith("_")]


torrent_clients = ["Jacktorr", "Torrest", "Elementum"]

torrent_indexers = ["Prowlarr", "Jackett", "Torrentio", "Elfhosted", "Burst"]


class Debrids(Enum):
    RD = "RealDebrid"
    PM = "Premiumize"
    TB = "Torbox"
    ED = "EasyDebrid"


class Indexer(Enum):
    PROWLARR = "Prowlarr"
    JACKETT = "Jackett"
    TORRENTIO = "Torrentio"
    MEDIAFUSION = "MediaFusion"
    JACKGRAM = "Jackgram"
    ELHOSTED = "Elfhosted"
    BURST = "Burst"
    ZILEAN = "Zilean"


class Players(Enum):
    JACKTORR = "Jacktorr"
    TORREST = "Torrest"
    ELEMENTUM = "Elementum"
    DEBRID = "Debrid"
    JACKGRAM = "Jackgram"


class Anime(Enum):
    SEARCH = "Anime_Search"
    POPULAR = "Anime_Popular"
    TRENDING = "Anime_Trending"
    AIRING = "Anime_On_The_Air"
    MOST_WATCHED = "Anime_Most_Watched"


class DialogListener:
    def __init__(self):
        self._dialog = DialogProgressBG()

    @property
    def dialog(self):
        return self._dialog

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._dialog.close()
        except:
            pass


def is_debrid_activated():
    return (
        get_setting("real_debrid_enabled")
        or get_setting("premiumize_enabled")
        or get_setting("torbox_enabled")
        or get_setting("easydebrid_enabled")
    )


def check_debrid_enabled(type):
    if type == Debrids.RD:
        return is_rd_enabled()
    elif type == Debrids.PM:
        return is_pm_enabled()
    elif type == Debrids.TB:
        return is_tb_enabled()
    elif type == Debrids.ED:
        return is_ed_enabled()


def is_rd_enabled():
    return get_setting("real_debrid_enabled")


def is_pm_enabled():
    return get_setting("premiumize_enabled")


def is_tb_enabled():
    return get_setting("torbox_enabled")


def is_ed_enabled():
    return get_setting("easydebrid_enabled")


def list_item(label, icon):
    item = ListItem(label)
    item.setArt(
        {
            "icon": os.path.join(ADDON_PATH, "resources", "img", icon),
            "thumb": os.path.join(ADDON_PATH, "resources", "img", icon),
            "fanart": os.path.join(ADDON_PATH, "fanart.png"),
        }
    )
    return item


def set_video_properties(list_item, poster, mode, title, overview, ids):
    set_media_infotag(list_item, mode, title, overview, ids=ids)
    list_item.setProperty("IsPlayable", "true")
    list_item.setArt(
        {
            "poster": poster,
            "fanart": poster,
            "icon": os.path.join(ADDON_PATH, "resources", "img", "magnet.png"),
        }
    )


def set_video_info(
    list_item,
    mode,
    name,
    overview="",
    ids="",
    season_number="",
    episode="",
    ep_name="",
    duration="",
    air_date="",
    url="",
):
    info = {"plot": overview}

    if ids:
        _, _, imdb_id = ids.split(", ")
        info["imdbnumber"] = imdb_id

    if duration:
        info["duration"] = int(duration)

    if mode in ["movies", "multi"]:
        info.update({"mediatype": "movie", "title": name, "originaltitle": name})
    else:
        info.update({"mediatype": "tvshow", "tvshowtitle": name})
        if ep_name:
            info["title"] = name
        if url:
            info["filenameandpath"] = url
        if air_date:
            info["aired"] = air_date
        if season_number:
            info["season"] = int(season_number)
        if episode:
            info["episode"] = int(episode)

    list_item.setInfo("video", info)


def make_listing(metadata):
    title = metadata.get("title")
    ids = metadata.get("ids")
    tv_data = metadata.get("tv_data", {})
    mode = metadata.get("mode", "")

    list_item = ListItem(label=title)
    list_item.setLabel(title)
    list_item.setPath(metadata.get("url"))
    list_item.setContentLookup(False)

    if tv_data:
        ep_name, episode, season = tv_data.split("(^)")
    else:
        ep_name = episode = season = ""

    set_media_infotag(
        list_item,
        mode,
        title,
        season_number=season,
        episode=episode,
        ep_name=ep_name,
        ids=ids,
    )

    set_windows_property(mode, ids)
    return list_item


def set_media_infotag(
    list_item,
    mode,
    name,
    overview="",
    ids="",
    season_number="",
    episode="",
    ep_name="",
    duration="",
    air_date="",
    url="",
):
    info_tag = list_item.getVideoInfoTag()
    if mode == "movies":
        info_tag.setMediaType("movie")
        info_tag.setTitle(name)
        info_tag.setOriginalTitle(name)
    elif mode == "multi":
        info_tag.setMediaType("video")
        info_tag.setTitle(name)
    else:
        info_tag.setMediaType("season")
        if ep_name:
            info_tag.setTitle(f"{ep_name} S{int(season_number):02d}E{int(episode):02d}")
        info_tag.setTvShowTitle(name)
        if url:
            info_tag.setFilenameAndPath(url)
        if air_date:
            info_tag.setFirstAired(air_date)
        if season_number:
            info_tag.setSeason(int(season_number))
        if episode:
            info_tag.setEpisode(int(episode))

    list_item.setProperty("IsPlayable", "true")

    info_tag.setPlot(overview)
    if duration:
        info_tag.setDuration(int(duration))
    if ids:
        tmdb_id, tvdb_id, imdb_id = ids.split(", ")
        info_tag.setIMDBNumber(imdb_id)
        info_tag.setUniqueIDs(
            {"imdb": str(imdb_id), "tmdb": str(tmdb_id), "tvdb": str(tvdb_id)}
        )


def set_windows_property(mode, ids):
    if ids:
        tmdb_id, tvdb_id, imdb_id = ids.split(", ")
        if mode == "movies":
            ids = {
                "tmdb": tmdb_id,
                "imdb": imdb_id,
            }
        else:
            ids = {
                "tvdb": tvdb_id,
            }
        set_property(
            "script.trakt.ids",
            json.dumps(ids),
        )


def set_watched_file(title, is_torrent, extra_data):
    if title in main_db.database["jt:lfh"]:
        return

    if is_torrent:
        color = get_random_color("Direct")
        title = f"[B][COLOR {color}][Direct][/COLOR][/B] - {title}"
    else:
        color = get_random_color("Cached")
        title = f"[B][COLOR {color}][Cached][/COLOR][/B] - {title}"

    if title not in main_db.database["jt:watch"]:
        main_db.database["jt:watch"][title] = True

    main_db.database["jt:lfh"][title] = {
        "timestamp": datetime.now(),
        "ids": extra_data.get("ids", []),
        "tv_data": extra_data.get("tv_data", {}),
        "url": extra_data.get("url", ""),
        "is_torrent": is_torrent,
        "magnet": extra_data.get("magnet", ""),
        "info_hash": extra_data.get("info_hash", ""),
        "type": extra_data.get("type", ""),
        "is_pack": extra_data.get("is_pack", False),
        "file_id": extra_data.get("pack_info", {}).get("file_id", ""),
        "torrent_id": extra_data.get("pack_info", {}).get("torrent_id", ""),
    }
    main_db.commit()


def set_watched_title(title, ids, mode="", media_type=""):
    if mode == "multi":
        mode = media_type
    if title != "None":
        main_db.database["jt:lth"][title] = {
            "timestamp": datetime.now(),
            "ids": ids,
            "mode": mode,
        }
        main_db.commit()


def is_torrent_watched(title):
    return main_db.database["jt:watch"].get(title, False)


def get_fanart_details(tvdb_id="", tmdb_id="", mode="tv"):
    identifier = "{}|{}".format("fanart.tv", tvdb_id)
    data = cache.get(identifier, hashed_key=True)
    if data:
        return data
    else:
        fanart = FanartTv(get_setting("fanart_tv_client_id"))
        if mode == "tv":
            results = fanart.get_show(tvdb_id)
            data = get_fanart_data(results)
        else:
            results = fanart.get_movie(tmdb_id)
            data = get_fanart_data(results)
        if data:
            cache.set(
                identifier,
                data,
                timedelta(hours=get_cache_expiration() if is_cache_enabled() else 0),
                hashed_key=True,
            )
    return data


def get_fanart_data(fanart_details):
    fanart_objec = fanart_details["fanart_object"]
    fanart = clearlogo = poster = ""
    if fanart_objec:
        art = fanart_objec.get("art", {})
        fanart_obj = art.get("fanart", {})
        if fanart_obj:
            fanart = fanart_obj[0]["url"]

        clearlogo_obj = art.get("clearlogo", {})
        if clearlogo_obj:
            clearlogo = clearlogo_obj[0]["url"]

        poster_obj = art.get("poster", {})
        if poster_obj:
            poster = poster_obj[0]["url"]

    return {"fanart": fanart, "clearlogo": clearlogo, "poster": poster}


def get_cached(path, params={}):
    identifier = "{}|{}".format(path, params)
    return cache.get(identifier, hashed_key=True)


def set_cached(data, path, params={}):
    identifier = "{}|{}".format(path, params)
    cache.set(
        identifier,
        data,
        timedelta(hours=get_cache_expiration() if is_cache_enabled() else 0),
        hashed_key=True,
    )


def db_get(name, func, path, params):
    identifier = "{}|{}".format(path, params)
    data = cache.get(identifier, hashed_key=True)
    if not data:
        if name == "search_client":
            data = func()
        cache.set(
            identifier,
            data,
            timedelta(hours=get_cache_expiration() if is_cache_enabled() else 0),
            hashed_key=True,
        )
    return data


def tvdb_get(path, params={}):
    identifier = "{}|{}".format(path, params)
    data = cache.get(identifier, hashed_key=True)
    if data:
        return data
    if path == "get_imdb_id":
        data = TVDBAPI().get_imdb_id(params)
    cache.set(
        identifier,
        data,
        timedelta(hours=get_cache_expiration() if is_cache_enabled() else 0),
        hashed_key=True,
    )
    return data


def tmdb_get(path, params={}):
    identifier = "{}|{}".format(path, params)
    data = cache.get(identifier, hashed_key=True)
    if data:
        return data
    if path == "search_tv":
        data = Search().tv_shows(params)
    elif path == "search_movie":
        data = Search().movies(params)
    elif path == "movie_details":
        data = Movie().details(params)
    elif path == "tv_details":
        data = TV().details(params)
    elif path == "season_details":
        data = Season().details(params["id"], params["season"])
    elif path == "movie_genres":
        data = Genre().movie_list()
    elif path == "tv_genres":
        data = Genre().tv_list()
    elif path == "discover_movie":
        discover = Discover()
        data = discover.discover_movies(params)
    elif path == "discover_tv":
        discover = Discover()
        data = discover.discover_tv_shows(params)
    elif path == "trending_movie":
        trending = Trending()
        data = trending.movie_week(page=params)
    elif path == "trending_tv":
        trending = Trending()
        data = trending.tv_week(page=params)
    elif path == "find_by_tvdb":
        data = Find().find_by_tvdb_id(params)
    cache.set(
        identifier,
        data,
        timedelta(hours=get_cache_expiration() if is_cache_enabled() else 0),
        hashed_key=True,
    )
    return data


def get_tmdb_movie_data(id):
    details = tmdb_get("movie_details", id)
    imdb_id = details.external_ids.get("imdb_id")
    runtime = details.runtime
    return imdb_id, runtime


def get_tmdb_tv_data(id):
    details = tmdb_get("tv_details", id)
    imdb_id = details.external_ids.get("imdb_id")
    tvdb_id = details.external_ids.get("tvdb_id")
    return imdb_id, tvdb_id


def set_content_type(mode, media_type="movies"):
    if mode == "tv" or media_type == "tv" or mode == "anime":
        setContent(ADDON_HANDLE, MOVIES_TYPE)
    elif mode == "movies" or media_type == "movies":
        setContent(ADDON_HANDLE, SHOWS_TYPE)


# This method was taken from script.elementum.jackett addon
def get_random_color(provider_name):
    hash = hashlib.sha256(provider_name.encode("utf")).hexdigest()
    colors = []

    spec = 10
    for i in range(0, 3):
        offset = spec * i
        rounded = round(
            int(hash[offset : offset + spec], 16) / int("F" * spec, 16) * 255
        )
        colors.append(int(max(rounded, PROVIDER_COLOR_MIN_BRIGHTNESS)))

    while (sum(colors) / 3) < PROVIDER_COLOR_MIN_BRIGHTNESS:
        for i in range(0, 3):
            colors[i] += 10

    for i in range(0, 3):
        colors[i] = f"{colors[i]:02x}"

    return "FF" + "".join(colors).upper()


def get_colored_languages(languages):
    if not languages:
        return ""
    colored_languages = []
    for lang in languages:
        lang_color = get_random_color(lang)
        colored_lang = f"[B][COLOR {lang_color}][{lang}][/COLOR][/B]"
        colored_languages.append(colored_lang)
    colored_languages = " ".join(colored_languages)
    return colored_languages


def execute_thread_pool(results, func, *args, **kwargs):
    with ThreadPoolExecutor(max_workers=len(results)) as executor:
        [executor.submit(func, res, *args, **kwargs) for res in results]
        executor.shutdown(wait=True)


def paginate_list(data, page_size=10):
    for i in range(0, len(data), page_size):
        yield data[i : i + page_size]


def clear_all_cache():
    cache.clean_all()
    bookmark_db.clear_bookmarks()
    clear_cache(cache_type="trakt")
    clear_cache(cache_type="list")
    clear(type="lth")
    clear(type="lfh")


def clear(type="lth"):
    dialog = Dialog()
    confirmed = dialog.yesno(
        "Clear History",
        "Do you want to clear this history list?.",
    )
    if confirmed:
        if type == "lth":
            main_db.database["jt:lth"] = {}
        else:
            main_db.database["jt:lfh"] = {}
        main_db.commit()
        container_refresh()


def limit_results(results):
    indexer = get_setting("indexer")
    if indexer == Indexer.JACKETT:
        limit = get_int_setting("jackett_results_per_page")
    elif indexer == Indexer.PROWLARR:
        limit = get_int_setting("prowlarr_results_per_page")
    elif indexer == Indexer.TORRENTIO:
        limit = get_int_setting("torrentio_results_per_page")
    elif indexer == Indexer.ELHOSTED:
        limit = get_int_setting("elfhosted_results_per_page")
    elif indexer == Indexer.JACKGRAM:
        limit = get_int_setting("jackgram_results_per_page")
    else:
        limit = 50
    return results[:limit]


def get_description_length():
    indexer = get_setting("indexer")
    if indexer == Indexer.JACKETT:
        desc_length = "jackett_desc_length"
    elif indexer == Indexer.PROWLARR:
        desc_length = "prowlarr_desc_length"
    elif indexer == Indexer.TORRENTIO:
        desc_length = "torrentio_desc_length"
    elif indexer == Indexer.ELHOSTED:
        desc_length = "elfhosted_desc_length"
    elif indexer == Indexer.JACKGRAM:
        desc_length = "jackgram_desc_length"
    else:
        desc_length = 150
        return desc_length
    return int(get_setting(desc_length))


def remove_duplicate(results):
    seen_values = []
    result_dict = []
    for res in results:
        if res not in seen_values:
            result_dict.append(res)
            seen_values.append(res)
    return result_dict


def unzip(zip_location, destination_location, destination_check):
    try:
        zipfile = ZipFile(zip_location)
        zipfile.extractall(path=destination_location)
        if os.path.exists(destination_check):
            status = True
        else:
            status = False
    except:
        status = False
    return status


def post_process(res, season=None):
    kodilog("utils::post_process")
    if season:
        check_pack(res, season)
    if (
        get_setting("indexer") == Indexer.TORRENTIO
        and get_setting("torrentio_priority_lang") != "None"
    ):
        res = sort_by_priority_language(res)
    else:
        res = sort_results(res)
    return res


def check_pack(results, season_num):
    season_fill = f"{int(season_num):02}"
    pattern1 = r"\.S%s\." % (season_num)
    pattern2 = r"\.S%s\." % (season_fill)
    pattern3 = r"\sS%s\s" % (season_num)
    pattern4 = r"\.%s\.season" % (season_num)
    pattern5 = r"total\.season"
    pattern6 = r"season"
    pattern7 = r"the\.complete"
    pattern8 = r"complete"
    pattern9 = r"\.season\.%s\." % season_num
    pattern10 = r"\.season%s\." % season_num
    pattern11 = r"\.season\.%s\." % season_fill
    pattern12 = r"\sS%s\s" % (season_fill)

    patterns = "|".join(
        [
            pattern1,
            pattern2,
            pattern3,
            pattern4,
            pattern5,
            pattern6,
            pattern7,
            pattern8,
            pattern9,
            pattern10,
            pattern11,
            pattern12,
        ]
    )

    for res in results:
        match = re.search(f"{patterns}", res["title"])
        if match:
            res["isPack"] = True
        else:
            res["isPack"] = False


def pre_process(res, mode, episode_name, episode, season):
    kodilog("utils::pre_process")
    res = remove_duplicate(res)
    if get_setting("indexer") == Indexer.TORRENTIO:
        res = filter_by_torrentio_provider(res)
    res = limit_results(res)
    if mode == "tv":
        res = filter_by_episode(res, episode_name, episode, season)
    res = filter_by_quality(res)
    return res


def sort_by_priority_language(results):
    priority_lang = get_setting("torrentio_priority_lang")
    priority_lang_list = []
    non_priority_lang_list = []
    for res in results:
        if "languages" in res and priority_lang in res["languages"]:
            priority_lang_list.append(res)
        else:
            non_priority_lang_list.append(res)
    return sort_results(priority_lang_list, non_priority_lang_list)


def filter_by_priority_language(results):
    indexer = get_setting("indexer")
    if indexer == Indexer.TORRENTIO:
        filtered_results = []
        priority_lang = get_setting("torrentio_priority_lang")
        for res in results:
            if priority_lang in res["languages"]:
                filtered_results.append(res)
        return filtered_results


def sort_results(first_res, second_res=None):
    indexer = get_setting("indexer")
    if indexer == Indexer.JACKETT:
        sort_by = get_setting("jackett_sort_by")
    elif indexer == Indexer.PROWLARR:
        sort_by = get_setting("prowlarr_sort_by")
    elif indexer == Indexer.TORRENTIO:
        sort_by = get_setting("torrentio_sort_by")
    elif indexer == Indexer.ELHOSTED:
        sort_by = get_setting("elfhosted_sort_by")
    elif indexer == Indexer.BURST:
        sort_by = get_setting("burst_sort_by")
    elif indexer == Indexer.JACKGRAM:
        sort_by = get_setting("jackgram_sort_by")
    else:
        sort_by = "None"

    if sort_by == "Seeds":
        first_sorted = sorted(first_res, key=lambda r: r["seeders"], reverse=True)
        if second_res:
            return sort_second_result(first_sorted, second_res, type="seeders")
    elif sort_by == "Size":
        first_sorted = sorted(first_res, key=lambda r: r["size"], reverse=True)
        if second_res:
            return sort_second_result(first_sorted, second_res, type="size")
    elif sort_by == "Date":
        first_sorted = sorted(first_res, key=lambda r: r["publishDate"], reverse=True)
        if second_res:
            return sort_second_result(first_sorted, second_res, type="publishDate")
    elif sort_by == "Quality":
        first_sorted = sorted(first_res, key=lambda r: r["quality"], reverse=True)
        if second_res:
            return sort_second_result(first_sorted, second_res, type="quality")
    elif sort_by == "Cached":
        first_sorted = sorted(
            first_res, key=lambda r: r.get("isCached", ""), reverse=True
        )
        if second_res:
            return sort_second_result(first_sorted, second_res, type="isCached")
    else:
        return first_res

    return first_sorted


def sort_second_result(first_sorted, second_res, type):
    second_sorted = sorted(second_res, key=lambda r: r[type], reverse=True)
    first_sorted.extend(second_sorted)
    return first_sorted


def filter_by_episode(results, episode_name, episode_num, season_num):
    episode_fill = f"{int(episode_num):02}"
    season_fill = f"{int(season_num):02}"
    pattern1 = r"S%sE%s" % (season_fill, episode_fill)
    pattern2 = r"%sx%s" % (season_fill, episode_fill)
    pattern3 = r"\s%s\s" % (season_fill)
    pattern4 = r"\.S%s" % (season_fill)
    pattern5 = r"\.S%sE%s" % (season_fill, episode_fill)
    pattern6 = r"\sS%sE%s\s" % (season_fill, episode_fill)

    patterns = "|".join(
        [pattern1, pattern2, pattern3, pattern4, pattern5, pattern6, episode_name]
    )

    filtered_episodes = []
    for res in results:
        match = re.search(f"{patterns}", res["title"])
        if match:
            filtered_episodes.append(res)
    return filtered_episodes


def filter_by_quality(results):
    quality_720p = []
    quality_1080p = []
    quality_4k = []
    no_quarlity = []

    for res in results:
        title = res["title"]
        if "480p" in title:
            res["quality"] = "[B][COLOR orange]480p[/COLOR][/B]"
            quality_720p.append(res)
        elif "720p" in title:
            res["quality"] = "[B][COLOR orange]720p[/COLOR][/B]"
            quality_720p.append(res)
        elif "1080p" in title:
            res["quality"] = "[B][COLOR blue]1080p[/COLOR][/B]"
            quality_1080p.append(res)
        elif "2160" in title:
            res["quality"] = "[B][COLOR yellow]4k[/COLOR][/B]"
            quality_4k.append(res)
        else:
            res["quality"] = "[B][COLOR yellow]N/A[/COLOR][/B]"
            no_quarlity.append(res)

    combined_list = quality_4k + quality_1080p + quality_720p + no_quarlity
    return combined_list


def clean_auto_play_undesired(results):
    undesired = ("SD", "CAM", "TELE", "SYNC", "480p")
    for res in copy.deepcopy(results):
        if res.get("isPack"):
            results.remove(res)
        else:
            if any(u in res["title"] for u in undesired):
                results.remove(res)
    return results[0]


def is_torrent_url(uri):
    res = requests.head(uri, timeout=20, headers=USER_AGENT_HEADER)
    if (
        res.status_code == 200
        and res.headers.get("Content-Type") == "application/octet-stream"
    ):
        return True
    else:
        return False


def supported_video_extensions():
    media_types = getSupportedMedia("video")
    return media_types.split("|")


def add_next_button(func_name, page=1, **kwargs):
    list_item = ListItem(label="Next")
    list_item.setArt(
        {"icon": os.path.join(ADDON_PATH, "resources", "img", "nextpage.png")}
    )

    page += 1
    addDirectoryItem(
        ADDON_HANDLE,
        build_url(func_name, page=page, **kwargs),
        list_item,
        isFolder=True,
    )
    endOfDirectory(ADDON_HANDLE)


def is_video(s):
    return s.lower().endswith(video_extensions)


def get_info_hash_from_magnet(magnet):
    return Magnet.from_string(magnet).infohash


def is_magnet_link(link):
    if link.startswith("magnet:?"):
        return link


def is_url(url):
    return bool(re.match(URL_REGEX, url))


def info_hash_to_magnet(info_hash):
    return f"magnet:?xt=urn:btih:{info_hash}"


def get_state_string(state):
    if 0 <= state <= 9:
        return translation(30650 + state)
    return translation(30660)


def get_service_host():
    return get_jacktorr_setting("service_host")


def get_username():
    return get_jacktorr_setting("service_login")


def get_password():
    return get_jacktorr_setting("service_password")


def ssl_enabled():
    return get_jacktorr_setting("ssl_connection")


def get_port():
    return get_jacktorr_setting("service_port")


def unicode_flag_to_country_code(unicode_flag):
    if len(unicode_flag) != 2:
        return "Invalid flag Unicode"

    first_letter = unicodedata.name(unicode_flag[0]).replace(
        "REGIONAL INDICATOR SYMBOL LETTER ", ""
    )
    second_letter = unicodedata.name(unicode_flag[1]).replace(
        "REGIONAL INDICATOR SYMBOL LETTER ", ""
    )

    country_code = first_letter.lower() + second_letter.lower()
    return country_code


def debrid_dialog_update(type, total, dialog, lock):
    with lock:
        dialog_update["count"] += 1
        dialog_update["percent"] += 2

        dialog.update(
            dialog_update.get("percent"),
            f"Jacktook [COLOR FFFF6B00]Debrid-{type}[/COLOR]",
            f"Checking: {dialog_update.get('count')}/{total}",
        )


def get_public_ip():
    public_ip = cache.get("public_ip")
    if not public_ip:
        try:
            response = requests.get("https://ipconfig.io/ip", timeout=5)
            response.raise_for_status()
            public_ip = response.text.strip()
            cache.set(
                "public_ip",
                public_ip,
                timedelta(hours=get_cache_expiration() if is_cache_enabled() else 0),
            )
        except requests.RequestException as e:
            kodilog(f"Error getting public ip: {e}")
            return None
    return public_ip


def extract_publish_date(date):
    if not date:
        return ""
    match = re.search(r"\d{4}-\d{2}-\d{2}", date)
    return match.group() if match else ""

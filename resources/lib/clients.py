import json
from urllib.parse import quote
import requests
from resources.lib.kodi import get_setting, log, notify, translation

from resources.lib.utils import Indexer
from resources.lib.kodi import hide_busy_dialog
from urllib3.exceptions import InsecureRequestWarning

from xbmcgui import DialogProgressBG
from xbmc import Keyboard


def get_client():
    selected_indexer = get_setting("selected_indexer")

    if selected_indexer == Indexer.JACKETT:
        host = get_setting("jackett_host")
        host = host.rstrip("/")
        api_key = get_setting("jackett_apikey")

        if not host or not api_key:
            notify(translation(30220))
            return

        if len(api_key) != 32:
            notify(translation(30221))
            return

        return Jackett(host, api_key)

    elif selected_indexer == Indexer.PROWLARR:
        host = get_setting("prowlarr_host")
        host = host.rstrip("/")
        api_key = get_setting("prowlarr_apikey")

        if not host or not api_key:
            notify(translation(30223))
            return

        if len(api_key) != 32:
            notify(translation(30224))
            return

        return Prowlarr(host, api_key)


class Jackett:
    def __init__(self, host, apikey) -> None:
        self.host = host
        self.apikey = apikey

    def search(self, query, tracker, mode, insecure=False):
        try:
            if tracker == "anime":
                url = f"{self.host}/api/v2.0/indexers/nyaasi/results?apikey={self.apikey}&t=search&Query={query}"
            elif tracker == "all":
                if mode == "tv":
                    url = f"{self.host}/api/v2.0/indexers/all/results?apikey={self.apikey}&t=tvsearch&Query={query}"
                elif mode == "movie":
                    url = f"{self.host}/api/v2.0/indexers/all/results?apikey={self.apikey}&t=movie&Query={query}"
                elif mode == "multi":
                    url = f"{self.host}/api/v2.0/indexers/all/results?apikey={self.apikey}&t=search&Query={query}"
            res = requests.get(url, verify=insecure)
            if res.status_code != 200:
                notify(f"{translation(30229)} ({res.status_code})")
                return
            return self._parse_response(res)
        except Exception as e:
            notify(f"{translation(30229)} {str(e)}")
            return

    def _parse_response(self, response):
        results = []
        res_dict = json.loads(response.content)
        for res in res_dict["Results"]:
            model = {
                "title": res["Title"],
                "indexer": res["Tracker"],
                "publishDate": res["PublishDate"],
                "guid": res["Guid"],
                "magnetUrl": res["MagnetUri"],
                "downloadUrl": res["Link"],
                "size": res["Size"],
                "seeders": res["Seeders"],
                "peers": res["Peers"],
                "infoHash": res["InfoHash"],
            }
            results.append(model)
        return results


class Prowlarr:
    def __init__(self, host, apikey) -> None:
        self.host = host
        self.apikey = apikey

    def search(self, query, tracker, indexers, anime_indexers, mode, insecure=False):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Api-Key": self.apikey,
        }
        try:
            if tracker == "anime":
                if anime_indexers:
                    anime_indexers_url = "".join(
                        [f"&IndexerIds={index}" for index in anime_indexers]
                    )
                    url = f"{self.host}/api/v1/search?query={query}{anime_indexers_url}"
                else:
                    notify(translation(30231))
                    return
            elif tracker == "all":
                if mode == "tv":
                    url = f"{self.host}/api/v1/search?query={query}&Categories=5000"
                elif mode == "movie":
                    url = f"{self.host}/api/v1/search?query={query}&Categories=2000"
                elif mode == "multi":
                    url = f"{self.host}/api/v1/search?query={query}"
                if indexers:
                    indexers_url = "".join(
                        [f"&IndexerIds={index}" for index in indexers]
                    )
                    url = url + indexers_url
            res = requests.get(url, verify=insecure, headers=headers)
            if res.status_code != 200:
                notify(f"{translation(30230)} {res.status_code}")
                return
            return json.loads(res.text)
        except Exception as e:
            notify(f"{translation(30230)} {str(e)}")
            return


def search_api(query, mode, tracker):
    query = None if query == "None" else query

    selected_indexer = get_setting("selected_indexer")
    jackett_insecured = get_setting("jackett_insecured")
    prowlarr_insecured = get_setting("prowlarr_insecured")

    if prowlarr_insecured or jackett_insecured:
        requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

    p_dialog = DialogProgressBG()

    if selected_indexer == Indexer.JACKETT:
        jackett = get_client()
        if not jackett:
            return

        if not query:
            keyboard = Keyboard("", "Search for torrents:", False)
            keyboard.doModal()
            if keyboard.isConfirmed():
                text = keyboard.getText().strip()
                p_dialog.create(
                    "Jacktook [COLOR FFFF6B00]Jackett[/COLOR]", "Searching..."
                )
                response = jackett.search(quote(text), tracker, mode, jackett_insecured)
            else:
                hide_busy_dialog()
                return
        else:
            p_dialog.create("Jacktook [COLOR FFFF6B00]Jackett[/COLOR]", "Searching...")
            response = jackett.search(query, tracker, mode, jackett_insecured)

    elif selected_indexer == Indexer.PROWLARR:
        indexers_ids = get_setting("prowlarr_indexer_ids")
        indexers_ids_list = indexers_ids.split() if indexers_ids else None

        anime_ids = get_setting("prowlarr_anime_indexer_ids")
        anime_indexers_ids_list = anime_ids.split() if anime_ids else None

        prowlarr = get_client()
        if not prowlarr:
            return

        if not query:
            keyboard = Keyboard("", "Search for torrents:", False)
            keyboard.doModal()
            if keyboard.isConfirmed():
                text = keyboard.getText().strip()
                text = quote(text)
                p_dialog.create(
                    "Jacktook [COLOR FFFF6B00]Prowlarr[/COLOR]", "Searching..."
                )
                response = prowlarr.search(
                    text,
                    tracker,
                    indexers_ids_list,
                    anime_indexers_ids_list,
                    mode,
                    prowlarr_insecured,
                )
            else:
                hide_busy_dialog()
                return
        else:
            p_dialog.create("Jacktook [COLOR FFFF6B00]Prowlarr[/COLOR]", "Searching...")
            response = prowlarr.search(
                query,
                tracker,
                indexers_ids_list,
                anime_indexers_ids_list,
                mode,
                prowlarr_insecured,
            )

    p_dialog.close()
    del p_dialog

    return response

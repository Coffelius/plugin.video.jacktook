from datetime import timedelta
import os
import threading
from lib.api.tmdbv3api.objs.anime import TmdbAnime
from lib.api.tmdbv3api.objs.find import Find
from lib.api.tmdbv3api.objs.genre import Genre
from lib.api.tmdbv3api.objs.movie import Movie
from lib.api.tmdbv3api.objs.search import Search
from lib.api.tmdbv3api.objs.season import Season
from lib.api.tmdbv3api.objs.discover import Discover
from lib.api.tmdbv3api.objs.trending import Trending
from lib.api.tmdbv3api.objs.tv import TV
from lib.utils.kodi_utils import ADDON_PATH
from lib.utils.settings import get_cache_expiration, is_cache_enabled
from lib.db.cached import cache
from lib.utils.utils import execute_thread_pool


def add_icon_genre(item, name):
    genre_icons = {
        "Action": "genre_action.png",
        "Adventure": "genre_adventure.png",
        "Action & Adventure": "genre_adventure.png",
        "Science Fiction": "genre_scifi.png",
        "Sci-Fi & Fantasy": "genre_scifi.png",
        "Fantasy": "genre_fantasy.png",
        "Animation": "genre_animation.png",
        "Comedy": "genre_comedy.png",
        "Crime": "genre_crime.png",
        "Documentary": "genre_documentary.png",
        "Kids": "genre_kids.png",
        "News": "genre_news.png",
        "Reality": "genre_reality.png",
        "Soap": "genre_soap.png",
        "Talk": "genre_talk.png",
        "Drama": "genre_drama.png",
        "Family": "genre_family.png",
        "History": "genre_history.png",
        "Horror": "genre_horror.png",
        "Music": "genre_music.png",
        "Mystery": "genre_mystery.png",
        "Romance": "genre_romance.png",
        "Thriller": "genre_thriller.png",
        "War": "genre_war.png",
        "War & Politics": "genre_war.png",
        "Western": "genre_western.png",
    }
    icon_path = genre_icons.get(name)
    if icon_path:
        item.setArt(
            {
                "icon": os.path.join(ADDON_PATH, "resources", "img", icon_path),
                "thumb": os.path.join(ADDON_PATH, "resources", "img", icon_path),
            }
        )


def add_icon_tmdb(item, icon_path="tmdb.png"):
    item.setArt(
        {
            "icon": os.path.join(ADDON_PATH, "resources", "img", icon_path),
            "thumb": os.path.join(ADDON_PATH, "resources", "img", icon_path),
        }
    )


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


def get_tmdb_media_details(id, mode):
    if not id:
        return
    if mode == "tv":
        details = tmdb_get("tv_details", id)
    elif mode == "movies":
        details = tmdb_get("movie_details", id)
    return details


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


def anime_checker(results, mode):
    anime_results = []
    anime = TmdbAnime()
    list_lock = threading.Lock()

    def task(res, anime_results, list_lock):
        results = anime.tmdb_keywords(mode, res["id"])
        if mode == "tv":
            keywords = results["results"]
        else:
            keywords = results["keywords"]
        for i in keywords:
            if i["id"] == 210024:
                with list_lock:
                    anime_results.append(res)

    execute_thread_pool(results, task, anime_results, list_lock)
    results["results"] = anime_results
    results["total_results"] = len(anime_results)
    return results
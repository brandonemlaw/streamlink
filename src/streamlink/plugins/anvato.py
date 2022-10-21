"""
$description Global live streaming platform used by various US media outlets, including many local news stations.
$url w3.mp.lura.live
$type live
"""

import logging
import re
import base64
import urllib
import json
from datetime import datetime
from time import time
from urllib.parse import urljoin, urlparse

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.plugin import parse_params
from streamlink.stream.hls import HLSStream, HLSStreamReader, HLSStreamWorker, HLSStreamWriter
from streamlink.stream.dash import DASHStream
from streamlink.plugin.api import validate

log = logging.getLogger(__name__)


class AnvatoHLSStream(HLSStream):
    __shortname__ = "hls-anvato"

    def __init__(self, session_, url, page_url=None, q=None, **args):
        super().__init__(session_, url, None, **args)
        self._page_url = page_url
        self._q = q
        self._watch_increment = 30 #30 seconds

        self.watch_timeout = int(time()) + self._watch_increment 
        self.api = AnvatoApi(session_, page_url)

        new_url = self.getUrlFromApi()
        log.debug(f"Url: {url}")
        log.debug(f"New-url: {new_url}")
        self._url = url

        first_parsed = urlparse(self._url)
        self._first_netloc = first_parsed.netloc
        self.watch_timeout = int(time()) + self._watch_increment

    def _next_watch_timeout(self):
        _next = datetime.fromtimestamp(self.watch_timeout).isoformat(" ")
        log.debug(f"next watch_timeout at {_next}")

    def open(self):
        self._next_watch_timeout()
        return super().open()

    @property
    def url(self):
        if int(time()) >= self.watch_timeout:
            log.debug("Reloading HLS URL")
            _hls_url = self.getUrlFromApi()
            log.debug(f"HLS URL: {_hls_url}")
            if not _hls_url:
                self.watch_timeout += 10
                return self._url

            self.watch_timeout = int(time()) + self._watch_increment
            self._next_watch_timeout()

            original_parsed = urlparse(self._url)
            original_ts = urllib.parse.parse_qs(original_parsed.query)['ts'][0]
            
            parsed = urlparse(_hls_url)
            ts = urllib.parse.parse_qs(parsed.query)['ts'][0]
            
            log.debug(f"Replacing: {self._url}")
            self._url = parsed._replace(
                query = parsed.query.replace(f"ts={ts}", f"ts={original_ts}")).geturl()
            log.debug(f"with: {self._url}")
        return self._url
    
    def getUrlFromApi(self):
        url_hls = self.api.get_hls_url()
            
        if not url_hls:
            return
        for q, s in HLSStream.parse_variant_playlist(self.session, url_hls).items():
            if q == self._q:
                log.debug(f"s: {s}")
                return s.url
        


class AnvatoApi:
    def __init__(self, session, page_url):
        self.session = session
        self.page_url = page_url
        self.api_url = None

    def get_api_url(self):
        if not self.api_url:
            getResult = self.session.http.get(
                self.page_url,
                allow_redirects=True,
                schema=validate.Schema(
                    validate.transform(re.compile(r"""<script>window.loadAnvato\((?P<json>{.*})\);</script>""").search),
                    validate.transform(lambda v: v.group(1)),
                    validate.parse_json(),
                    {
                        "video": str,
                        "accessKey": str
                    },
                ),
            )
            self.api_url = f"https://tkx.mp.lura.live/rest/v2/mcp/video/{getResult['video']}?anvack={getResult['accessKey']}"
        print(self.api_url)
        return self.api_url


    def get_hls_url(self):
        postResult = self.session.http.post(
            self.get_api_url()
        )
        resultMatch = re.match(r"^(anvatoVideoJSONLoaded\()?({.*})(\()?", postResult.text)
        if (not resultMatch) or (not resultMatch.group(2)):
            log.error("The response does not have the expected data")
            return

        schema_data = validate.Schema(
            validate.parse_json(),
            {
                "def_title": str,
                "published_urls": [{
                    "embed_url": validate.url(),
                    "format": str,
                }],
            },
        )

        data = schema_data.validate(resultMatch.group(2))
        self.title = data["def_title"]
        for published_url in data["published_urls"]:
            if published_url["format"] == "m3u8-variant":
                return published_url["embed_url"]
                #return AnvatoHLSStream(self.get_api_url()).parse_variant_playlist(self.session, )

        log.error("This page does not have a valid HLS stream")


@pluginmatcher(re.compile(
    r"""https?://(
    pix11.com |
    ktla.com |
    wgntv.com |
    cw33.com |
    kfor.com 
    )(
    /live/ |
    /on-air/live-streaming |
    /on-air/live-video-feed-2 |
    /on-air/live-streaming-sc
    )/
    """, re.VERBOSE
))
class Anvato(Plugin):
    def _get_streams(self):
        self.api = AnvatoApi(self.session, self.url)
        url_hls = self.api.get_hls_url()
        if not url_hls:
            return
        for q, s in HLSStream.parse_variant_playlist(self.session, url_hls).items():
            yield q, AnvatoHLSStream(self.session, s.url, page_url=self.url, q=q, force_restart=True)



__plugin__ = Anvato

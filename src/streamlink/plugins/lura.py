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

from streamlink.plugin import Plugin, pluginmatcher
from streamlink.plugin.plugin import parse_params
from streamlink.stream.hls import HLSStream
from streamlink.plugin.api import validate

log = logging.getLogger(__name__)


@pluginmatcher(re.compile(

))
class Lura(Plugin):

    def _get_streams(self):
        getResult = self.session.http.get(
            self.url,
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

        url = f"https://tkx.mp.lura.live/rest/v2/mcp/video/{getResult['video']}?anvack={getResult['accessKey']}"
        postResult = self.session.http.post(
            url
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
                    "format": "m3u8-variant",
                }],
            },
        )

        data = schema_data.validate(resultMatch.group(2))
        self.title = data["def_title"]
        return HLSStream.parse_variant_playlist(self.session, data["published_urls"][0]["embed_url"])


__plugin__ = Lura

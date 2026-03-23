import scrapy
import re
import json
from pathlib import Path
from biedronka.items import ImageItem

class LeafletSpider(scrapy.Spider):
    name = "gazetka"
    allowed_domains = ["biedronka.pl", "leaflet-api.prod.biedronka.cloud", "images.biedronka.cloud"]
    start_urls = ["https://biedronka.pl/pl/gazetki"]

    def parse(self, response):
        for a in response.css("a.page-slot-columns::attr(href)").getall():
            yield scrapy.Request(
                    url = response.urljoin(a),
                    callback = self.parse_leaflet
            )

# problem z gazetkami 18+

    def parse_leaflet(self, response):
        url = response.request.url
        if  ",id," in url:
            date = 'UNKNOWN'
            if re.search(r'\-[0-9]{2}\-[0-9]{2}', url):
                if "-od-" in url:
                    date = f"OD {re.search(r'[0-9]{2}\-[0-9]{2}', url).group()}"
                else:
                    date = f"{re.search(r'[0-9]{2}\-[0-9]{2}', url).group()}"
            leaflet_id = url.split(",id,")[1].split(",")[0]
            if not Path(f"gazetki/{date} {leaflet_id}").exists():
                uuid = re.search(r'galleryLeaflet\.init\("([^"]+)"\)', response.text).group(1)
                api_url = 'https://leaflet-api.prod.biedronka.cloud/api/leaflets/'+uuid+'?ctx=web'
                yield scrapy.Request(
                    url = api_url,
                    headers = {
                        "Origin": "https://www.biedronka.pl",
                        "Referer": "https://www.biedronka.pl"
                    },
                    callback = self.parse_api,
                    cb_kwargs = {
                        'leaflet_id': leaflet_id,
                        'date': date
                    }
            )


    def parse_api(self, response, leaflet_id, date):
        data = json.loads(response.text)
        for page in data["images_mobile"]:
            yield ImageItem(
                image_urls = [page["image"]],
                leaflet_id = leaflet_id,
                date = date
            )


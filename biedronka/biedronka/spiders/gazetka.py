import scrapy
import re
import json
from pathlib import Path
from biedronka.items import ImageItem

UUID_PATTERNS = [
    r'galleryLeaflet\.init\("([^"]+)"\)',
    r'Leaflet\.init\("([^"]+)"\)',
    r'"leafletId"\s*:\s*"([0-9a-f\-]{36})"',
    r'"uuid"\s*:\s*"([0-9a-f\-]{36})"',
]

FLOWPAPER_DOC_RE = re.compile(r'startDocument\s*=\s*"([^"]+)"')
FLOWPAPER_SUB_RE = re.compile(r'subfolder\s*=\s*"([^"]+)"')

MAX_FLOWPAPER_PAGES = 80

class LeafletSpider(scrapy.Spider):
    name = "gazetka"
    allowed_domains = ["biedronka.pl", "leaflet-api.prod.biedronka.cloud", "images.biedronka.cloud"]
    start_urls = ["https://biedronka.pl/pl/gazetki"]

    AGE_GATE_URL = "https://www.biedronka.pl/front/user/adultconfirmationpress"

    def start_requests(self):
        yield scrapy.Request(
            url=self.AGE_GATE_URL,
            callback=self._submit_age_form,
            dont_filter=True,
        )

    def _submit_age_form(self, response):
        yield scrapy.FormRequest(
            url=self.AGE_GATE_URL,
            formdata={"yes": "Tak"},
            callback=self._age_confirmed,
            dont_filter=True,
        )

    def _age_confirmed(self, response):
        for url in self.start_urls:
            yield scrapy.Request(url=url, callback=self.parse, dont_filter=True)

    def parse(self, response):
        for a in response.css("a.page-slot-columns::attr(href)").getall():
            full_url = response.urljoin(a)
            if "/press," not in full_url and "/pressadult," not in full_url:
                continue
            yield scrapy.Request(
                    url=full_url,
                    callback=self.parse_leaflet
            )

    def parse_leaflet(self, response):
        url = response.request.url
        if ",id," not in url:
            return

        date_label = 'UNKNOWN'
        date_match = re.search(r'-(\d{2}-\d{2})', url)
        if date_match:
            raw_date = date_match.group(1)
            if "-od-" in url:
                date_label = f"OD {raw_date}"
            else:
                date_label = raw_date

        leaflet_id = url.split(",id,")[1].split(",")[0]
        if Path(f"gazetki/{date_label} {leaflet_id}").exists():
            return

        uuid = None
        for pattern in UUID_PATTERNS:
            match = re.search(pattern, response.text)
            if match:
                uuid = match.group(1)
                break

        if uuid:
            api_url = f'https://leaflet-api.prod.biedronka.cloud/api/leaflets/{uuid}?ctx=web'
            yield scrapy.Request(
                url=api_url,
                headers={
                    "Origin": "https://www.biedronka.pl",
                    "Referer": "https://www.biedronka.pl"
                },
                callback=self.parse_api,
                cb_kwargs={
                    'leaflet_id': leaflet_id,
                    'date': date_label
                }
            )
            return

        doc_match = FLOWPAPER_DOC_RE.search(response.text)
        sub_match = FLOWPAPER_SUB_RE.search(response.text)
        if doc_match and sub_match:
            doc = doc_match.group(1)
            subfolder = sub_match.group(1)
            for page in range(1, MAX_FLOWPAPER_PAGES + 1):
                img_url = (
                    f"https://www.biedronka.pl/flexpaper/view"
                    f"?format=jpg&subfolder={subfolder}&page={page}&doc={doc}"
                )
                yield scrapy.Request(
                    url=img_url,
                    callback=self.parse_flowpaper_page,
                    cb_kwargs={
                        'leaflet_id': leaflet_id,
                        'date': date_label,
                        'page': page,
                    },
                    dont_filter=True,
                )
            return

        self.logger.warning(f"Nie znaleziono UUID ani FlowPaper na stronie: {url}")

    def parse_api(self, response, leaflet_id, date):
        data = json.loads(response.text)
        for page in data["images_mobile"]:
            yield ImageItem(
                image_urls=[page["image"]],
                leaflet_id=leaflet_id,
                date=date
            )

    def parse_flowpaper_page(self, response, leaflet_id, date, page):
        if response.status != 200:
            return
        content_type = response.headers.get('Content-Type', b'').decode('utf-8', errors='ignore')
        if 'image' not in content_type:
            return
        yield ImageItem(
            image_urls=[response.url],
            leaflet_id=leaflet_id,
            date=date
        )

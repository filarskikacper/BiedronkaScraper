BOT_NAME = "biedronka"

SPIDER_MODULES = ["biedronka.spiders"]
NEWSPIDER_MODULE = "biedronka.spiders"

ADDONS = {}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

ROBOTSTXT_OBEY = True

CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 1

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
}

ITEM_PIPELINES = {"biedronka.pipelines.LeafletImagesPipeline": 1}
IMAGES_STORE = "./gazetki"

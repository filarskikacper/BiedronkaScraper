import json
from pathlib import Path, PurePosixPath
from scrapy.utils.httpobj import urlparse_cached
from scrapy.pipelines.images import ImagesPipeline


class LeafletImagesPipeline(ImagesPipeline):
    def file_path(self, request, response=None, info=None, *, item=None):
        return f"{item['date']} {item['leaflet_id']}/" + PurePosixPath(urlparse_cached(request).path).name

    def item_completed(self, results, item, info):
        images_store = info.spider.settings.get('IMAGES_STORE', './gazetki')
        folder = Path(images_store) / f"{item['date']} {item['leaflet_id']}"

        urls_file = folder / "_urls.json"
        existing = {}
        if urls_file.exists():
            with open(urls_file, encoding="utf-8") as f:
                existing = json.load(f)

        for success, result in results:
            if success:
                filename = PurePosixPath(result['path']).name
                existing[filename] = result['url']

        folder.mkdir(parents=True, exist_ok=True)
        with open(urls_file, 'w', encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False)

        return item

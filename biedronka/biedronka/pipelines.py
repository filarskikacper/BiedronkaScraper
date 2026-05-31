from pathlib import PurePosixPath
from scrapy.utils.httpobj import urlparse_cached
from scrapy.pipelines.images import ImagesPipeline


class LeafletImagesPipeline(ImagesPipeline):
    def file_path(self, request, response=None, info=None, *, item=None):
        return f"{item['date']} {item['leaflet_id']}/" + PurePosixPath(urlparse_cached(request).path).name

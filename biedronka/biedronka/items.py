import scrapy


class ImageItem(scrapy.Item):
    image_urls = scrapy.Field()
    images = scrapy.Field()
    leaflet_id = scrapy.Field()
    date = scrapy.Field()

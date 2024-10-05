from database import *

def rss_template(config):
    print(config)
    temp = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": config.get('title', ''),
        "home_page_url": config.get('url', ''),
        "feed_url": config.get('url', '') + "/feed.json",
        "description": config.get('description', ''),
        "icon": config.get('icon', ''),
        "favicon": config.get('favicon', ''),
        "authors": [
            {
                "name": config.get('author', ''),
            }
        ],
        "language": "zh-CN",
        "follow_challenge": {}
        "items": []
    }

    if config.get('follow_challenge', None):
        temp['follow_challenge'] = config['follow_challenge']
    return temp

def generate_rss_json(template, config):
    photos_sorted_by_date = (Photo
                            .select()
                            .join(EXIFData, JOIN.LEFT_OUTER, on=(Photo.exif_data == EXIFData.id))
                            .order_by(Case(None, [(EXIFData.date.is_null(), 1)], 0), EXIFData.date.desc()))

    for photo in photos_sorted_by_date:
        exif_date = photo.exif_data.date if photo.exif_data else '0000-00-00 08:59:12'
        url = config['base_url'] + "/" + photo.path
        single = f'{config["url"]}?name={photo.path}'
        tmp = {
            "id": url,
            "url": url,
            "external_url": config['url'],
            "title": photo.name,
            "content_html": photo.desc,
            "image": url,
            "date_published": exif_date,
            "date_modified": exif_date,
        }
        template['items'].append(tmp)
    return template
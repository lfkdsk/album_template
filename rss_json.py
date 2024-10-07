from database import *

def rss_template(config):
    temp = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": f"{config.get('title', '')} Feed",
        "home_page_url": f"{config.get('url', '')}/grid-all",
        "feed_url": f"{config.get('url', '')}/feed.json",
        "description": config.get('description', ''),
        "icon": config.get('icon', ''),
        "favicon": config.get('favicon', ''),
        "authors": [
            {
                "name": config.get('author', ''),
            }
        ],
        "language": "zh-CN",
        "follow_challenge": {},
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
        exif_date = photo.exif_data.date if photo.exif_data else '1970-02-06 08:59:12'
        if not photo.exif_data:
            continue
        url = config['base_url'] + "/" + photo.path
        single = f'{config["url"]}?name={photo.path}'
        tmp = {
            "id": url,
            "url": single,
            "external_url": single,
            "title": photo.name,
            "content_html": f'<div><img src="{url}"/><p>{photo.desc}</p></div>',
            "image": url,
            "date_published": exif_date,
            "date_modified": exif_date,
        }
        template['items'].append(tmp)
    return template
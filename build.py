import yaml
import os
import json
import pathlib
import shutil
import exifread
from natsort import natsorted
from database import *
from tool import *

gen_thumbnail = False
thumbnail_public = "thumbnail_public"
public = "public"
pathlib.Path(f"./{thumbnail_public}/").mkdir(parents=True, exist_ok=True)
pathlib.Path(f"./{public}/").mkdir(parents=True, exist_ok=True)

# init database
if os.path.exists('sqlite.db'):
    os.remove('sqlite.db')

db_path = "./public/sqlite.db"

db.init(db_path)
db.connect()
db.create_tables([Album, Tag, Location, EXIFData, Photo])

# check paths.
if not os.path.exists("./gallery/"):
    raise "need git clone gallery first."

# check config.
if not os.path.exists("./gallery/CONFIG.yml") or not os.path.exists('./gallery/README.yml'):
    raise "CONFIG or README is null."

config = {}
# re-generate config file.
with open("./gallery/CONFIG.yml", 'r', encoding="utf-8") as g, open("./_config.yml", "r+", encoding="utf-8") as c, open("./new_config.yml", "w", encoding="utf-8") as n:
    g_file, c_file = yaml.safe_load(g), yaml.safe_load(c)
    for item in g_file:
        print(item)
        c_file[str(item)] = g_file[item]
        config[str(item)] = g_file[item]
    print(list(c_file))        
    yaml.safe_dump(c_file, n, allow_unicode=True)

thumbnail_url = config["thumbnail_url"]
base_url = config["base_url"]
thumbnail_size = config.get("thumbnail_size", 1000)
if not base_url or not base_url:
    raise "need set base url in github CONFIG.yml ."

with open("./gallery/README.yml", 'r') as f:
    y = yaml.safe_load(f)

if not y:
    raise "could not found README.yml"

# overwrite _config theme.
shutil.copyfile('./gallery/README.yml', './source/_data/album.yml')

index = 0
# anlaysis summary 
all_files = {}
all_locations = {}

for d in y:
    title = d
    print(title)
    element = y[d]
    cover = element['cover']
    url = element['url']
    hidden = element.get('hidden', False)
    date = element.get('date', '')
    subtitle = element.get('subtitle', '')
    location = element.get('location', [])
    layout = element.get('layout', 'album')
    style = element.get('style', 'default')
    index_md = f"./gallery/{url}/index.md"
    gallery_dir = f"./gallery/{url}"
    rss_text = ''
    text = ''

    if os.path.exists(f"./gallery/{url}/index.md"):
        f = open(index_md, 'r')
        for l in f.readlines():
            text += l
    photos = ''
    index_yml_name = f"./gallery/{url}/index.yml"
    if os.path.exists(index_yml_name):
        with open(index_yml_name, 'r', encoding="utf-8") as i:
            index_yml = yaml.safe_load(i)

    sorted_files = natsorted(os.listdir(gallery_dir))
    pathlib.Path(f"./{thumbnail_public}/{url}/").mkdir(parents=True, exist_ok=True)
    cover, _ = os.path.splitext(cover)
    cover = f'{thumbnail_url}/{cover}.webp'

    album_model, _ = Album.get_or_create(dir=url)

    for i in sorted_files:
        name, ext = os.path.splitext(i)
        desc = ' - · - '
        exf = open(f'{gallery_dir}/{i}', 'rb')
        tags = exifread.process_file(exf)
        tag_text = ''
        exif_data = {}
        pure_exif_data = {}
        for tag in tags.keys():
            # print(f"{tag} : {str(tags[tag])}")
            if tag in ['Image Make', 'Image Model', 'EXIF LensModel', 'EXIF FocalLength','EXIF FNumber', 'EXIF ISOSpeedRatings', 'EXIF ExposureTime', 'EXIF DateTimeOriginal']:
              pre = pro = cur = ''
              if tag == 'EXIF FNumber':
                  pre = 'F'
                  cur = str(eval(str(tags[tag])))
              elif tag == 'EXIF ISOSpeedRatings':
                  pre = 'ISO '
                  cur = str(eval(str(tags[tag])))
              elif tag == 'EXIF ExposureTime':
                  pro = 's'
                  cur = str(tags[tag])
              elif tag == 'EXIF DateTimeOriginal':
                  exif_data[tag] = pure_exif_data[tag] = str(tags[tag])
                  continue
              elif tag == 'EXIF FocalLength':
                  cur = str(eval(str(tags[tag])))
                  pro = 'mm'
              elif tag == 'Image Make':
                  cur = str(tags[tag])
              else:
                  cur = str(tags[tag])
              cur_text = pre + cur + pro
              exif_data[tag] = cur_text
              pure_exif_data[tag] = cur
              tag_text += cur_text
              tag_text += ' '
        is_video = False
        exif_model = to_exif_date(pure_exif_data)
        if exif_model:
            exif_model.save()
        if 'index_yml' in locals() and name in index_yml:
            desc = index_yml[name]['desc']
        if ext in ['.md', '.yml',] or name in ['.DS_Store'] or name.startswith('__'):
            print(f"skip {name}{ext}")
            continue
        video = ""
        img_url = f'{base_url}/{url}/{i}'
        img_thumbnail_url = f'{thumbnail_url}/{url}/{name}.webp'
        thumbnail_name =f'./{thumbnail_public}/{url}/{name}.webp'
        # compress image
        if gen_thumbnail or not os.path.exists(thumbnail_name):
            thumbnail_image(f'{gallery_dir}/{i}', output_file=thumbnail_name, max_size=(thumbnail_size, thumbnail_size))
        if ext[1:].lower() in ["mov", "mp4"]:
            is_video = True
            for thum_name, file in [(os.path.splitext(n)[0], n) for n in sorted_files]:
                if thum_name == f'__{name}':
                    video = file
                    print(f'found video {video}')
            if video == "":
                continue # cannot found thumtail.
            video = f'{base_url}/{url}/{video}'
            img_url, video = video, img_url
        
        # get gps location. 
        loc = read_gps(f'./gallery/{url}/{i}')
        result = {
            'path': f'{url}/{i}',
            'dir': url,
            'exif': tag_text,
            'url': img_url,
            'thum': img_thumbnail_url,
            'location': loc,
            'name': name,
            'desc': desc,
            'exif_data': exif_data
        }
        img_key = f'{url}/{i}'
        all_files[img_key] = result
        photo_model = Photo.get_or_none(path=img_key)
        loc_model = to_location(photo_model, loc)
        if not photo_model:
            photo_model = Photo.create(
                path=img_key,
                dir=album_model,
                exif=tag_text,
                name=name,
                desc=desc,
                location=loc_model,
                exif_data=exif_model,
            )
        # copy location only to speed up the location page.
        if loc:
            all_locations[img_key] = all_files[img_key]

        p = f'''
- name: {name} 
  video: {video}
  share: {url}/{i}
  thum: {img_thumbnail_url}
  url: {img_url}
  exif: "{tag_text}"
  desc: "{desc}"
'''
        rss_text += f'- <img src="{img_thumbnail_url}">\n'
        photos += p
    tmp = f'''
---
title: {title}
date: {date}
cover: {cover}
layout: {layout}
permalink: {url}
hidden: {hidden}
url: {url}
style: {style}
location: {location}
subtitle: {subtitle}
rss: 
{rss_text}
photos:
{photos}
---
{text}
'''
    pathlib.Path(f'source/gallery/vol{index}.md').write_text(tmp)
    print(f'generate md file for source/gallery/vol{index}.md')
    index += 1

with open(f"./{public}/photos.json", 'w', encoding="utf-8") as f:
    print(f'generate photos.json with {len(all_files)} items.')
    json.dump(all_files, f, ensure_ascii=False)

with open("./source/_data/photos.yml", "w", encoding="utf-8") as f:
    yaml.safe_dump(all_files, f, allow_unicode=True)

with open("./source/_data/location.yml", "w", encoding="utf-8") as f:
    yaml.safe_dump(all_locations, f, allow_unicode=True)

db.close()

shutil.copyfile('./gallery/README.yml', f'./{thumbnail_public}/README.yml')

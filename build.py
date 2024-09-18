import yaml
import os
import json
import pathlib
import shutil
import exifread
import hashlib
from natsort import natsorted
from database import *
from tool import *

gen_thumbnail = False
thumbnail_public = "thumbnail_public"
public = "public"
gallery = "gallery"
pathlib.Path(f"./{thumbnail_public}/").mkdir(parents=True, exist_ok=True)
pathlib.Path(f"./{public}/").mkdir(parents=True, exist_ok=True)


db_path = "./public/sqlite.db"
# init database
# if os.path.exists(db_path):
#     os.remove(db_path)

db.init(db_path)
db.connect()
db.create_tables([Album, Tag, Location, EXIFData, Photo])

# check paths.
if not os.path.exists(f"./{gallery}/"):
    raise "need git clone gallery first."

# copy custom css
css_file_name = ''
if os.path.exists(f"./{gallery}/style.css"):
    text = open(f'./{gallery}/style.css', 'r').read()
    md5 = hashlib.md5(text.encode()).hexdigest()
    css_file_name = f'custom/style.{md5}.css'
    shutil.copyfile(f'./{gallery}/style.css', f'./source/{css_file_name}')

# check config.
if not os.path.exists(f"./{gallery}/CONFIG.yml") or not os.path.exists(f'./{gallery}/README.yml'):
    raise "CONFIG or README is null."

config = {}
# re-generate config file.
with open(f"./{gallery}/CONFIG.yml", 'r', encoding="utf-8") as gallery_config_file, \
     open("./_config.yml", "r+", encoding="utf-8") as template_config_file, \
     open("./new_config.yml", "w", encoding="utf-8") as new_config_file: 
    gallery_config, template_config = yaml.safe_load(gallery_config_file), yaml.safe_load(template_config_file)
    if css_file_name:
        template_config['custom_css'] = css_file_name
    for item in gallery_config:
        print(item)
        template_config[str(item)] = gallery_config[item]
        config[str(item)] = gallery_config[item]
    print(list(template_config))
    yaml.safe_dump(template_config, new_config_file, allow_unicode=True)

thumbnail_url = config["thumbnail_url"]
base_url = config["base_url"]
thumbnail_size = config.get("thumbnail_size", 1000)
if not base_url or not base_url:
    raise "need set base url in github CONFIG.yml ."

with open(f"./{gallery}/README.yml", 'r') as index_file:
    readme_yaml = yaml.safe_load(index_file)

if not readme_yaml:
    raise "could not found README.yml"

# overwrite _config theme.
shutil.copyfile(f'./{gallery}/README.yml', './source/_data/album.yml')

index = 0
# anlaysis summary
all_files = {}
all_locations = {}

for album_key in readme_yaml:
    title = album_key
    print(title)
    element = readme_yaml[album_key]
    cover = element['cover']
    url = element['url']
    hidden = element.get('hidden', False)
    date = element.get('date', '')
    subtitle = element.get('subtitle', '')
    location = element.get('location', [])
    layout = element.get('layout', 'album')
    style = element.get('style', 'default')
    index_md = f"./{gallery}/{url}/index.md"
    gallery_dir = f"./{gallery}/{url}"
    rss_text = ''
    text = ''

    if os.path.exists(f"./{gallery}/{url}/index.md"):
        index_file = open(index_md, 'r')
        for index_line in index_file.readlines():
            text += index_line
    photos = ''
    index_yml_name = f"./{gallery}/{url}/index.yml"
    if os.path.exists(index_yml_name):
        with open(index_yml_name, 'r', encoding="utf-8") as sorted_file:
            index_yml = yaml.safe_load(sorted_file)

    sorted_files = natsorted(os.listdir(gallery_dir))
    pathlib.Path(f"./{thumbnail_public}/{url}/").mkdir(parents=True, exist_ok=True)
    cover, _ = os.path.splitext(cover)
    cover = f'{thumbnail_url}/{cover}.webp'

    album_model, _ = Album.get_or_create(dir=url)

    for sorted_file in sorted_files:
        name, ext = os.path.splitext(sorted_file)
        if ext in ['.md', '.yml',] or name in ['.DS_Store'] or name.startswith('__'):
            print(f"skip {name}{ext}")
            continue
        desc = ' - · - '
        exf = open(f'{gallery_dir}/{sorted_file}', 'rb')
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
                  cur = str(round(eval(str(tags[tag])), 1))
              elif tag == 'EXIF ISOSpeedRatings':
                  pre = 'ISO '
                  cur = str(eval(str(tags[tag])))
              elif tag == 'EXIF ExposureTime':
                  pro = 's'
                  cur = str(tags[tag])
                  resu = cur.split('/')
                  # calc for iPhone with expo time like:
                  if len(resu) == 2 and resu[0] != '1':
                    a, b = eval(resu[0]), eval(resu[1])
                    cur = f'{a/b}' if a > b else f'1/{int(b/a)}'
              elif tag == 'EXIF DateTimeOriginal':
                  exif_data[tag] = pure_exif_data[tag] = str(tags[tag])
                  continue
              elif tag == 'EXIF FocalLength':
                  cur = str(round(eval(str(tags[tag])), 1))
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
        video = ""
        img_url = f'{base_url}/{url}/{sorted_file}'
        img_thumbnail_url = f'{thumbnail_url}/{url}/{name}.webp'
        thumbnail_name =f'./{thumbnail_public}/{url}/{name}.webp'
        # compress image
        if gen_thumbnail or not os.path.exists(thumbnail_name):
            thumbnail_image(f'{gallery_dir}/{sorted_file}', output_file=thumbnail_name, max_size=(thumbnail_size, thumbnail_size))
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
        loc = read_gps(f'./{gallery}/{url}/{sorted_file}')
        result = {
            'path': f'{url}/{sorted_file}',
            'dir': url,
            'exif': tag_text,
            'url': img_url,
            'thum': img_thumbnail_url,
            'location': loc,
            'name': name,
            'desc': desc,
            'exif_data': exif_data
        }
        img_key = f'{url}/{sorted_file}'
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
        else:
            photo_model.dir = album_model
            photo_model.exif = tag_text
            photo_model.name = name
            photo_model.desc = desc
            photo_model.location = loc_model
            photo_model.exif_data = exif_model
            photo_model.save()
        # copy location only to speed up the location page.
        if loc:
            all_locations[img_key] = all_files[img_key]

        p = f'''
- name: {name}
  video: {video}
  share: {url}/{sorted_file}
  thum: {img_thumbnail_url}
  url: {img_url}
  exif: "{tag_text}"
  desc: "{desc}"
'''
        rss_text += f'- <img src="{img_url}">\n'
        photos += p

    dir_linked_photos = Photo.select().where(Photo.dir == album_model)
    for item in dir_linked_photos:
        if os.path.exists(f'./{gallery}/{item.path}'):
           continue
        print(f'delete {item.path} row instance.')
        item.delete_instance() 

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

with open(f"./{public}/photos.json", 'w', encoding="utf-8") as index_file:
    print(f'generate photos.json with {len(all_files)} items.')
    json.dump(all_files, index_file, ensure_ascii=False)

with open("./source/_data/photos.yml", "w", encoding="utf-8") as index_file:
    yaml.safe_dump(all_files, index_file, allow_unicode=True)

with open("./source/_data/location.yml", "w", encoding="utf-8") as index_file:
    yaml.safe_dump(all_locations, index_file, allow_unicode=True)

db.close()

shutil.copyfile(f'./{gallery}/README.yml', f'./{thumbnail_public}/README.yml')

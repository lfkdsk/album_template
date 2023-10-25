import yaml
import os
import exifread
import pathlib
import shutil
from PIL import Image, ImageOps
from natsort import natsorted

gen_thumbnail = False

def thumbnail_image(input_file, output_file, max_size=(1000, 1000), resample=3, ext='webp'):
    im = Image.open(input_file)
    im.thumbnail(max_size, resample=resample)
    im = ImageOps.exif_transpose(im)
    im.save(output_file, format=ext, optimize=True)

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
thumbnail_public = "thumbnail_public"
if not base_url or not base_url:
    raise "need set base url in github CONFIG.yml ."

with open("./gallery/README.yml", 'r') as f:
    y = yaml.safe_load(f)

if not y:
    raise "could not found README.yml"

# overwrite _config theme.
shutil.copyfile('./gallery/README.yml', './source/_data/album.yml')

pathlib.Path(f"./{thumbnail_public}/").mkdir(parents=True, exist_ok=True)

index = 0

for d in y:
    title = d
    print(title)
    element = y[d]
    cover = element['cover']
    url = element['url']
    date = element.get('date', '')
    subtitle = element.get('subtitle', '')
    location = element.get('location', [])
    style = element.get('style', 'default')
    index_md = f"./gallery/{url}/index.md"
    gallery_dir = f"./gallery/{url}"
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

    for i in sorted_files:
        name, ext = os.path.splitext(i)
        desc = ' - · - '
        exf = open(f'{gallery_dir}/{i}', 'rb')
        tags = exifread.process_file(exf)
        tag_text = ''
        for tag in tags.keys():
            if tag in ['Image Make', 'Image Model', 'EXIF LensModel','EXIF FNumber', 'EXIF ISOSpeedRatings', 'EXIF ShutterSpeedValue',]:
              pre = ''
              if tag == 'EXIF FNumber':
                  pre = 'F'
              elif tag == 'EXIF ISOSpeedRatings':
                  pre = 'ISO'
              elif tag == 'EXIF ShutterSpeedValue':
                  pre = 'SS'
              tag_text += pre + str(tags[tag]) + ' '
        is_video = False
        if 'index_yml' in locals() and name in index_yml:
            desc = index_yml[name]['desc']
        if ext == '.md' or ext == '.yml' or name.startswith('__'):
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
        if desc == ' - · - ' and tag_text != '':
            desc = tag_text
        p = f'''
- name: {name} 
  video: {video}
  share: {url}/{i}
  thum: {img_thumbnail_url}
  url: {img_url}
  exif: "{tag_text}"
  desc: "{desc}"
'''
        photos += p
    tmp = f'''
---
title: {title}
date: {date}
cover: {cover}
layout: album
permalink: {url}
url: {url}
style: {style}
location: {location}
subtitle: {subtitle}
photos:
{photos}
---
{text}
'''
    pathlib.Path(f'source/gallery/vol{index}.md').write_text(tmp)
    print(f'generate md file for source/gallery/vol{index}.md')
    index += 1

input = "./gallery/"

# barrowed from 
# https://gist.github.com/snakeye/fdc372dbf11370fe29eb 
def _convert_to_degress(value):
    """
    Helper function to convert the GPS coordinates stored in the EXIF to degress in float format
    :param value:
    :type value: exifread.utils.Ratio
    :rtype: float
    """
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)

    return d + (m / 60.0) + (s / 3600.0)

def read_gps(file_name: str):
    if not os.path.exists(file_name):
        return (-1, -1)
    
    with open(file_name, 'rb') as f:
        exif_dict = exifread.process_file(f)
        latitude = exif_dict.get('GPS GPSLatitude')
        latitude_ref = exif_dict.get('GPS GPSLatitudeRef')
        longitude = exif_dict.get('GPS GPSLongitude')
        longitude_ref = exif_dict.get('GPS GPSLongitudeRef')
        if latitude:
            lat_value = _convert_to_degress(latitude)
            if latitude_ref.values != 'N':
                lat_value = -lat_value
        else:
            return (-1, -1)
        if longitude:
            lon_value = _convert_to_degress(longitude)
            if longitude_ref.values != 'E':
                lon_value = -lon_value
        else:
            return (-1, -1)
        return (lat_value, lon_value)

def anlayze_location():
    with open("./source/_data/gallery.yml", "w", encoding="utf-8") as f:
        single = {}
        for (dirpath, dirnames, filenames) in os.walk(input):
            for dir in dirnames:
                files = os.listdir(os.path.join(dirpath, dir))
                for file in files:
                    name, ext = os.path.splitext(file)
                    if ext.lower() not in [".jpg", ".jpeg", ".webp"]:
                        continue
                    a, b = read_gps(os.path.join(dirpath, dir, file))
                    if a == -1 and b == -1:
                        continue;
                    print(f'name {file} GPS: {a}, {b}')
                    nK = os.path.join(dir, file)
                    single[nK] = {
                        "url": nK,
                        "location": [a, b],
                        "dir": dir,
                        "name": name,
                    }
        yaml.safe_dump(single, f, allow_unicode=True)

anlayze_location()
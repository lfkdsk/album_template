import yaml
import os
import pathlib
import shutil
from PIL import Image, ImageOps
from natsort import natsorted

gen_thumbnail = True

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

# re-generate config file.
with open("./gallery/CONFIG.yml", 'r', encoding="utf-8") as g, open("./_config.yml", "r+", encoding="utf-8") as c, open("./new_config.yml", "w", encoding="utf-8") as n:
    g_file, c_file = yaml.safe_load(g), yaml.safe_load(c)
    for item in g_file:
        print(item)
        c_file[str(item)] = g_file[item]
    print(list(c_file))        
    yaml.safe_dump(c_file, n, allow_unicode=True)

thumbnail_url = os.getenv("THUMBNAIL_URL")
base_url = os.getenv("BASE_URL")
thumbnail_size = os.getenv("THUMBNAIL_SIZE") if os.getenv("THUMBNAIL_SIZE") is not None else 1000
thumbnail_public = "thumbnail_public"
if not base_url or not base_url:
    raise "need set base url in github action."

with open("./gallery/README.yml", 'r') as f:
    y = yaml.safe_load(f)

if not y:
    raise "could not found README.yml"

# overwrite _config theme.
# shutil.copyfile('./_config.type.yml', './themes/hexo-theme-type/_config.yml')
shutil.copyfile('./gallery/README.yml', './source/_data/album.yml')

pathlib.Path(f"./{thumbnail_public}/").mkdir(parents=True, exist_ok=True)

index = 0

for d in y:
    title = d
    print(title)
    element = y[d]
    cover = element['cover']
    url = element['url']
    date = element['date']
    subtitle = element.get('subtitle', '')
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
        p = f'''
- name: {name} 
  video: {video}
  thum: {img_thumbnail_url}
  url: {img_url}
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
style: {style}
subtitle: {subtitle}
photos:
{photos}
---
{text}
'''
    pathlib.Path(f'source/gallery/vol{index}.md').write_text(tmp)
    print(f'generate md file for source/gallery/vol{index}.md')
    index += 1
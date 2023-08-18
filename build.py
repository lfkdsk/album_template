import yaml
import os
import pathlib
import shutil

base_url = os.getenv("BASE_URL")
if not base_url:
    raise "need set base url in github action."

if not os.path.exists("./gallery/"):
    raise "need git clone gallery first."

with open("./gallery/README.md", 'r') as f:
    y = yaml.safe_load(f)

if not y:
    raise "could not found README.md"

shutil.copyfile('./gallery/README.md', './source/_data/album.yml')
index = 0
for d in y:
    title = d
    print(title)
    element = y[d]
    cover = element['cover']
    url = element['url']
    date = element['date']
    index_md = f"./gallery/{url}/index.md"
    gallery_dir = f"./gallery/{url}"
    text = ''
    if os.path.exists(f"./gallery/{url}/index.md"):
        f = open(index_md, 'r')
        for l in f.readlines():
            text += l
    photos = ''
    for i in os.listdir(gallery_dir):
        name, ext = os.path.splitext(i)
        if ext == '.md':
            continue
        p = f'- {base_url}/{url}/{i}\n'
        photos += p
    tmp = f'''
---
title: {title}
date: {date}
cover: {cover}
layout: album
permalink: {url}
photos:
{photos}
---
{text}
'''
    pathlib.Path(f'source/gallery/vol{index}.md').write_text(tmp)
    print(f'generate md file for source/gallery/vol{index}.md')
    index += 1
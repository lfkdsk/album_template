import yaml
import os
import pathlib
import shutil

if not os.path.exists("./gallery/"):
    raise "need git clone gallery first."

if not os.path.exists("./gallery/CONFIG.yml") or not os.path.exists('./gallery/README.yml'):
    raise "CONFIG or README is null."

with open("./gallery/CONFIG.yml", 'r', encoding="utf-8") as g, open("./_config.yml", "r+", encoding="utf-8") as c, open("./new_config.yml", "w", encoding="utf-8") as n:
    g_file, c_file = yaml.safe_load(g), yaml.safe_load(c)
    for item in g_file:
        print(item)
        c_file[str(item)] = g_file[item]
    print(list(c_file))        
    yaml.safe_dump(c_file, n, allow_unicode=True)

base_url = os.getenv("BASE_URL")
if not base_url:
    raise "need set base url in github action."

with open("./gallery/README.yml", 'r') as f:
    y = yaml.safe_load(f)

if not y:
    raise "could not found README.yml"

# overwrite _config theme.
# shutil.copyfile('./_config.type.yml', './themes/hexo-theme-type/_config.yml')
shutil.copyfile('./gallery/README.yml', './source/_data/album.yml')
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
    index_yml_name = f"./gallery/{url}/index.yml"
    if os.path.exists(index_yml_name):
        with open(index_yml_name, 'r', encoding="utf-8") as i:
            index_yml = yaml.safe_load(i)
    for i in os.listdir(gallery_dir):
        name, ext = os.path.splitext(i)
        desc = ' - · - '
        if 'index_yml' in locals() and name in index_yml:
            desc = index_yml[name]['desc']
        if ext == '.md' or ext == '.yml':
            continue
        p = f'''
- name: {name} 
  url: {base_url}/{url}/{i}
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
photos:
{photos}
---
{text}
'''
    pathlib.Path(f'source/gallery/vol{index}.md').write_text(tmp)
    print(f'generate md file for source/gallery/vol{index}.md')
    index += 1
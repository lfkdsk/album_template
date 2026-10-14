import yaml
import os
import json
import pathlib
import shutil
import hashlib
import subprocess
import re
from datetime import datetime, timedelta
from natsort import natsorted
from database import *
from rss_json import *
from tool import *
import gallery_cache

# True: 无视缓存，重新生成全部缩略图（需要下载全部原图）。
gen_thumbnail = False
thumbnail_public = "thumbnail_public"
public = "public"
gallery = "gallery"
pathlib.Path(f"./{thumbnail_public}/").mkdir(parents=True, exist_ok=True)
pathlib.Path(f"./{public}/").mkdir(parents=True, exist_ok=True)


db_path = "./public/sqlite.db"
# init database
if os.path.exists(db_path):
    os.remove(db_path)

db.init(db_path)
db.connect()
db.create_tables([Album, Tag, Location, EXIFData, Photo])

# check paths.
if not os.path.exists(f"./{gallery}/"):
    raise SystemExit("need git clone gallery first.")

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

# 手写页面必须自带 date:。缺了的话 hexo 会退回文件 mtime——而 git 不保存 mtime，
# CI 每次 checkout 都把它重置成当下，于是 content.json / archives / rss 里的日期
# 每天都变，即使相册内容一个字没动，也会在 gh-pages 上堆出一串纯时间戳的空提交。
# 这类问题不报错就只能靠某天翻 commit 历史才发现，所以让它在构建时立刻失败：
# 站点会停在上一次的好状态，而修复只是补一行 front-matter。
# source/gallery/vol*.md 不在检查范围内——那些是本脚本自己生成的，日期在下面
# 由 URL 派生（见 hash_int 那段），本来就是确定的。
_dateless = []
for _root, _dirs, _files in os.walk('./source'):
    if 'gallery' in _root.split(os.sep) and _root.endswith('gallery'):
        _files = [f for f in _files if not f.startswith('vol')]
    for _f in _files:
        # .html 也要查：source/search/index.html 就带 front-matter，一样会
        # 因为缺 date 而退回 mtime（第一版检查只扫 .md，正好漏了它）。
        if not _f.endswith(('.md', '.html')):
            continue
        _p = os.path.join(_root, _f)
        with open(_p, 'r', encoding='utf-8') as _fh:
            if not re.search(r'^date:', _fh.read(), re.M):
                _dateless.append(_p)
if _dateless:
    raise SystemExit(
        '以下页面缺少 date: front-matter，会让 hexo 退回文件 mtime，'
        '导致每日构建产生无意义的空提交：\n  '
        + '\n  '.join(sorted(_dateless))
        + '\n\n补一行即可，例如 date: 2026-01-01 12:00:00'
    )

config = {}
default_album_layout = None
# re-generate config file.
with open(f"./{gallery}/CONFIG.yml", 'r', encoding="utf-8") as gallery_config_file, \
     open("./_config.yml", "r+", encoding="utf-8") as template_config_file, \
     open("./new_config.yml", "w", encoding="utf-8") as new_config_file:
    gallery_config, template_config = yaml.safe_load(gallery_config_file), yaml.safe_load(template_config_file)
    if css_file_name:
        template_config['custom_css'] = css_file_name
    default_album_layout = gallery_config.get('album_layout') or gallery_config.get('default_album_layout')
    for item in gallery_config:
        print(item)
        template_config[str(item)] = gallery_config[item]
        config[str(item)] = gallery_config[item]
    print(list(template_config))
    # sort_keys=False to preserve nav (and other) ordering from CONFIG.yml
    yaml.safe_dump(template_config, new_config_file, allow_unicode=True, sort_keys=False)

thumbnail_url = config["thumbnail_url"]
base_url = config["base_url"]
# Pin base_url to the gallery's exact commit instead of a moving @branch ref.
# jsDelivr caches the @branch->commit resolution for ~12h, so after updating a
# file (e.g. fixing a Live Photo's clap atom) the @master URL keeps serving the
# old bytes for up to 12h and per-file purges don't help -- they re-fetch at the
# still-stale ref. A commit-pinned URL is immutable, so every deploy that
# changes the gallery automatically gets fresh, never-stale media URLs.
try:
    gallery_sha = subprocess.check_output(
        ["git", "-C", f"./{gallery}", "rev-parse", "HEAD"],
        stderr=subprocess.DEVNULL,
    ).decode().strip()
    pinned_base_url = re.sub(
        r"(https?://cdn\.jsdelivr\.net/gh/[^/@]+/[^/@]+)@[^/]+",
        rf"\g<1>@{gallery_sha}",
        base_url,
    )
    if pinned_base_url != base_url:
        dirty = subprocess.run(
            ["git", "-C", f"./{gallery}", "status", "--porcelain"],
            capture_output=True, text=True,
        ).stdout.strip()
        if dirty:
            print(f"WARNING: ./{gallery} has uncommitted changes -- pinned URLs "
                  f"use HEAD ({gallery_sha[:10]}), not the working tree; commit & "
                  f"push the gallery before deploying or jsDelivr will 404 / lag.")
        print(f"pin base_url -> {pinned_base_url}")
        base_url = pinned_base_url
    else:
        print(f"base_url is not a jsDelivr @ref URL; leaving as-is: {base_url}")
except Exception as e:
    print(f"could not pin base_url to a commit ({e}); using {base_url}")
thumbnail_size = config.get("thumbnail_size", 1000)
if not base_url or not base_url:
    raise "need set base url in github CONFIG.yml ."

with open(f"./{gallery}/README.yml", 'r') as index_file:
    readme_yaml = yaml.safe_load(index_file)

if not readme_yaml:
    raise "could not found README.yml"

# overwrite _config theme.
shutil.copyfile(f'./{gallery}/README.yml', './source/_data/album.yml')

# 照片元数据和缩略图走 thumbnail 分支上的 manifest.json 缓存，只处理新增 / 变化的照片，
# 见 gallery_cache.py。之后的循环只读缓存和 yml，不再碰原图。
gallery_tree, photo_meta = gallery_cache.sync(
    f"./{gallery}", f"./{thumbnail_public}",
    [readme_yaml[k]['url'] for k in readme_yaml],
    thumbnail_size, force_thumbnail=gen_thumbnail,
)

index = 0
# anlaysis summary
all_files = {}
all_locations = {}

with db.atomic():
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
        layout = element.get('layout', default_album_layout or 'album')
        style = element.get('style', 'default')
        index_md = f"./{gallery}/{url}/index.md"
        gallery_dir = f"./{gallery}/{url}"
        rss_text = ''
        text = ''

        # Albums without an explicit date in README.yml would get the file mtime
        # (= CI build time) as their hexo post date, causing every generated file
        # that renders a post date to change on every daily cron build. Derive a
        # stable, deterministic date from the album URL instead.
        if not date:
            hash_int = int(hashlib.sha256(url.encode()).hexdigest(), 16)
            date = (datetime(2020, 1, 1) + timedelta(days=hash_int % 1461)).strftime('%Y-%m-%d')

        if os.path.exists(f"./{gallery}/{url}/index.md"):
            index_file = open(index_md, 'r')
            for index_line in index_file.readlines():
                text += index_line
        photos = ''
        index_yml_name = f"./{gallery}/{url}/index.yml"
        if os.path.exists(index_yml_name):
            with open(index_yml_name, 'r', encoding="utf-8") as sorted_file:
                index_yml = yaml.safe_load(sorted_file)

        # 文件列表来自 git tree（CI 里工作区没有原图），排序用缓存里的拍摄时间。
        if url not in gallery_tree:
            raise FileNotFoundError(f'album dir not found in gallery HEAD: {gallery_dir}')
        album_shas = dict(gallery_tree[url])
        sorted_files = sort_photos(gallery_tree[url], photo_meta)
        # Map lower-cased name -> real filename so Live Photo .mov/.MOV lookups are
        # case-insensitive while the generated URL keeps the real on-disk case
        # (iPhone exports .MOV; GitHub Pages on Linux is case-sensitive).
        mov_files = {f.lower(): f for f in sorted_files if os.path.splitext(f)[1].lower() == '.mov'}
        pathlib.Path(f"./{thumbnail_public}/{url}/").mkdir(parents=True, exist_ok=True)
        cover, _ = os.path.splitext(cover)
        cover_url = f'{base_url}/{cover}.webp'
        cover = f'{thumbnail_url}/{cover}.webp'
        rss_text += f'- <img src="{cover_url}"/>\n'

        album_model, _ = Album.get_or_create(dir=url)

        for sorted_file in sorted_files:
            name, ext = os.path.splitext(sorted_file)
            if not gallery_cache.is_photo(sorted_file):
                print(f"skip {name}{ext}")
                continue
            desc = ' - · - '
            meta = photo_meta[album_shas[sorted_file]]
            if 'error' in meta:
                print("EXIF parse failed:", meta['error'], f'{gallery_dir}/{sorted_file}')
                continue
            # 每张照片都要新的 dict / list：同一个对象出现两次，yaml 会输出成 &id001 引用。
            tag_text = meta['exif']
            exif_data = dict(meta['exif_data'])
            pure_exif_data = dict(meta['pure_exif_data'])
            is_video = False
            exif_model = to_exif_date(pure_exif_data)
            if exif_model:
                exif_model.save()
            else:
                exif_data = {}
                tag_text = ''
                pure_exif_data = {}
            if 'index_yml' in locals() and name in index_yml:
                desc = index_yml[name]['desc']
            video_url = ""
            livephoto = False
            img_url = f'{base_url}/{url}/{sorted_file}'
            img_thumbnail_url = f'{thumbnail_url}/{url}/{name}.webp'

            livevideo = mov_files.get(f'{name}.mov'.lower())
            if livevideo:
                video_url = f'{base_url}/{url}/{livevideo}'
                livephoto = True
            # get gps location.
            loc = list(meta['gps'])
            img_key = f'{url}/{sorted_file}'
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
            all_files[img_key] = result
            loc_model = to_location(loc, meta['country'])
            Photo.create(
                path=img_key,
                dir=album_model,
                exif=tag_text,
                name=name,
                desc=desc,
                location=loc_model,
                livephoto=livephoto,
                exif_data=exif_model,
            )
            # copy location only to speed up the location page.
            if loc:
                result = {
                    'path': f'{url}/{sorted_file}',
                    'dir': url,
                    'url': img_url,
                    'thum': img_thumbnail_url,
                    'location': loc,
                    'name': name,
                }
                all_locations[img_key] = result

            p = f'''
- name: {name}
  video: {video_url}
  share: {url}/{sorted_file}
  thum: {img_thumbnail_url}
  url: {img_url}
  exif: "{tag_text}"
'''
            if img_url != cover_url:
                rss_text += f'- <img src="{img_url}"/>\n'
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

# useless now.
# with open(f"./{public}/photos.json", 'w', encoding="utf-8") as index_file:
#     print(f'generate photos.json with {len(all_files)} items.')
#     json.dump(all_files, index_file, ensure_ascii=False)

class CustomJSONEncoder(json.JSONEncoder):
    def encode(self, o):
        result = super().encode(o)
        result = result.replace(r'\u003c', '<')
        result = result.replace(r'\u003e', '>')
        result = result.replace(r'\u0026', '&')
        return result

with open(f"./{public}/feed.json", 'w', encoding="utf-8") as json_feed:
    template = rss_template(config)
    result = generate_rss_json(template, config)
    json.dump(result, json_feed, cls=CustomJSONEncoder, ensure_ascii=False)

with open("./source/_data/photos.yml", "w", encoding="utf-8") as index_file:
    yaml.safe_dump(all_files, index_file, allow_unicode=True)

with open("./source/_data/location.yml", "w", encoding="utf-8") as index_file:
    yaml.safe_dump(all_locations, index_file, allow_unicode=True)

# Animal analysis data — joins gallery/.analysis/animal_index.json with all_files.
animal_index_path = f"./{gallery}/.analysis/animal_index.json"
animals_data = []
if os.path.exists(animal_index_path):
    with open(animal_index_path, 'r', encoding='utf-8') as f:
        animal_index = json.load(f)

    def lookup_photo(path):
        if path in all_files:
            return all_files[path]
        base, _ = os.path.splitext(path)
        for alt in ('.webp', '.jpg', '.jpeg', '.JPG', '.JPEG', '.png', '.PNG'):
            cand = base + alt
            if cand in all_files:
                return all_files[cand]
        return None

    for species_key, paths in animal_index.items():
        if species_key.startswith('_'):
            continue
        zh, _, en = species_key.partition(' / ')
        photos = []
        located = 0
        for p in paths:
            meta = lookup_photo(p)
            if not meta:
                print(f"[animals] skip missing photo: {p}")
                continue
            entry = {
                'path': meta['path'],
                'dir': meta['dir'],
                'name': meta['name'],
                'url': meta['url'],
                'thum': meta['thum'],
                'location': meta.get('location') or [],
                'desc': meta.get('desc', ''),
                'exif': meta.get('exif', ''),
            }
            if entry['location']:
                located += 1
            photos.append(entry)
        if not photos:
            continue
        animals_data.append({
            'key': species_key,
            'zh': zh.strip() or species_key,
            'en': en.strip(),
            'count': len(photos),
            'located': located,
            'cover': photos[0]['thum'],
            'photos': photos,
        })
    animals_data.sort(key=lambda a: (-a['count'], a['zh']))

with open("./source/_data/animals.yml", "w", encoding="utf-8") as index_file:
    yaml.safe_dump(animals_data, index_file, allow_unicode=True)

# Annual summary — copy gallery/.analysis/annual-summary/<year>.json into public/.
# Theme's summary.ejs reads these to override the RANDOM monthly photo pick.
annual_summary_src = f"./{gallery}/.analysis/annual-summary"
annual_summary_dst = f"./{public}/annual-summary"
if os.path.exists(annual_summary_src):
    pathlib.Path(annual_summary_dst).mkdir(parents=True, exist_ok=True)
    for fname in os.listdir(annual_summary_src):
        if not fname.endswith(".json"):
            continue
        shutil.copyfile(
            os.path.join(annual_summary_src, fname),
            os.path.join(annual_summary_dst, fname),
        )
        print(f"[annual-summary] copy {fname}")

# db.execute_sql("PRAGMA journal_mode=OFF;")
# db.execute_sql("PRAGMA synchronous=OFF;")
# db.execute_sql("PRAGMA page_size=1024;")
db.close()

shutil.copyfile(f'./{gallery}/README.yml', f'./{thumbnail_public}/README.yml')

if os.path.exists(f'./{gallery}/CNAME'):
    shutil.copyfile(f'./{gallery}/CNAME', f'./{public}/CNAME')

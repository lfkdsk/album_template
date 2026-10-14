"""增量构建：照片元数据和缩略图按 git blob SHA 缓存。

CI 里 gallery 是 partial clone（filter=blob:none）+ sparse checkout，工作区里只有
yml / md 这些小文件，原图一张都没有。这里做三件事：

1. 用 `git ls-tree` 拿到 "路径 -> blob SHA"，代替 os.listdir；
2. 读 thumbnail 分支里的 manifest.json，SHA 命中的照片直接用缓存的元数据；
3. 没命中的照片（或缩略图需要重做的）一次性 fetch 下来，用 `git cat-file --batch`
   按 SHA 读进内存：每张只读一次，取出全部元数据并生成缩略图。

原图按 SHA 从对象库读，而不是 checkout 到工作区：不会覆盖本地 gallery 里未提交的
改动，缓存里的元数据也一定对应这个 SHA 的内容。gallery 是完整 clone 时（本地开发、
旧版 workflow）对象都在本地，跳过 fetch，其余流程完全一样。

manifest 只是可丢弃的缓存：丢了、坏了、版本不对，都按冷缓存全量重算一次，结果不变。
它只增不删——删掉的照片，其记录和缩略图都留着，下次同内容再出现时还能直接命中。
"""
import io
import json
import os
import shutil
import subprocess
from collections import defaultdict

import exifread

from tool import get_country, get_exif_datetime, parse_exif_tags, read_gps, thumbnail_image

# 改了下面 analyze_photo 的解析逻辑（或国家边界数据），就把版本 +1，强制全量重算。
MANIFEST_VERSION = 1
MANIFEST_NAME = 'manifest.json'


def is_photo(filename):
    name, ext = os.path.splitext(filename)
    return not (ext.lower() in ['.md', '.yml', '.mov'] or name in ['.DS_Store', '.gitkeep'] or name.startswith('__'))


def thumbnail_rel(url, filename):
    name, _ = os.path.splitext(filename)
    return f'{url}/{name}.webp'


def _git(repo, *args, **kwargs):
    return subprocess.run(['git', '-C', repo, *args], check=True, **kwargs)


def list_tree(repo):
    """{目录: [(文件名, blob sha), ...]}，只含 HEAD 里的文件。"""
    out = _git(repo, 'ls-tree', '-r', '-z', 'HEAD', capture_output=True).stdout
    dirs = defaultdict(list)
    for entry in out.split(b'\0'):
        if not entry:
            continue
        meta, path = entry.split(b'\t', 1)
        _, obj_type, sha = meta.decode().split(' ')
        if obj_type != 'blob':
            continue
        dirname, filename = os.path.split(path.decode('utf-8'))
        dirs[dirname].append((filename, sha))
    return dirs


def prefetch(repo, shas):
    """partial clone 里缺的 blob 一次请求拉下来（git 自己懒加载时用的也是这条命令）。

    不预取的话 cat-file 会一个对象一个请求地懒加载，冷缓存时要几千次往返。
    """
    out = _git(repo, 'rev-list', '--objects', '--missing=print', 'HEAD', capture_output=True, text=True).stdout
    missing = {line[1:] for line in out.splitlines() if line.startswith('?')}
    wanted = sorted(set(shas) & missing)
    if not wanted:
        return 0
    remotes = subprocess.run(['git', '-C', repo, 'config', '--get-regexp', r'^remote\..*\.promisor$'],
                             capture_output=True, text=True).stdout.split()  # 没有匹配时返回码是 1
    remote = remotes[0][len('remote.'):-len('.promisor')] if remotes else 'origin'
    print(f'[cache] fetching {len(wanted)} blobs from {remote}')
    _git(repo, '-c', 'fetch.negotiationAlgorithm=noop', 'fetch', '-q', remote,
         '--no-tags', '--no-write-fetch-head', '--recurse-submodules=no', '--filter=blob:none', '--stdin',
         input='\n'.join(wanted) + '\n', text=True)
    return len(wanted)


class BlobReader:
    def __init__(self, repo):
        self.proc = subprocess.Popen(['git', '-C', repo, 'cat-file', '--batch'],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, sha):
        self.proc.stdin.write(sha.encode() + b'\n')
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().split()
        if len(header) != 3:
            raise RuntimeError(f'git cat-file: {b" ".join(header).decode()}')
        data = self.proc.stdout.read(int(header[2]))
        self.proc.stdout.read(1)  # 结尾的换行
        return data

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()


def analyze_photo(data):
    """一张原图的全部元数据。结果只取决于文件内容，所以可以按 SHA 缓存。"""
    try:
        tags = exifread.process_file(io.BytesIO(data))
    except Exception as e:
        # 和旧版一样：exifread 解析失败的文件（比如 HEIC）整张跳过。
        return {'error': str(e)}
    tag_text, exif_data, pure_exif_data = parse_exif_tags(tags)
    gps = read_gps(tags)
    dt = get_exif_datetime(io.BytesIO(data))
    return {
        'exif': tag_text,
        'exif_data': exif_data,
        'pure_exif_data': pure_exif_data,
        'gps': gps,
        'country': get_country(gps[1], gps[0]) if gps else '',
        'datetime': dt.strftime('%Y:%m:%d %H:%M:%S') if dt else None,
    }


def load_manifest(path):
    empty = {'version': MANIFEST_VERSION, 'photos': {}, 'thumb_owner': {}}
    if not os.path.exists(path):
        print(f'[cache] no {path}, cold build')
        return empty
    try:
        with open(path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception as e:
        print(f'[cache] unreadable {path} ({e}), cold build')
        return empty
    if manifest.get('version') != MANIFEST_VERSION:
        print(f'[cache] manifest version {manifest.get("version")} != {MANIFEST_VERSION}, cold build')
        return empty
    return manifest


def save_manifest(path, manifest):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        # 一行一条记录，thumbnail 分支上每次提交的 diff 只有新增的几行。
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')
    os.replace(tmp, path)


def sync(gallery, thumbnail_dir, album_urls, thumbnail_size, force_thumbnail=False):
    """补齐缓存和缩略图，返回 (tree, photos)：tree 见 list_tree，photos 是 {sha: 元数据}。"""
    tree = list_tree(gallery)
    manifest_path = os.path.join(thumbnail_dir, MANIFEST_NAME)
    manifest = load_manifest(manifest_path)
    photos = manifest['photos']
    thumb_owner = manifest['thumb_owner']

    def thumb_file(rel):
        return os.path.join(thumbnail_dir, rel)

    # sha -> 已有的缩略图，用于重命名 / 同一张图出现在多个相册时直接复制。
    thumbs_by_sha = defaultdict(list)
    for rel, sha in thumb_owner.items():
        thumbs_by_sha[sha].append(rel)

    stats = defaultdict(int)
    candidates = [(url, filename, sha) for url in album_urls
                  for filename, sha in tree.get(url, []) if is_photo(filename)]

    def stale(rel, sha):
        # 同名替换、删掉后再传同名新图：SHA 对不上就重做。没有来源记录的缩略图见下面的"沿用"。
        if force_thumbnail:
            return True
        if rel in thumb_owner:
            return thumb_owner[rel] != sha or not os.path.exists(thumb_file(rel))
        return not os.path.exists(thumb_file(rel))

    def copy_source(rel, sha):
        return next((r for r in thumbs_by_sha.get(sha, [])
                     if r != rel and thumb_owner.get(r) == sha and os.path.exists(thumb_file(r))), None)

    # 要下载的原图：缓存没命中的，加上缩略图要重做、又没有同 SHA 缩略图可复制的。
    # 一次 fetch 拉完，后面两步都只读本地对象库。
    wanted = []
    for url, filename, sha in candidates:
        entry = photos.get(sha)
        rel = thumbnail_rel(url, filename)
        if entry is None or ('error' not in entry and stale(rel, sha) and (force_thumbnail or not copy_source(rel, sha))):
            wanted.append(sha)
    stats['fetched'] = prefetch(gallery, wanted) if wanted else 0
    reader = BlobReader(gallery) if wanted else None

    # 1. 元数据。先全部补齐，第 2 步才知道哪些文件解析失败、不该占用缩略图。
    for url, filename, sha in candidates:
        if sha not in photos:
            photos[sha] = analyze_photo(reader.read(sha))
            stats['analyzed'] += 1

    # 2. 缩略图
    claimed = set()
    for url, filename, sha in candidates:
        if 'error' in photos[sha]:
            continue
        rel = thumbnail_rel(url, filename)
        if rel in claimed:
            # 同一相册里 a.jpg / a.webp 会撞到同一个缩略图，按 tree 顺序先到先得，
            # 保证每次构建结论一致、不会来回重做。
            continue
        claimed.add(rel)
        if not stale(rel, sha):
            if rel not in thumb_owner:
                # 冷缓存（第一次迁移 / manifest 丢失）时 thumbnail 分支上已有的缩略图
                # 没有来源记录：和旧版一样直接沿用，只补记来源。全部重做要 ~1s/张，
                # 而且换了 Pillow 版本后字节不同，会把整个 thumbnail 分支重写一遍。
                thumb_owner[rel] = sha
                thumbs_by_sha[sha].append(rel)
                stats['adopted'] += 1
            continue
        os.makedirs(os.path.dirname(thumb_file(rel)), exist_ok=True)
        src = None if force_thumbnail else copy_source(rel, sha)
        if src:
            # 重命名 / 同一张图出现在多个相册
            print(f'[cache] copy thumbnail {src} -> {rel}')
            shutil.copyfile(thumb_file(src), thumb_file(rel))
            stats['copied'] += 1
        else:
            print(f'[cache] thumbnail {url}/{filename}')
            thumbnail_image(io.BytesIO(reader.read(sha)), output_file=thumb_file(rel),
                            max_size=(thumbnail_size, thumbnail_size))
            stats['thumbnails'] += 1
        thumb_owner[rel] = sha
        thumbs_by_sha[sha].append(rel)
    if reader:
        reader.close()

    save_manifest(manifest_path, manifest)
    print('[cache] ' + ', '.join(f'{k}={stats[k]}' for k in ('analyzed', 'fetched', 'thumbnails', 'copied', 'adopted'))
          + f', cached={len(photos)}')
    return tree, photos

#!/usr/bin/env python3
"""增量构建的闭环测试。

用合成照片建一个本地 gallery 仓库，按 CI 的方式（partial clone + sparse checkout，
缩略图目录在多次构建之间延续，相当于 thumbnail 分支）一步步改动 gallery 并构建，
每一步都和"从零构建"（完整 clone、空缩略图目录）对比：

- vol*.md / photos.yml / location.yml / animals.yml / feed.json / sqlite.db 等产物完全一致；
- 当前照片的缩略图字节一致（增量那边允许多出已删除照片的旧缩略图）；
- manifest 里的元数据和从零算出来的一致；
- 每一步实际下载 / 解析 / 生成了多少张，和预期一致（防止悄悄退化成全量）；
- partial clone 的工作区里始终没有原图，也没有被改动。

覆盖：新项目第一次构建（没有 thumbnail 分支）、热缓存、新增、同名替换、删除后再传
同名新图、重命名 / 移动相册、manifest 丢失、manifest 版本变化、旧版 workflow（完整 clone）。

传 --legacy-ref <commit> 时，每一步再用该 commit 的 build.py（改造前的旧版）从零构建，
产物也必须一致。

    python tests/closed_loop.py --legacy-ref 752c505
"""
import argparse
import filecmp
import io
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile

from PIL import Image
from PIL.TiffImagePlugin import IFDRational as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_FILES = ['build.py', 'tool.py', 'database.py', 'rss_json.py', 'gallery_cache.py', '_config.yml',
              'ne_110m_admin_0_countries.shp', 'ne_110m_admin_0_countries.dbf', 'ne_110m_admin_0_countries.shx']
# 和 gallery 仓库 .github/workflows/main.yml 里的 sparse-checkout 保持一致。
SPARSE = ['/*.yml', '/*.css', '/CNAME', '/.analysis/', '/**/index.yml', '/**/index.md']
OUTPUTS = ['source/_data/photos.yml', 'source/_data/location.yml', 'source/_data/animals.yml',
           'source/_data/album.yml', 'public/feed.json', 'public/CNAME', 'new_config.yml',
           'thumbnail_public/README.yml']
GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME='test', GIT_AUTHOR_EMAIL='test@example.com',
               GIT_COMMITTER_NAME='test', GIT_COMMITTER_EMAIL='test@example.com',
               GIT_CONFIG_NOSYSTEM='1')


def sh(*cmd, cwd=None, **kw):
    return subprocess.run(cmd, cwd=cwd, check=True, env=GIT_ENV, capture_output=True, text=True, **kw).stdout


# ---------------------------------------------------------------- 合成 gallery

def photo_bytes(seed, fmt='JPEG', exif=True, gps=None, date='2023:06:05 12:31:40', size=(900, 600)):
    rnd = random.Random(seed)
    im = Image.new('RGB', size, tuple(rnd.randrange(256) for _ in range(3)))
    # 加点色块，保证不同 seed 的缩略图不同，也让 webp 压缩有事可做。
    for _ in range(12):
        x, y = rnd.randrange(size[0]), rnd.randrange(size[1])
        im.paste(tuple(rnd.randrange(256) for _ in range(3)), (x, y, x + 120, y + 80))
    kw = {}
    if exif:
        e = Image.Exif()
        e[0x010F] = 'FUJIFILM'
        if exif != 'make-only':
            e[0x0110] = 'X-T5'
        e[0x8769] = {0x9003: date, 0x829A: R(1, 250), 0x829D: R(28, 10), 0x8827: 400,
                     0x920A: R(230, 10), 0xA434: 'XF23mmF1.4 R'}
        if gps:
            (lat, lat_ref), (lon, lon_ref) = gps
            e[0x8825] = {1: lat_ref, 2: (R(lat, 1), R(30, 1), R(15, 1)), 3: lon_ref, 4: (R(lon, 1), R(25, 1), R(10, 1))}
        kw['exif'] = e
    buf = io.BytesIO()
    im.save(buf, fmt, **kw)
    return buf.getvalue()


def fake_heic(n):
    # exifread 解析会抛异常（真实的 HEIC 也一样），旧版和新版都整张跳过。
    return b'\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic' + bytes([n]) * 64

CONFIG_YML = '''title: Closed Loop
url: https://example.com
thumbnail_url: https://cdn.jsdelivr.net/gh/someone/gallery@thumbnail
base_url: https://cdn.jsdelivr.net/gh/someone/gallery@master
thumbnail_size: 400
'''
README_YML = '''Album A:
  url: album-a
  date: "2024-01-02"
  cover: album-a/a1.jpg
  location: [37.77, -122.41]
Album B:
  url: album-b
  date: "2024-02-03"
  style: fullscreen
  cover: album-b/b1.jpg
Album C:
  url: album-c
  cover: album-c/c1.jpg
'''


class Gallery:
    def __init__(self, base):
        self.origin = os.path.join(base, 'origin.git')
        self.src = os.path.join(base, 'gallery-src')
        sh('git', 'init', '-q', '--bare', '-b', 'master', self.origin)
        # GitHub 默认允许 partial clone 和按 SHA 取对象；本地裸仓库要手动打开。
        sh('git', '-C', self.origin, 'config', 'uploadpack.allowFilter', 'true')
        sh('git', '-C', self.origin, 'config', 'uploadpack.allowAnySHA1InWant', 'true')
        sh('git', 'clone', '-q', self.origin, self.src)
        sh('git', '-C', self.src, 'checkout', '-q', '-b', 'master')

    def write(self, path, data):
        p = os.path.join(self.src, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(data if isinstance(data, bytes) else data.encode())

    def remove(self, path):
        sh('git', '-C', self.src, 'rm', '-q', path)

    def move(self, a, b):
        os.makedirs(os.path.dirname(os.path.join(self.src, b)), exist_ok=True)
        sh('git', '-C', self.src, 'mv', a, b)

    def commit(self, msg):
        sh('git', '-C', self.src, 'add', '-A')
        sh('git', '-C', self.src, 'commit', '-q', '--allow-empty', '-m', msg)
        sh('git', '-C', self.src, 'push', '-q', 'origin', 'master')

    def full_clone(self, dst):
        sh('git', 'clone', '-q', '--depth', '1', f'file://{self.origin}', dst)
        return dst

    def partial_clone(self, dst):
        # 和 actions/checkout 的 filter: blob:none + sparse-checkout（非 cone）一样的步骤。
        sh('git', 'init', '-q', dst)
        sh('git', '-C', dst, 'remote', 'add', 'origin', f'file://{self.origin}')
        sh('git', '-C', dst, 'sparse-checkout', 'set', '--no-cone', *SPARSE)
        sh('git', '-C', dst, '-c', 'protocol.version=2', 'fetch', '-q', '--no-tags', '--filter=blob:none',
           '--depth=1', 'origin', '+master:refs/remotes/origin/master')
        sh('git', '-C', dst, 'checkout', '-q', '-B', 'master', 'refs/remotes/origin/master')
        return dst


def seed_gallery(g):
    g.write('CONFIG.yml', CONFIG_YML)
    g.write('README.yml', README_YML)
    g.write('CNAME', 'example.com\n')
    g.write('.analysis/animal_index.json', json.dumps({
        '猫 / Cat': ['album-a/a1.jpg', 'album-b/b2.jpg', 'album-a/missing.jpg'],
        '鹿 / Deer': ['album-c/c1.webp'],
    }, ensure_ascii=False))
    g.write('.analysis/annual-summary/2023.json', '{"months": []}')
    g.write('album-a/a1.jpg', photo_bytes(1, gps=((37, 'N'), (122, 'W'))))
    g.write('album-a/a2.jpg', photo_bytes(2, date='2021:01:01 08:00:00'))
    g.write('album-a/a3.png', photo_bytes(3, 'PNG', exif=False))
    g.write('album-a/a4.webp', photo_bytes(4, 'WEBP', gps=((35, 'N'), (139, 'E'))))
    g.write('album-a/A4.MOV', os.urandom(256))          # Live Photo，大小写和照片不一致
    g.write('album-a/a5.HEIC', fake_heic(5))
    # 同名的 HEIC + jpg 映射到同一个缩略图 a7.webp；HEIC 解析失败，缩略图必须归 jpg。
    g.write('album-a/a7.HEIC', fake_heic(7))
    g.write('album-a/a7.jpg', photo_bytes(11))
    g.write('album-a/.gitkeep', '')
    g.write('album-b/index.md', '这是 Album B 的说明。\n')
    g.write('album-b/index.yml', 'b1:\n  desc: 和 a1 是同一张图\nc1:\n  desc: 旧版 index_yml 会串到下一个相册\n')
    g.write('album-b/b1.jpg', photo_bytes(1, gps=((37, 'N'), (122, 'W'))))  # 内容和 a1 相同（同一个 SHA）
    g.write('album-b/b2.jpg', photo_bytes(5, exif='make-only'))
    g.write('album-c/c1.webp', photo_bytes(6, 'WEBP', exif=False))
    g.commit('init')


# 每一步：(说明, 改动 gallery 的函数, 增量构建预期的 [cache] 统计, 构建前对缓存做的手脚)
def steps():
    def noop(g):
        pass

    def add(g):
        g.write('album-a/a6.jpg', photo_bytes(7, gps=((48, 'N'), (2, 'E'))))
        g.write('album-c/c2.jpg', photo_bytes(8))

    def replace(g):
        g.write('album-a/a1.jpg', photo_bytes(9, gps=((40, 'N'), (74, 'W'))))

    def delete(g):
        g.remove('album-c/c2.jpg')

    def readd(g):
        g.write('album-c/c2.jpg', photo_bytes(10, date='2020:05:05 05:05:05'))

    def rename(g):
        g.move('album-a/a2.jpg', 'album-a/a2-renamed.jpg')
        g.move('album-b/b2.jpg', 'album-c/b2.jpg')

    def lose_manifest(thumb):
        os.remove(os.path.join(thumb, 'manifest.json'))

    def bump_version(thumb):
        p = os.path.join(thumb, 'manifest.json')
        m = json.load(open(p))
        m['version'] = -1
        json.dump(m, open(p, 'w'))

    z = dict(analyzed=0, fetched=0, thumbnails=0, copied=0, adopted=0)
    return [
        # a1/b1 同内容：只解析一次，b1 的缩略图直接复制 a1 的；a5、a7 的 HEIC 解析失败、没有缩略图。
        ('新项目第一次构建（还没有 thumbnail 分支）', noop, dict(z, analyzed=9, fetched=9, thumbnails=7, copied=1), None),
        ('热缓存，gallery 没有变化', noop, z, None),
        ('新增两张', add, dict(z, analyzed=2, fetched=2, thumbnails=2), None),
        ('同名替换（旧版会继续用旧缩略图）', replace, dict(z, analyzed=1, fetched=1, thumbnails=1), None),
        ('删除一张', delete, z, None),
        ('删掉后再传同名新图', readd, dict(z, analyzed=1, fetched=1, thumbnails=1), None),
        ('重命名 + 换相册：元数据命中，缩略图直接复制', rename, dict(z, copied=2), None),
        # 此时 12 个文件（a1 已替换，不再和 b1 同 SHA），其中两个 HEIC 解析失败没有缩略图。
        ('manifest 丢失：全量重算，已有缩略图沿用', noop, dict(z, analyzed=12, fetched=12, adopted=10), lose_manifest),
        ('manifest 版本变化：同上', noop, dict(z, analyzed=12, fetched=12, adopted=10), bump_version),
        ('旧版 workflow（完整 clone）', noop, z, 'full-clone'),
    ]


# ---------------------------------------------------------------- 构建与对比

def code_dir_from_worktree(dst):
    os.makedirs(dst)
    for f in CODE_FILES:
        shutil.copy(os.path.join(ROOT, f), dst)
    shutil.copytree(os.path.join(ROOT, 'source'), os.path.join(dst, 'source'))
    clean_generated(dst)
    return dst


def code_dir_from_ref(ref, dst):
    os.makedirs(dst)
    data = subprocess.run(['git', '-C', ROOT, 'archive', ref], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dst)
    return dst


def clean_generated(d):
    for sub in ('source/gallery', 'source/_data', 'source/custom'):
        p = os.path.join(d, sub)
        if not os.path.isdir(p):
            continue
        for f in os.listdir(p):
            if (sub == 'source/gallery' and f.startswith('vol')) or f in (
                    'photos.yml', 'location.yml', 'animals.yml', 'album.yml', 'gallery.yml') or f.startswith('style.'):
                os.remove(os.path.join(p, f))


def build(code, gallery_clone, thumb_state, work):
    """在 work 里跑一次 build.py。thumb_state 是上一次的缩略图目录（None 表示还没有）。"""
    shutil.copytree(code, work)
    os.symlink(gallery_clone, os.path.join(work, 'gallery'))
    if thumb_state:
        shutil.copytree(thumb_state, os.path.join(work, 'thumbnail_public'))
    r = subprocess.run([sys.executable, 'build.py'], cwd=work, capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f'build failed in {work}\n{r.stdout}\n{r.stderr}')
    return r.stdout


def cache_stats(log):
    m = re.search(r'\[cache\] analyzed=(\d+), fetched=(\d+), thumbnails=(\d+), copied=(\d+), adopted=(\d+)', log)
    if not m:
        raise AssertionError('no [cache] stats line in build log')
    return dict(zip(('analyzed', 'fetched', 'thumbnails', 'copied', 'adopted'), map(int, m.groups())))


def output_files(d):
    files = list(OUTPUTS)
    files += sorted('source/gallery/' + f for f in os.listdir(os.path.join(d, 'source/gallery')) if f.startswith('vol'))
    summary = os.path.join(d, 'public/annual-summary')
    if os.path.isdir(summary):
        files += sorted('public/annual-summary/' + f for f in os.listdir(summary))
    return files


def compare_outputs(a, b):
    errors = []
    fa, fb = output_files(a), output_files(b)
    if fa != fb:
        errors.append(f'output file lists differ: {sorted(set(fa) ^ set(fb))}')
    for f in fa:
        pa, pb = os.path.join(a, f), os.path.join(b, f)
        if os.path.exists(pa) != os.path.exists(pb) or (os.path.exists(pa) and not filecmp.cmp(pa, pb, shallow=False)):
            errors.append(f'{f} differs')
    dump_a = list(sqlite3.connect(os.path.join(a, 'public/sqlite.db')).iterdump())
    dump_b = list(sqlite3.connect(os.path.join(b, 'public/sqlite.db')).iterdump())
    if dump_a != dump_b:
        errors.append('sqlite.db differs')
    return errors


def thumbnails(d):
    out = {}
    root = os.path.join(d, 'thumbnail_public')
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith('.webp'):
                p = os.path.join(dirpath, f)
                out[os.path.relpath(p, root)] = open(p, 'rb').read()
    return out


def compare_thumbnails(expected_dir, actual_dir, exact=False):
    exp, act = thumbnails(expected_dir), thumbnails(actual_dir)
    errors = [f'thumbnail {k} missing' for k in exp if k not in act]
    errors += [f'thumbnail {k} differs' for k in exp if k in act and act[k] != exp[k]]
    if exact and set(act) != set(exp):
        errors.append(f'thumbnail sets differ: {sorted(set(act) ^ set(exp))}')
    return errors


def check_partial_clone(clone):
    errors = []
    files = sh('git', '-C', clone, 'ls-files', '-t').splitlines()
    checked_out = [l[2:] for l in files if not l.startswith('S ')]
    photos = [p for p in checked_out if not re.search(r'(\.yml|\.md|\.json|CNAME)$', p)]
    if photos:
        errors.append(f'partial clone has photos checked out: {photos}')
    if sh('git', '-C', clone, 'status', '--porcelain').strip():
        errors.append('partial clone working tree modified')
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--legacy-ref', help='同时和这个 commit 的旧版 build.py 对比')
    ap.add_argument('--keep', action='store_true', help='保留临时目录')
    args = ap.parse_args()

    base = tempfile.mkdtemp(prefix='closed-loop-')
    print(f'workdir: {base}')
    code = code_dir_from_worktree(os.path.join(base, 'code'))
    legacy = code_dir_from_ref(args.legacy_ref, os.path.join(base, 'legacy')) if args.legacy_ref else None
    g = Gallery(base)
    seed_gallery(g)

    thumb_state = None  # 相当于 thumbnail 分支
    failures = 0
    for i, (title, mutate, expected, tweak) in enumerate(steps()):
        mutate(g)
        g.commit(title)
        step = os.path.join(base, f'step{i}')
        if callable(tweak):
            tweak(thumb_state)

        scratch = os.path.join(step, 'scratch')
        build(code, g.full_clone(os.path.join(step, 'g-full')), None, scratch)

        if tweak == 'full-clone':
            clone = g.full_clone(os.path.join(step, 'g-inc'))
        else:
            clone = g.partial_clone(os.path.join(step, 'g-inc'))
        inc = os.path.join(step, 'incremental')
        stats = cache_stats(build(code, clone, thumb_state, inc))
        thumb_state = os.path.join(inc, 'thumbnail_public')

        errors = [f'incremental: {e}' for e in compare_outputs(scratch, inc)]
        errors += [f'incremental: {e}' for e in compare_thumbnails(scratch, inc)]
        if stats != expected:
            errors.append(f'cache stats {stats} != expected {expected}')
        if tweak != 'full-clone':
            errors += check_partial_clone(clone)
        m_scratch = json.load(open(os.path.join(scratch, 'thumbnail_public/manifest.json')))['photos']
        m_inc = json.load(open(os.path.join(inc, 'thumbnail_public/manifest.json')))['photos']
        errors += [f'manifest entry {k} differs' for k in m_scratch if m_inc.get(k) != m_scratch[k]]
        if legacy:
            old = os.path.join(step, 'legacy')
            build(legacy, g.full_clone(os.path.join(step, 'g-legacy')), None, old)
            errors += [f'legacy: {e}' for e in compare_outputs(old, scratch)]
            errors += [f'legacy: {e}' for e in compare_thumbnails(old, scratch, exact=True)]

        print(f'[{"FAIL" if errors else " OK "}] {i}. {title}  {stats}')
        for e in errors:
            print(f'       {e}')
        failures += bool(errors)

    if not args.keep and not failures:
        shutil.rmtree(base)
    print(f'{failures} step(s) failed' if failures else 'all steps passed')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()

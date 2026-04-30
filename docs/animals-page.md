# 动物图鉴页 / Animals Page

新增的 `/animals` 页面把 `gallery/analysis/animal_index.json` 里离线分析得到的动物索引可视化出来：左侧是按物种分组的卡片，右侧（地图区）会把所有带 GPS 坐标的照片按物种着色打点；点进单个物种后地图只显示该物种的足迹，下方是该物种的全部照片网格，点击照片直接跳到对应相册。视觉风格参考 `https://animap.elsetech.app/u/joway`。

## 数据流

```
gallery/analysis/animal_index.json   ← 离线 agent 标注（见 animal_index_guide.md）
        │
        │  build.py: 用 path 关联 all_files / photos.yml
        ▼
source/_data/animals.yml             ← 列表，按 count desc 排序
        │
        ▼
themes/hexo-theme-type/layout/animals.ejs   ← 渲染（Leaflet + 卡片网格）
        │
        ▼
public/animals/index.html            ← Hexo generate 输出
```

`source/_data/animals.yml` 中每个物种的 schema：

```yaml
- key: "中华田园猫·三花 / Chinese Domestic Cat (Calico / Tricolor)"
  zh: 中华田园猫·三花
  en: Chinese Domestic Cat (Calico / Tricolor)
  count: 41          # 实际能在 photos.yml 里找到的照片数
  located: 15        # 其中带 GPS 坐标的张数
  cover: <thumb url> # 取 photos[0].thum
  photos:
    - path: KeZhouQiuCat/DSCF3196.webp
      dir: KeZhouQiuCat
      name: DSCF3196
      url:  <full url>
      thum: <thumb url>
      location: [lat, lon]   # 没有坐标时为 []
      desc: ...
      exif: ...
```

`build.py` 的关联在 `# Animal analysis data` 段，找不到原文件名时按 `.webp/.jpg/.jpeg/.png` 等候选扩展名重试一次；最终都找不到就在控制台打印 `[animals] skip missing photo: ...` 并跳过。

## 启动 / 调试

完整流程（仓库根目录执行）：

```bash
# 一次性准备：拉子模块、装依赖
git submodule update --init --recursive
npm install

# 1. Python 端：扫描 gallery，生成 source/_data/* 和 source/gallery/vol*.md
conda activate py38   # 项目自带的 py38 环境；没有就用任何能装 requirements.txt 的 venv
python build.py

# 2. Hexo 端：生成站点 + 起本地服务
hexo g -f --config ./new_config.yml && hexo s --config ./new_config.yml
```

启动后访问 `http://localhost:4000/animals` 验证；URL `?species=<key>` 可直接深链到某个物种详情。

> 每次改 `gallery/analysis/animal_index.json` 后需要重新跑一次 `python build.py`，否则 `source/_data/animals.yml` 不会刷新。

## 在导航里露出入口

入口在主仓库的 gallery `CONFIG.yml` 里加一行（也可以放主题的 `_config.type.yml`，但 gallery 配置优先级更高）：

```yaml
nav:
  动物:
    link: /animals
    icon: pet  # 见 https://iconpark.oceanengine.com/home 任选合适图标
```

## 涉及的改动文件

| 文件 | 作用 |
|------|------|
| `build.py` | 在写完 `photos.yml` 之后，新增 `source/_data/animals.yml` 输出 |
| `themes/hexo-theme-type/layout/animals.ejs` | 新增：动物图鉴页（卡片 + 地图） |
| `themes/hexo-theme-type/layout/_partial/head.ejs` | 在 `page.layout=='location'` 之外，也对 `=='animals'` 注入 Leaflet |
| `source/animals.md` | 新增：`/animals` 路由的 front matter 入口 |

> 主题改动落在 `themes/hexo-theme-type/` 子模块，提交时记得分别在主题仓库和主仓库各自 commit & push。

## 后续可选优化

- `gallery/analysis/animal_index_guide.md` 里还有一批未扫描文件夹（`Walden-Pond/`、`Fuji/`、`SF-Asian-Museum/` 等），扫描完后无需改主题代码，只要重新 `python build.py` 即可纳入页面。
- 现在物种排序是 `count desc, zh asc`。如果想按分类（哺乳/鸟/爬行等）分组，可以在 `build.py` 里增加 `category` 字段并在 `animals.ejs` 里加分组渲染。
- 详情页地图当前 `fitBounds(maxZoom: 12)`；同一只猫多张近距离照片可能让地图缩到很近，需要时可以在 layout 里调 `maxZoom`。

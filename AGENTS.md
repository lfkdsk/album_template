# 项目结构
该项目为一个相册生成器的项目，album_template 下的 build.py 控制整体生成, CI 会自动 clone github gallery repo 到 gallery 目录，然后 theems 里面是 hexo 的主题，也是我魔改的。

build.py 会根据 readme.yml 图片生成 db，也会同时生成出每个相册的 .md 来驱动 hexo 生成出对应的相册页面，一些其他的动态功能我通过 db 拉到前端进行使用，这里使用了前端的 wasm sqlite 进行数据库操作，可以在静态部署的情况下在前端操作数据。

部署：部署在 github page 的静态界面。

# 配置该改哪里

站点配置有两份，build.py 把它们合成 `new_config.yml`（hexo 实际读的就是这份，不要手改，它是产物）：

```
album_template/_config.yml   基础站点配置
      +  gallery/CONFIG.yml   内容仓库的覆盖（顶层 key 逐个覆盖）
      =  new_config.yml
```

主题配置只有 `themes/hexo-theme-type/_config.yml` **一份**。注意 hexo 找站点级主题配置时认的是 `_config.<theme 值>.yml`（这里就是 `_config.hexo-theme-type.yml`）或以该名开头的文件——历史上仓库里有个 `_config.type.yml`，因为主题目录从上游的 `type` 改名成了 `hexo-theme-type`，那个文件从此再没被加载过，已删除。

gallery 仓库要覆盖主题配置，用 hexo 原生的 `theme_config:`（优先级最高，deep-merge）：

```yaml
# gallery/CONFIG.yml
theme_config:
  skin: classic
  color:
    main_color: '#71AFDD'
```

不需要再像早期那样把选项一个个从模板里的 `theme.x` 改成 `config.x`（`nav` / `footer_logo` / `google_analytics` 等就是这么迁的，保持现状即可，新增的别再走这条路）。

只想微调几个值、不想动主题：在 gallery 仓库放一个 `style.css`，build.py 会按 md5 命名拷进站点并通过 `config.custom_css` 注入，加载顺序在所有主题样式之后：

```css
:root { --radius-lg: 20px; --surface-2: #efece6; }
```

# 主题外观

视觉语言集中在 `themes/hexo-theme-type/source/css/tokens.scss`——圆角、间距、阴影、动效、表面色都是 CSS 变量。`:root` 是默认皮肤 `modern`，其它皮肤是 `[data-skin='…']` 下的一组值覆盖；值表达不了的形状差异放 `source/css/skins/<name>.scss`。

皮肤由 `_config.yml` 的 `skin:` 决定，写到 `<html data-skin>`。所有皮肤都编进产物，所以调设计时可以直接在控制台切换、不用重新构建：

```js
document.documentElement.dataset.skin = 'classic'
```

**主题在 CI 里不走 submodule**：`gallery/.github/workflows/main.yml` 的 `THEME_BRANCH` 决定线上跑哪个分支。改主题时确认这个值，否则本地看到的和线上跑的不是一套代码。

# 构建指令

```
conda activate py38
python build.py
```

`gallery` 必须是 git clone：照片列表取自 `git ls-tree HEAD`，未提交的照片不会出现在产物里。

# 增量构建

CI 里 gallery 是 partial clone（`filter: blob:none`）+ sparse checkout，只检出 yml / md / `.analysis/`，原图一张都不下载。照片元数据和缩略图按 git blob SHA 缓存在 thumbnail 分支的 `manifest.json`，每次只下载、解析新增或变化的照片（`gallery_cache.py`）：

- 缩略图记录来源 SHA（`thumb_owner`），同名替换、删掉后再传同名新图都会重新生成；重命名直接复制旧缩略图。
- 只增不删：删掉的照片，其缩略图和 manifest 记录都留着。
- manifest 只是缓存，丢了 / 版本不对就全量重算一次（结果不变，已有缩略图沿用）。改了 `analyze_photo` 的解析逻辑要把 `MANIFEST_VERSION` +1；不要往 manifest 里写手工数据。
- gallery 是完整 clone 时（本地开发、旧版 workflow）跳过下载，其余流程一样。sqlite.db 仍然每次全量重建，数据来自 manifest + yml。

改动构建逻辑后跑闭环测试（CI 也会跑）：用合成照片模拟新项目首次构建、热缓存、新增、替换、删除、重命名、manifest 丢失等，每一步都要和从零构建、旧版 build.py 的产物完全一致。

```
python tests/closed_loop.py --legacy-ref 752c505
```

# 部署指令

```
hexo g -f --config ./new_config.yml && hexo s --config ./new_config.yml
```
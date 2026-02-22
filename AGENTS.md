# 项目结构
该项目为一个相册生成器的项目，album_template 下的 build.py 控制整体生成, CI 会自动 clone github gallery repo 到 gallery 目录，然后 theems 里面是 hexo 的主题，也是我魔改的。

build.py 会根据 readme.yml 图片生成 db，也会同时生成出每个相册的 .md 来驱动 hexo 生成出对应的相册页面，一些其他的动态功能我通过 db 拉到前端进行使用，这里使用了前端的 wasm sqlite 进行数据库操作，可以在静态部署的情况下在前端操作数据。

部署：部署在 github page 的静态界面。

# 构建指令

```
conda activate py38
python build.py
```

# 部署指令

```
hexo g -f --config ./new_config.yml && hexo s --config ./new_config.yml
```
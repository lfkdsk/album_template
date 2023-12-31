---
title: 快速开始
date: 2022-04-19
permalink: /type/getstart/
---

## 快速开始

要使用 Type，必须首先安装 Hexo。你可以访问 Hexo 的文档来了解如何安装 Hexo 
> [hexo.io/zh-cn/](https://hexo.io/zh-cn/)。

Hexo 中有两份配置文件，分别为站点目录下的 `_config.yml` 和 主题目录下的 `_config.yml`，后文将前者称为「站点配置文件」，后者称之为「主题配置文件」。

本主题支持 npm 和 git 两种安装方式，你也可以下载 release 版本手动安装。

### 使用 npm 安装主题

进入 Hexo 根目录，依次执行以下命令。

```bash
npm install hexo-theme-type --save
npm install
cp -v ./node_modules/hexo-theme-type/_config_test.yml ./_config.type.yml
```

随后，修改 Hexo 根目录的「站点配置文件」

```yaml
theme: type
```

「主题配置文件」即为站点目录下的 `_config.type.yml` 文件。

随后，根据 [配置主题](/type/theme-settings/) 的指引，编辑主题配置文件。
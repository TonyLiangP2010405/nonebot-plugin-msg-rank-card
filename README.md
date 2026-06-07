<div align="center">
  <a href="https://v2.nonebot.dev/store"><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/nbp_logo.png" width="180" height="180" alt="NoneBotPluginLogo"></a>
  <br>
  <p><img src="https://github.com/A-kirami/nonebot-plugin-template/blob/resources/NoneBotPlugin.svg" width="240" alt="NoneBotPluginText"></p>
</div>

<div align="center">

# nonebot-plugin-msg-rank-card

_✨ 每日水群排行榜图片生成插件 ✨_

<a href="./LICENSE">
    <img src="https://img.shields.io/github/license/BigCherryBalls/nonebot-plugin-msg-rank-card.svg" alt="license">
</a>
<a href="https://pypi.python.org/pypi/nonebot-plugin-msg-rank-card">
    <img src="https://img.shields.io/pypi/v/nonebot-plugin-msg-rank-card.svg" alt="pypi">
</a>
<img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="python">

</div>

## 📖 介绍

本插件基于 [MsgRankCard](https://github.com/BigCherryBalls/MsgRankCard) 项目改写，是一个 NoneBot2 插件，用于记录群聊消息并生成精美的每日水群排行榜图片。

功能特点：
- 📝 自动记录群聊消息数量和在线时长
- 🎨 生成精美的排行榜图片，支持自定义背景、边框和字体
- 🖼️ 自动获取用户 QQ 头像
- 🏆 支持查看今日水群排行榜
- 🧹 支持自动清理过期数据

## 💿 安装

### 使用 nb-cli 安装

在 nonebot2 项目的根目录下打开命令行，输入以下指令即可安装

```bash
nb plugin install nonebot-plugin-msg-rank-card
```

### 使用包管理器安装

在 nonebot2 项目的插件目录下，打开命令行，根据你使用的包管理器，输入相应的安装命令

<details>
<summary>pip</summary>

```bash
pip install nonebot-plugin-msg-rank-card
```
</details>

<details>
<summary>poetry</summary>

```bash
poetry add nonebot-plugin-msg-rank-card
```
</details>

打开 nonebot2 项目根目录下的 `pyproject.toml` 文件，在 `[tool.nonebot]` 部分追加写入

```toml
plugins = ["nonebot_plugin_msg_rank_card"]
```

## ⚙️ 配置

在 nonebot2 项目的 `.env` 文件中添加下表中的配置

| 配置项 | 必填 | 默认值 | 说明 |
|:-----:|:----:|:----:|:----:|
| msg_rank_data_path | 否 | data/msg_rank | 数据存储路径 |
| msg_rank_resource_path | 否 | 插件目录/resources | 资源文件路径（背景图、边框、字体） |
| msg_rank_max_count | 否 | 10 | 排行榜最大显示人数 |
| msg_rank_auto_clean | 否 | true | 是否自动清理过期数据 |
| msg_rank_title | 否 | 今日水群排行榜 | 排行榜标题 |

## 🎉 使用

### 指令表

| 指令 | 权限 | 需要@ | 范围 | 说明 |
|:-----:|:----:|:----:|:----:|:----:|
| 水群榜 / msgrank | 群员 | 否 | 群聊 | 查看今日水群排行榜 |
| 清理水群数据 / clean_msgrank | 群主/管理员 | 否 | 群聊 | 清理过期数据 |

### 效果图

插件会自动记录群聊消息，发送 `/水群榜` 即可生成精美排行榜图片。

### 自定义资源

你可以替换插件目录下 `resources` 文件夹中的资源文件：
- `bg/` - 背景图片（随机选择）
- `frame/` - 排名边框装饰
- `ttf/` - 自定义字体（第一个 ttf 文件会被使用）

## 📄 许可证

本项目基于 [MsgRankCard](https://github.com/BigCherryBalls/MsgRankCard) 改写，采用 MIT 许可证。

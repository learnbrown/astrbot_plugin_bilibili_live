# AstrBot Bilibili 直播间状态查询插件

一个基于 [AstrBot](https://github.com/Soulter/AstrBot) 机器人框架的轻量级插件。用户只需在聊天框输入 `/live <房间号>`，机器人就会自动抓取并返回该 B 站直播间的最新状态、标题以及主播昵称。

## ✨ 功能特性

- **一键查询**：支持通过 B 站直播间长号/短号进行查询。
- **异步高效**：底层基于 `httpx` 异步网络库，支持连接池复用，响应速度极快，不阻塞机器人其他功能。
- **优雅的格式化输出**：直接返回排版整洁的卡片式文本。

## 📥 安装方法

### 方法一：通过 AstrBot 面板安装
从链接安装 `https://github.com/learnbrown/astrbot_plugin_bilibili_live`

### 方法二：直接放入插件目录

1. 进入你 AstrBot 的插件目录（如果在 Docker 中，请找到你挂载的 `plugins` 目录）。
2. 执行`git clone https://github.com/learnbrown/astrbot_plugin_bilibili_live.git`



## 🎮 使用说明

插件成功加载后，在机器人所在的群聊或私聊中发送以下指令：

### 1. 订阅直播间

**指令格式**

```text
/sub <房间号>       订阅直播间
/unsub <房间号>     取消订阅
/sub_list          查看以订阅直播间列表
```

### 2. 查询直播间信息

**指令格式**：

```text
/live <房间号>

```

**示例**：

```text
/live 33989

```

**机器人回复效果**：

```text
B站直播间 33989 信息
======================
UP主: 泛式 (UID: 63231)
标题: 最喜欢看阿B的电影了(已报备)
状态: 直播中
传送门: https://live.bilibili.com/33989

```

> **状态说明**：
> * 直播中：主播正在整活。
> * 未开播：主播还在休息。
> * 轮播中：当前正在放录播。
> 
> 

### 3. 查询用户信息

**指令格式**：

```text
/up <uid>

```

## 🛠️ 技术原理

使用 B 站 api 查询直播间及 Up 主信息

1. **房间状态**：请求 `https://api.live.bilibili.com/room/v1/Room/get_info?room_id=xxx` 接口获取 `title`、`live_status` 和 Up 主 `uid`。
2. **Up 主信息**：利用拿到的 `uid` 进一步请求 `https://api.bilibili.com/x/web-interface/card?mid=xxx` 接口获取 Up 主信息

## 📝 许可证

[MIT License](https://www.google.com/search?q=LICENSE)

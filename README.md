# AstrBot Bilibili 直播间订阅插件

一个基于 [AstrBot](https://github.com/Soulter/AstrBot) 机器人框架的轻量级插件。用户只需在聊天框输入 `/sub <room_id>`，机器人在Up主开播后第一时间发送通知。

## ✨ 功能特性

- **直播订阅**：通过直播间id订阅直播，开播后将第一时间通知。
- **一键查询**：支持通过 B 站直播间长号/短号进行查询。
- **优雅的格式化输出**：直接返回排版整洁的MarkDown格式文本。

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
/sub <room_id>       订阅直播间
/unsub <room_id>     取消订阅
/sublist             查看已订阅直播间列表
```

**机器人通知样例**

--- 
### 🔔 【直播提醒】您订阅的UP主开播啦！
- **UP主**: 泛式
- **直播间标题**: 周一工作中  
[🔗 直播间传送门](https://live.bilibili.com/33989)
--- 

### 2. 查询直播间信息

**指令格式**：

```/live <room_id>```


### 3. 查询用户信息

**指令格式**：

```/up <uid>```

## 🛠️ 技术原理

使用 B 站 api 查询直播间及 Up 主信息

1. **房间状态**：请求 `https://api.live.bilibili.com/room/v1/Room/get_info?room_id=xxx` 接口获取 `title`、`live_status` 和 Up 主 `uid`。
2. **Up 主信息**：利用拿到的 `uid` 进一步请求 `https://api.bilibili.com/x/web-interface/card?mid=xxx` 接口获取 Up 主信息

## 📝 许可证

[MIT License](https://www.google.com/search?q=LICENSE)

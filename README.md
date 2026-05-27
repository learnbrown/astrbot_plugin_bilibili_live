# AstrBot Bilibili 直播订阅插件

适用于 [AstrBot](https://github.com/Soulter/AstrBot) 的直播订阅插件。用户可通过聊天指令订阅 B 站直播间，机器人会在检测到目标直播间进入开播状态后，向对应会话发送通知。

当前文档对应版本：`1.3.8`

## 功能概览

- 支持按直播间房间号订阅与取消订阅。
- 支持查看当前会话下的订阅列表。
- 支持查询直播间信息与 UP 主信息。
- 支持轮询直播状态，并在开播时向订阅会话发送通知。
- 支持将订阅记录持久化到 `AstrBot/data/bilibili_live_subs.json`。

## 安装方式

### 方式一：通过 AstrBot 面板安装

仓库地址：

```text
https://github.com/learnbrown/astrbot_plugin_bilibili_live
```

### 方式二：手动放入插件目录

1. 进入 AstrBot 的插件目录。
2. 执行以下命令：

```bash
git clone https://github.com/learnbrown/astrbot_plugin_bilibili_live.git
```

## 指令说明

| 指令 | 参数 | 说明 |
| --- | --- | --- |
| `/sub <room_id>` | `room_id` | 订阅指定直播间 |
| `/unsub <room_id>` | `room_id` | 取消订阅指定直播间 |
| `/sublist` | 无 | 查看当前会话的订阅列表 |
| `/live <room_id>` | `room_id` | 查询直播间信息 |
| `/up <uid>` | `uid` | 查询 UP 主信息 |

## 消息示例

### 命令响应示例

以下内容由 `event.plain_result` 返回，支持 Markdown 渲染：

```markdown
### 订阅已生效

- 主播：**泛式**
- 房间号：`33989`
- 当前状态：未开播
- 说明：机器人将在状态变更为“直播中”后发送通知。
```

### 主动通知示例

以下内容由 `self.context.send_message` 主动发送。由于当前框架限制，该类消息暂不支持 Markdown：

```text
【B站开播通知】
主播：泛式
房间号：33989
直播标题：周一工作中
直播链接：https://live.bilibili.com/33989
```

## 数据存储

订阅信息默认保存到以下位置：

```text
AstrBot/data/bilibili_live_subs.json
```

存储内容包含以下信息：

- 直播间房间号
- 主播名称
- 上次轮询状态
- 订阅该直播间的会话标识列表

## 工作机制

插件主要依赖以下 B 站接口：

1. 直播间信息接口  
   `https://api.live.bilibili.com/room/v1/Room/get_info?room_id=<room_id>`
2. UP 主信息接口  
   `https://api.bilibili.com/x/web-interface/card?mid=<uid>`

轮询任务会定期读取订阅记录并查询直播状态。当检测到状态从“非直播中”切换为“直播中”时，插件会向已订阅该直播间的会话发送开播通知。

## 兼容性说明

- 支持 Markdown 的命令响应会优先使用结构化 Markdown 文本输出。
- 主动推送消息受 AstrBot 当前框架限制，暂时使用纯文本格式发送。

## 变更记录

详细更新请参见 [CHANGELOG.md](./CHANGELOG.md)。

## 许可证

本项目基于 [MIT License](https://en.wikipedia.org/wiki/MIT_License) 发布。

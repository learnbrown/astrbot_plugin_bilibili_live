import asyncio
import json
import os

import httpx

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register


@register("bilibili_live_viewer", "ReinerBrown", "通过房间号查询B站直播间状态", "1.3.3")
class BilibiliLivePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 初始化一个全局的 AsyncClient，复用连接池提升性能
        # 别忘了加上 User-Agent 伪装
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://search.bilibili.com/",
        }
        self.client = httpx.AsyncClient(headers=self.headers, timeout=5.0)

        # 获取当前插件文件 (__init__.py) 的绝对路径
        plugin_dir = os.path.dirname(
            __file__
        )  # 对应 \AstrBot\data\plugins\astrbot_plugin_bilibili_live

        # 连续向上跳两级，到达 \AstrBot\data 目录
        plugins_dir = os.path.dirname(plugin_dir)  # 对应 \AstrBot\data\plugins
        data_dir = os.path.dirname(plugins_dir)  # 对应 \AstrBot\data

        # 将数据文件拼接到 data 目录下
        self.db_path = os.path.join(data_dir, "bilibili_live_subs.json")
        logger.info(f"[B站订阅] 数据持久化路径已定位至: {self.db_path}")
        self.subscribed_rooms = self.load_data()

        # 定义后台轮询任务变量
        self.polling_task = None

    async def initialize(self):
        """插件初始化"""
        logger.info("Bilibili 直播间查询插件已加载。")

        # 启动异步循环轮询
        self.polling_task = asyncio.create_task(self.start_polling())

    async def terminate(self):
        """插件销毁时关闭 httpx 客户端，释放连接池"""
        await self.client.aclose()

        if self.polling_task:
            self.polling_task.cancel()
            try:
                # 等待任务彻底结束，防止抛出未处理的 CancelledError 异常
                await self.polling_task
            except asyncio.CancelledError:
                pass

        # 最后关闭网络连接池
        await self.client.aclose()

        logger.info("Bilibili 直播间查询插件已卸载。")

    # 注册 /live 指令，接收一个 int 类型的 room_id 参数
    @filter.command("live")
    async def get_live_info(self, event: AstrMessageEvent, room_id: int):
        """查询 B 站直播间状态。使用方法: /live <房间号>"""

        # 提示用户正在查询（对于耗时网络请求，先给个反馈体验更好，可根据喜好删留）
        # yield event.plain_result(f"正在查询直播间 {room_id} 的信息，请稍候...")

        # 1. 尝试调用第一个接口获取直播状态和标题
        info_url = "https://api.live.bilibili.com/room/v1/Room/get_info"

        try:
            response = await self.client.get(info_url, params={"room_id": room_id})
            response.raise_for_status()
            res_json = response.json()

            if res_json.get("code") != 0:
                yield event.plain_result(
                    f"查询失败，API 报错: {res_json.get('message')}"
                )
                return

            data = res_json.get("data", {})
            title = data.get("title", "无标题")
            status_code = data.get("live_status", 0)
            uid = data.get("uid")

            # 状态映射
            status_map = {0: "未开播", 1: "直播中", 2: "轮播中"}
            live_status = status_map.get(status_code, "未知状态")

            # 2. 如果成功拿到 uid，我们可以顺便请求第二个接口获取主播昵称
            uname = "未知主播"
            if uid:
                user_url = f"https://api.bilibili.com/x/web-interface/card?mid={uid}"
                try:
                    # 获取主播昵称名片
                    user_resp = await self.client.get(user_url)
                    if user_resp.status_code == 200:
                        user_json = user_resp.json()
                        if user_json.get("code") == 0:
                            uname = (
                                user_json.get("data", {})
                                .get("card", {})
                                .get("name", "未知主播")
                            )
                except Exception:
                    # 获取昵称失败不影响大局，静默处理即可
                    pass

            # 3. 组装最终结果文本发送给用户
            result_text = (
                f"B站直播间 {room_id} 信息\n"
                f"======================\n"
                f"UP主: {uname} (UID: {uid})\n"
                f"标题: {title}\n"
                f"状态: {live_status}\n"
                f"传送门: https://live.bilibili.com/{room_id}"
            )

            yield event.plain_result(result_text)

        except httpx.TimeoutException:
            yield event.plain_result("请求超时，B站服务器可能开小差了，请稍后再试。")
        except httpx.HTTPStatusError as e:
            yield event.plain_result(f"网络请求异常，状态码: {e.response.status_code}")
        except Exception as e:
            logger.error(f"插件运行出错: {str(e)}")
            yield event.plain_result("发生未知错误，请检查日志。")

    @filter.command("up")
    async def get_up_info(self, event: AstrMessageEvent, uid: int):
        """查询 B 站 UP 主信息。使用方法: /up <UID>"""
        user_url = f"https://api.bilibili.com/x/web-interface/card?mid={uid}"
        try:
            response = await self.client.get(user_url)
            response.raise_for_status()
            res_json = response.json()

            if res_json.get("code") != 0:
                yield event.plain_result(
                    f"查询失败，API 报错: {res_json.get('message')}"
                )
                return

            data = res_json.get("data", {}).get("card", {})
            uname = data.get("name", "未知UP主")
            sign = data.get("sign", "无签名")
            level = data.get("level_info", {}).get("current_level", "未知等级")
            fans = data.get("fans", "未知粉丝数")

            result_text = (
                f"B站UP主信息\n"
                f"======================\n"
                f"昵称: {uname}\n"
                f"签名: {sign}\n"
                f"等级: {level}\n"
                f"粉丝数: {fans}\n"
                f"个人主页: https://space.bilibili.com/{uid}"
            )

            yield event.plain_result(result_text)

        except httpx.TimeoutException:
            yield event.plain_result("请求超时，B站服务器可能开小差了，请稍后再试。")
        except httpx.HTTPStatusError as e:
            yield event.plain_result(f"网络请求异常，状态码: {e.response.status_code}")
        except Exception as e:
            logger.error(f"插件运行出错: {str(e)}")
            yield event.plain_result("发生未知错误，请检查日志。")

    def load_data(self):
        """从 JSON 文件加载订阅数据"""
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"加载订阅数据失败: {e}")
        # 默认结构：{"房间号": {"uname": "主播名", "last_status": 0, "targets": ["unified_session_id_1"]}}
        return {}

    def save_data(self):
        """保存订阅数据到 JSON 文件"""
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.subscribed_rooms, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存订阅数据失败: {e}")

    @filter.command("sub", aliases=["subscribe"])
    async def subscribe_room(self, event: AstrMessageEvent, room_id: int):
        """订阅B站直播间。使用方法: /sub <房间号>"""
        session_id = (
            event.unified_msg_origin
        )  # 获取当前聊天场景的唯一ID（群或私聊），用于后续精准推送通知
        room_str = str(room_id)

        # 如果已经订阅过，检查当前聊天场景是否在通知列表中
        if room_str in self.subscribed_rooms:
            if session_id in self.subscribed_rooms[room_str]["targets"]:
                yield event.plain_result(f"已经订阅过直播间 {room_id}")
                return
            else:
                self.subscribed_rooms[room_str]["targets"].append(session_id)
                self.save_data()
                yield event.plain_result(f"成功订阅直播间 {room_id}")
                return

        # 如果是全新的房间号，先请求一次获取主播名字和当前状态
        yield event.plain_result(f"正在验证直播间 {room_id} 的信息...")
        info_url = "https://api.live.bilibili.com/room/v1/Room/get_info"

        try:
            resp = await self.client.get(info_url, params={"room_id": room_id})
            res_json = resp.json()
            if res_json.get("code") != 0:
                yield event.plain_result(
                    f"订阅失败，B站API报错: {res_json.get('message')}"
                )
                return

            data = res_json.get("data", {})
            uid = data.get("uid")
            # last_status = data.get("live_status", 0) # 0未开播，1直播，2轮播
            last_status = 0

            # 获取昵称
            uname = "未知主播"
            if uid:
                card_url = "https://api.bilibili.com/x/web-interface/card"
                card_resp = await self.client.get(card_url, params={"mid": uid})
                if card_resp.json().get("code") == 0:
                    uname = (
                        card_resp.json()
                        .get("data", {})
                        .get("card", {})
                        .get("name", "未知主播")
                    )

            # 写入内存并保存
            self.subscribed_rooms[room_str] = {
                "uname": uname,
                "last_status": last_status,
                "targets": [session_id],
            }
            self.save_data()
            yield event.plain_result(
                f"成功订阅主播 「{uname}」 (房间号: {room_id})！开播时将会收到通知。"
            )

        except Exception as e:
            yield event.plain_result(f"订阅失败，网络请求异常: {str(e)}")

    @filter.command("unsub")
    async def unsubscribe_room(self, event: AstrMessageEvent, room_id: int):
        """取消订阅B站直播间。使用方法: /unsub <房间号>"""
        session_id = event.unified_msg_origin
        room_str = str(room_id)

        if (
            room_str not in self.subscribed_rooms
            or session_id not in self.subscribed_rooms[room_str]["targets"]
        ):
            yield event.plain_result(f"当前聊天框并没有订阅过房间号 {room_id}。")
            return

        self.subscribed_rooms[room_str]["targets"].remove(session_id)
        # 如果没有任何渠道订阅该房间了，直接从配置里彻底移除
        if not self.subscribed_rooms[room_str]["targets"]:
            self.subscribed_rooms.pop(room_str)

        self.save_data()
        yield event.plain_result(f"成功取消订阅直播间 {room_id}。")

    @filter.command("sub_list", aliases=["subs", "subscriptions", "sublist"])
    async def list_subscriptions(self, event: AstrMessageEvent):
        """查看本聊天框已订阅的直播间列表"""
        session_id = event.unified_msg_origin
        lines = []

        for room_id, info in self.subscribed_rooms.items():
            if session_id in info["targets"]:
                status_str = "直播中" if info["last_status"] == 1 else "未开播"
                lines.append(f"- {info['uname']} ({room_id}) [{status_str}]")

        if not lines:
            yield event.plain_result("当前没有订阅任何直播间。使用 /sub <房间号> 订阅")
        else:
            yield event.plain_result("当前已订阅的直播间：\n" + "\n".join(lines))

    # ================= 后台轮询逻辑 =================

    async def start_polling(self):
        """异步轮询核心逻辑"""
        # 建议等待系统完全启动后再开始轮询
        await asyncio.sleep(10)

        while True:
            if self.client.is_closed:
                logger.warning("[B站直播轮询] 检测到 client 已关闭，轮询任务自动退出。")
                break

            if self.subscribed_rooms:
                logger.info(
                    f"[B站直播轮询] 开始检查 {len(self.subscribed_rooms)} 个直播间..."
                )
                info_url = "https://api.live.bilibili.com/room/v1/Room/get_info"

                for room_id, info in list(self.subscribed_rooms.items()):
                    if self.client.is_closed:
                        break

                    try:
                        resp = await self.client.get(
                            info_url, params={"room_id": int(room_id)}
                        )
                        if resp.status_code != 200:
                            continue

                        res_json = resp.json()
                        if res_json.get("code") != 0:
                            continue

                        data = res_json.get("data", {})
                        current_status = data.get("live_status", 0)
                        title = data.get("title", "无标题")

                        # 🌟 核心判断：如果上次是 0 (未开播) 或 2 (轮播)，这次变成了 1 (直播中) -> 触发开播提醒
                        if info["last_status"] != 1 and current_status == 1:
                            notice_text = (
                                f"【直播提醒】您订阅的Up主开播了\n"
                                f"=========================\n"
                                f"Up主: {info['uname']}\n"
                                f"直播间标题: {title}\n"
                                f"传送门: https://live.bilibili.com/{room_id}"
                            )
                            message_chain = MessageChain().message(notice_text)
                            # 循环向所有订阅了该房间的聊天窗口发送通知
                            for target_session_id in info["targets"]:
                                try:
                                    # 利用 AstrBot 内置的 context.send_message 向指定 session 发送主动消息
                                    await self.context.send_message(
                                        target_session_id, message_chain
                                    )
                                except Exception as send_err:
                                    logger.error(f"发送开播通知失败: {send_err}")

                        # 更新内存中的最新状态并保存
                        if info["last_status"] != current_status:
                            self.subscribed_rooms[room_id]["last_status"] = (
                                current_status
                            )
                            self.save_data()
                    except RuntimeError as e:
                        # 捕捉 client 已经关闭的运行时异常，直接优雅地结束
                        logger.warning(
                            f"[B站直播轮询] 捕获到客户端运行时异常(可能已被关闭): {e}"
                        )
                        break
                    except Exception as e:
                        logger.error(f"轮询直播间 {room_id} 出错: {e}")

                    # 每次请求完一个房间歇 1 秒，防止短时间请求太猛被B站封IP
                    await asyncio.sleep(1)

            try:
                await asyncio.sleep(180)
            except asyncio.CancelledError:
                # 🌟 修复点 3：响应 terminate 的 cancel 信号，优雅退出
                logger.info("[B站直播轮询] 轮询任务收到取消信号，正在退出...")
                break

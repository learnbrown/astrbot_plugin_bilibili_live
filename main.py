import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

ROOM_INFO_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
USER_CARD_URL = "https://api.bilibili.com/x/web-interface/card"
LIVE_STATUS_TEXT = {
    0: "未开播",
    1: "直播中",
    2: "轮播中",
}
STARTUP_DELAY_SECONDS = 10
POLL_INTERVAL_SECONDS = 180
REQUEST_INTERVAL_SECONDS = 1


@register(
    "bilibili_live_subscription",
    "ReinerBrown",
    "通过房间号订阅B站直播间，开播后将会收到通知",
    "1.3.8",
)
class BilibiliLivePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://search.bilibili.com/",
        }
        self.client = httpx.AsyncClient(headers=self.headers, timeout=5.0)

        plugin_dir = Path(__file__).resolve().parent
        data_dir = plugin_dir.parent.parent
        self.db_path = data_dir / "bilibili_live_subs.json"
        logger.info(f"[B站订阅] 数据持久化路径: {self.db_path}")

        self.subscribed_rooms = self.load_data()
        self.polling_task: asyncio.Task | None = None

    async def initialize(self):
        """插件初始化。"""
        logger.info("Bilibili 直播订阅插件已加载。")
        if self.polling_task is None or self.polling_task.done():
            self.polling_task = asyncio.create_task(self.start_polling())

    async def terminate(self):
        """插件销毁时停止轮询任务并关闭 HTTP 客户端。"""
        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
            finally:
                self.polling_task = None

        if not self.client.is_closed:
            await self.client.aclose()

        logger.info("Bilibili 直播订阅插件已卸载。")

    def load_data(self) -> dict[str, dict[str, Any]]:
        """从 JSON 文件加载并规范化订阅数据。"""
        if not self.db_path.exists():
            return {}

        try:
            with self.db_path.open(encoding="utf-8") as file:
                raw_data = json.load(file)
        except Exception as exc:
            logger.error(f"加载订阅数据失败: {exc}")
            return {}

        return self._normalize_subscriptions(raw_data)

    def save_data(self):
        """保存订阅数据到 JSON 文件。"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self.db_path.open("w", encoding="utf-8") as file:
                json.dump(self.subscribed_rooms, file, ensure_ascii=False, indent=4)
        except Exception as exc:
            logger.error(f"保存订阅数据失败: {exc}")

    def _normalize_subscriptions(self, raw_data: Any) -> dict[str, dict[str, Any]]:
        """兼容旧数据，并过滤掉无法使用的订阅记录。"""
        if not isinstance(raw_data, dict):
            logger.warning("[B站订阅] 订阅文件格式不是字典，已忽略原始内容。")
            return {}

        normalized: dict[str, dict[str, Any]] = {}
        for room_id, info in raw_data.items():
            if not isinstance(info, dict):
                continue

            targets = info.get("targets", [])
            if isinstance(targets, str):
                targets = [targets]
            if not isinstance(targets, list):
                continue

            clean_targets: list[str] = []
            for target in targets:
                if isinstance(target, str) and target and target not in clean_targets:
                    clean_targets.append(target)

            if not clean_targets:
                continue

            last_status = info.get("last_status", 0)
            try:
                last_status = int(last_status)
            except (TypeError, ValueError):
                last_status = 0

            normalized[str(room_id)] = {
                "uname": str(info.get("uname") or "未知主播"),
                "last_status": last_status,
                "targets": clean_targets,
            }

        return normalized

    async def _request_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    async def _fetch_room_info(self, room_id: int) -> dict[str, Any]:
        payload = await self._request_json(ROOM_INFO_URL, {"room_id": room_id})
        if payload.get("code") != 0:
            raise ValueError(payload.get("message") or "直播间信息查询失败")
        return payload.get("data") or {}

    async def _fetch_user_card(self, uid: int) -> dict[str, Any]:
        payload = await self._request_json(USER_CARD_URL, {"mid": uid})
        if payload.get("code") != 0:
            raise ValueError(payload.get("message") or "UP主信息查询失败")
        return payload.get("data", {}).get("card", {}) or {}

    async def _fetch_anchor_name(self, uid: int | None) -> str:
        if not uid:
            return "未知主播"

        try:
            card = await self._fetch_user_card(uid)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(f"[B站订阅] 获取主播昵称失败，uid={uid}: {exc}")
            return "未知主播"

        return card.get("name") or "未知主播"

    @staticmethod
    def _status_text(status_code: int) -> str:
        return LIVE_STATUS_TEXT.get(status_code, "未知状态")

    @staticmethod
    def _build_live_notice(uname: str, room_id: str, title: str) -> str:
        return (
            "【B站开播通知】\n"
            f"主播：{uname}\n"
            f"房间号：{room_id}\n"
            f"直播标题：{title}\n"
            f"直播链接：https://live.bilibili.com/{room_id}"
        )

    @staticmethod
    def _build_http_error_message(exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "请求超时，请稍后重试。"
        if isinstance(exc, httpx.HTTPStatusError):
            return f"网络请求失败，HTTP 状态码：{exc.response.status_code}。"
        if isinstance(exc, httpx.HTTPError):
            return f"网络请求失败：{exc}"
        if isinstance(exc, ValueError):
            return str(exc)
        return f"处理请求时发生异常：{exc}"

    @filter.command("sub", alias={"订阅"})
    async def subscribe_room(self, event: AstrMessageEvent, room_id: int):
        """订阅 B 站直播间。使用方法: /sub <房间号>"""
        session_id = event.unified_msg_origin
        room_key = str(room_id)
        existing = self.subscribed_rooms.get(room_key)

        if existing:
            if session_id in existing["targets"]:
                yield event.plain_result(
                    f"### 订阅状态\n\n当前会话已订阅直播间 `{room_id}`，无需重复提交。"
                )
                return

            existing["targets"].append(session_id)
            self.save_data()
            yield event.plain_result(
                "### 订阅已更新\n\n"
                f"- 主播：**{existing['uname']}**\n"
                f"- 房间号：`{room_id}`\n"
                "- 结果：当前会话已加入通知范围。"
            )
            return

        yield event.plain_result(
            f"### 订阅请求已接收\n\n正在核验直播间 `{room_id}` 的信息，请稍候。"
        )

        try:
            room_info = await self._fetch_room_info(room_id)
            uid = room_info.get("uid")
            uname = await self._fetch_anchor_name(uid)
            current_status = int(room_info.get("live_status", 0))

            # 首次订阅时记录当前状态，避免主播本就开播时被误判为“刚刚开播”。
            self.subscribed_rooms[room_key] = {
                "uname": uname,
                "last_status": current_status,
                "targets": [session_id],
            }
            self.save_data()

            yield event.plain_result(
                "### 订阅已生效\n\n"
                f"- 主播：**{uname}**\n"
                f"- 房间号：`{room_id}`\n"
                f"- 当前状态：{self._status_text(current_status)}\n"
                "- 说明：机器人将在状态变更为“直播中”后发送通知。"
            )
        except Exception as exc:
            logger.error(f"[B站订阅] 订阅直播间失败，room_id={room_id}: {exc}")
            yield event.plain_result(
                f"### 订阅失败\n\n原因：{self._build_http_error_message(exc)}"
            )

    @filter.command("unsub", alias={"取消订阅"})
    async def unsubscribe_room(self, event: AstrMessageEvent, room_id: int):
        """取消订阅 B 站直播间。使用方法: /unsub <房间号>"""
        session_id = event.unified_msg_origin
        room_key = str(room_id)
        existing = self.subscribed_rooms.get(room_key)

        if not existing or session_id not in existing["targets"]:
            yield event.plain_result(
                f"### 未找到订阅记录\n\n当前会话未订阅直播间 `{room_id}`。"
            )
            return

        existing["targets"].remove(session_id)
        if not existing["targets"]:
            self.subscribed_rooms.pop(room_key, None)

        self.save_data()
        yield event.plain_result(
            "### 订阅已取消\n\n"
            f"- 房间号：`{room_id}`\n"
            "- 结果：当前会话不再接收该直播间的开播通知。"
        )

    @filter.command("sublist", alias={"订阅列表", "subs"})
    async def list_subscriptions(self, event: AstrMessageEvent):
        """查看当前会话的直播订阅列表。"""
        session_id = event.unified_msg_origin
        lines = []

        for room_id, info in self.subscribed_rooms.items():
            if session_id not in info["targets"]:
                continue

            lines.append(
                f"- **[{info['uname']}](https://live.bilibili.com/{room_id})**"
                f" | 房间号：`{room_id}`"
                f" | 状态：{self._status_text(info.get('last_status', 0))}"
            )

        if not lines:
            yield event.plain_result(
                "### 订阅列表\n\n当前会话暂无直播订阅记录。\n\n可使用 `/sub <房间号>` 添加订阅。"
            )
            return

        yield event.plain_result("### 订阅列表\n\n" + "\n".join(lines))

    async def start_polling(self):
        """后台轮询直播状态，并在状态切换为直播中时发送通知。"""
        await asyncio.sleep(STARTUP_DELAY_SECONDS)

        while True:
            try:
                if self.client.is_closed:
                    logger.warning("[B站轮询] HTTP 客户端已关闭，轮询任务结束。")
                    break

                data_changed = False
                if self.subscribed_rooms:
                    logger.info(
                        f"[B站轮询] 本轮开始检查 {len(self.subscribed_rooms)} 个直播间。"
                    )

                for room_id, info in list(self.subscribed_rooms.items()):
                    if self.client.is_closed:
                        break

                    try:
                        room_info = await self._fetch_room_info(int(room_id))
                        current_status = int(room_info.get("live_status", 0))
                        title = room_info.get("title") or "无标题"
                        previous_status = int(info.get("last_status", 0))

                        if previous_status != 1 and current_status == 1:
                            # 主动推送目前不支持 Markdown，因此这里使用纯文本通知。
                            notice_text = self._build_live_notice(
                                info.get("uname", "未知主播"),
                                room_id,
                                title,
                            )
                            message_chain = MessageChain().message(notice_text)

                            for target_session_id in list(info.get("targets", [])):
                                try:
                                    await self.context.send_message(
                                        target_session_id, message_chain
                                    )
                                except Exception as send_exc:
                                    logger.error(
                                        "[B站轮询] 发送开播通知失败，"
                                        f"room_id={room_id}, target={target_session_id}: {send_exc}"
                                    )

                        if previous_status != current_status:
                            self.subscribed_rooms[room_id]["last_status"] = (
                                current_status
                            )
                            data_changed = True

                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        logger.error(f"[B站轮询] 查询直播间 {room_id} 失败: {exc}")

                    await asyncio.sleep(REQUEST_INTERVAL_SECONDS)

                if data_changed:
                    self.save_data()

                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                logger.info("[B站轮询] 轮询任务收到取消信号，正在退出。")
                break

    @filter.command("live")
    async def get_live_info(self, event: AstrMessageEvent, room_id: int):
        """查询 B 站直播间信息。使用方法: /live <房间号>"""
        try:
            room_info = await self._fetch_room_info(room_id)
            uid = room_info.get("uid")
            uname = await self._fetch_anchor_name(uid)
            title = room_info.get("title") or "无标题"
            status_code = int(room_info.get("live_status", 0))

            result_text = (
                "### 直播间信息\n\n"
                f"- 房间号：`{room_id}`\n"
                f"- 主播：**{uname}**\n"
                f"- UID：`{uid}`\n"
                f"- 标题：{title}\n"
                f"- 状态：{self._status_text(status_code)}\n"
                f"- 链接：[进入直播间](https://live.bilibili.com/{room_id})"
            )
            yield event.plain_result(result_text)
        except Exception as exc:
            logger.error(f"[B站查询] 查询直播间失败，room_id={room_id}: {exc}")
            yield event.plain_result(
                f"### 查询失败\n\n原因：{self._build_http_error_message(exc)}"
            )

    @filter.command("up")
    async def get_up_info(self, event: AstrMessageEvent, uid: int):
        """查询 B 站 UP 主信息。使用方法: /up <UID>"""
        try:
            user_card = await self._fetch_user_card(uid)
            uname = user_card.get("name") or "未知UP主"
            sign = user_card.get("sign") or "无签名"
            level = user_card.get("level_info", {}).get("current_level", "未知等级")
            fans = user_card.get("fans", "未知粉丝数")

            result_text = (
                "### UP 主信息\n\n"
                f"- 昵称：**{uname}**\n"
                f"- UID：`{uid}`\n"
                f"- 等级：Lv.{level}\n"
                f"- 粉丝数：{fans}\n"
                f"- 签名：{sign}\n"
                f"- 主页：[访问空间](https://space.bilibili.com/{uid})"
            )
            yield event.plain_result(result_text)
        except Exception as exc:
            logger.error(f"[B站查询] 查询UP主失败，uid={uid}: {exc}")
            yield event.plain_result(
                f"### 查询失败\n\n原因：{self._build_http_error_message(exc)}"
            )

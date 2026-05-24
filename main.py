from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import httpx

@register("bilibili_live_viewer", "ReinerBrown", "通过房间号查询B站直播间状态", "1.1.3")
class BilibiliLivePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 初始化一个全局的 AsyncClient，复用连接池提升性能
        # 别忘了加上 User-Agent 伪装
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.client = httpx.AsyncClient(headers=self.headers, timeout=5.0)

    async def initialize(self):
        """插件初始化"""
        logger.info("Bilibili 直播间查询插件已加载。")

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
                yield event.plain_result(f"查询失败，API 报错: {res_json.get('message')}")
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
                            uname = user_json.get("data", {}).get("card", {}).get("name", "未知主播")
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

    async def terminate(self):
        """插件销毁时关闭 httpx 客户端，释放连接池"""
        await self.client.aclose()
        logger.info("Bilibili 直播间查询插件已卸载。")
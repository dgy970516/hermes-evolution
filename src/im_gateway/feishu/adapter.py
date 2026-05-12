"""
Feishu Adapter — WebSocket long connection mode
================================================
Uses lark-oapi SDK's WebSocket client (ws.Client) to receive events.
No ngrok or public URL needed — Hermes connects outbound to Feishu.

Event subscription setting must be: "Receive events through persistent connection"
"""

import asyncio
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import aiohttp

from src.im_gateway.base import IMAdapter, Message as HermesMessage, Card

logger = logging.getLogger("hermes.feishu")

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"


def _create_session() -> aiohttp.ClientSession:
    import ssl
    if os.environ.get("SSL_VERIFY", "").lower() in ("none", "false", "0"):
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        logger.warning("SSL verification disabled")
        return aiohttp.ClientSession(connector=connector)
    try:
        import certifi
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        return aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx))
    except ImportError:
        return aiohttp.ClientSession()


class FeishuAdapter(IMAdapter):
    def __init__(self, app_id: str, app_secret: str, verification_token: str = "", encrypt_key: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._message_handler = None
        self._token = ""
        self._token_expires = 0
        self._session: aiohttp.ClientSession | None = None
        self._ws_thread: threading.Thread | None = None
        self._ws_client = None

    async def initialize(self):
        self._session = _create_session()
        await self._refresh_token()
        logger.info("Feishu adapter initialized")

    async def _refresh_token(self):
        if not self._session:
            return
        try:
            async with self._session.post(
                FEISHU_TOKEN_URL,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            ) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    self._token = data["tenant_access_token"]
                    self._token_expires = time.time() + data.get("expire", 7200) - 60
                    logger.info("Feishu token refreshed")
                else:
                    logger.warning(f"Feishu token error: {data.get('msg', '')}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Feishu auth failed: {e}")

    async def _ensure_token(self):
        if time.time() >= self._token_expires:
            await self._refresh_token()

    # ── WebSocket Event Subscription ──

    def start_ws(self, message_callback):
        """
        Start WebSocket long connection to receive Feishu events.
        No ngrok needed — connects outbound to Feishu's server.

        In Feishu Dev Console → 事件与回调 → 订阅方式:
          Choose: "Receive events through persistent connection" (长连接)
        """
        import lark_oapi as lark

        # 保存主事件循环引用（start_ws 在主线程调用）
        try:
            self._main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._main_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._main_loop)

        logger.info("Starting Feishu WebSocket connection...")

        def handle_message(data: lark.im.v1.P2ImMessageReceiveV1):
            try:
                event = data.event
                msg = event.message
                sender = event.sender

                msg_type = getattr(msg, "message_type", "") or getattr(msg, "msg_type", "") or ""
                content_raw = getattr(msg, "content", "") or "{}"
                chat_type = getattr(msg, "chat_type", "") or "p2p"

                if msg_type != "text":
                    return

                if hasattr(content_raw, "text"):
                    text = content_raw.text
                else:
                    try:
                        content = json.loads(content_raw) if isinstance(content_raw, str) else content_raw
                        text = content.get("text", "") if isinstance(content, dict) else str(content)
                    except (json.JSONDecodeError, TypeError):
                        text = str(content_raw)

                user_id = ""
                if sender and hasattr(sender, "sender_id") and sender.sender_id:
                    si = sender.sender_id
                    user_id = getattr(si, "open_id", "") or getattr(si, "user_id", "") or ""

                if chat_type == "group" and "@" not in text:
                    return
                if "@" in text:
                    text = text.split("@")[0].strip()

                if not text or not user_id:
                    return

                logger.info(f"📩 Feishu message from {user_id[:8]}...: {text[:100]}")

                if message_callback and self._main_loop and not self._main_loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        self._process_and_respond(user_id, text, message_callback),
                        self._main_loop,
                    )

            except Exception as e:
                logger.error(f"Handle message error: {e}", exc_info=True)

        event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(handle_message) \
            .build()

        self._ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        logger.info("✅ Feishu WebSocket connecting...")

        # Patch asyncio to allow nested event loops (needed for ws.Client in a thread)
        import nest_asyncio
        nest_asyncio.apply()

        # ws.Client.start() blocks, so run in a thread
        self._ws_thread = threading.Thread(target=self._ws_client.start, daemon=True)
        self._ws_thread.start()
        logger.info("✅ Feishu WebSocket started (no ngrok needed!)")

    async def _process_and_respond(self, user_id: str, text: str, callback):
        """Process message and send response back via Feishu"""
        try:
            await callback(user_id, text)
        except Exception as e:
            logger.error(f"Process error: {e}")
            await self.send_message(user_id, f"❌ 处理出错: {str(e)[:100]}")

    def stop_ws(self):
        if self._ws_client:
            try:
                self._ws_client.stop()
            except Exception:
                pass

    # ── Send Messages (via REST API) ──

    async def send_message(self, user_id: str, content: str, retry: int = 1):
        await self._ensure_token()
        if not self._token:
            logger.error("No Feishu token available")
            return

        # 清理内容
        safe_content = content.strip()
        safe_content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', safe_content)
        # 替换 markdown 代码块为简单格式
        safe_content = safe_content.replace("```", "")
        # 连续空行压缩为单个
        safe_content = re.sub(r'\n{3,}', '\n\n', safe_content)
        # 每行缩进清理
        safe_content = safe_content[:1500]

        display = safe_content[:60].replace("\n", " ")
        body = {
            "receive_id": user_id,
            "msg_type": "text",
            "content": json.dumps({"text": safe_content}, ensure_ascii=False),
        }

        for attempt in range(retry):
            try:
                async with self._session.post(
                    FEISHU_SEND_URL,
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=body,
                ) as resp:
                    result = await resp.json()
                    if result.get("code") == 0:
                        logger.info(f"✅ Sent: {display}")
                        return
                    elif result.get("code") == 99991663:
                        logger.warning("Token expired, refreshing...")
                        await self._refresh_token()
                        continue
                    else:
                        logger.warning(f"Send failed ({result.get('code')}): {result.get('msg', '')}")
                        # 如果是内容问题，尝试简化消息
                        if "content" in result.get("msg", ""):
                            simpler = safe_content.replace("```", "'").replace("\\", "/")[:500]
                            body["content"] = json.dumps({"text": simpler}, ensure_ascii=False)
                            continue
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Send error (attempt {attempt+1}): {e}")
                if attempt < retry - 1:
                    await asyncio.sleep(1)

    async def send_card(self, user_id: str, card: Card):
        await self._ensure_token()
        if not self._token:
            return

        card_json = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": card.title}},
            "elements": [{"tag": "markdown", "content": card.content}],
        }
        if card.buttons:
            card_json["elements"].append({
                "tag": "action",
                "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": btn["text"]},
                     "type": "primary" if btn.get("text") == "确认" else "default",
                     "value": {"action": btn.get("action", "")}}
                    for btn in card.buttons
                ],
            })

        try:
            async with self._session.post(
                FEISHU_SEND_URL,
                headers={"Authorization": f"Bearer {self._token}"},
                json={"receive_id": user_id, "msg_type": "interactive", "content": json.dumps(card_json, ensure_ascii=False)},
            ) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    logger.warning(f"Card send failed: {result.get('msg', '')}")
        except Exception as e:
            logger.error(f"Card error: {e}")

    async def send_file(self, user_id: str, filepath: str, filename: str = "") -> dict:
        """Upload and send a file to Feishu user"""
        import aiohttp as aiohttp_module

        await self._ensure_token()
        if not self._token:
            return {"success": False, "message": "No token"}

        file_path = Path(filepath)
        if not file_path.exists():
            return {"success": False, "message": f"File not found: {filepath}"}

        display_name = filename or file_path.name

        # Step 1: Upload file
        upload_url = "https://open.feishu.cn/open-apis/im/v1/files"
        try:
            async with self._session.post(
                upload_url,
                headers={"Authorization": f"Bearer {self._token}"},
                data=aiohttp_module.FormData({
                    "file_type": "xlsx",
                    "file_name": display_name,
                    "file": open(file_path, "rb"),
                }),
            ) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    return {"success": False, "message": result.get("msg", "")}
                file_key = result["data"]["file_key"]
        except Exception as e:
            return {"success": False, "message": f"Upload error: {e}"}

        # Step 2: Send file message
        file_msg_url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
        body = {
            "receive_id": user_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}),
        }
        try:
            async with self._session.post(
                file_msg_url,
                headers={"Authorization": f"Bearer {self._token}"},
                json=body,
            ) as resp:
                result = await resp.json()
                if result.get("code") == 0:
                    logger.info(f"✅ File sent to {user_id[:8]}...: {display_name}")
                    return {"success": True, "file_key": file_key}
                return {"success": False, "message": result.get("msg", "")}
        except Exception as e:
            return {"success": False, "message": f"Send error: {e}"}

    async def send_image(self, user_id: str, filepath: str) -> dict:
        """Upload and send an image to Feishu (uses image API, not file API)"""
        import aiohttp as aiohttp_module

        await self._ensure_token()
        if not self._token:
            return {"success": False, "message": "No token"}

        file_path = Path(filepath)
        if not file_path.exists():
            return {"success": False, "message": f"File not found: {filepath}"}

        # Step 1: Upload image
        upload_url = "https://open.feishu.cn/open-apis/im/v1/images"
        try:
            async with self._session.post(
                upload_url,
                headers={"Authorization": f"Bearer {self._token}"},
                data=aiohttp_module.FormData({
                    "image_type": "message",
                    "image": open(file_path, "rb"),
                }),
            ) as resp:
                result = await resp.json()
                if result.get("code") != 0:
                    return {"success": False, "message": result.get("msg", "")}
                image_key = result["data"]["image_key"]
        except Exception as e:
            return {"success": False, "message": f"Upload error: {e}"}

        # Step 2: Send image message
        img_msg_url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
        body = {
            "receive_id": user_id,
            "msg_type": "image",
            "content": json.dumps({"image_key": image_key}),
        }
        try:
            async with self._session.post(
                img_msg_url,
                headers={"Authorization": f"Bearer {self._token}"},
                json=body,
            ) as resp:
                result = await resp.json()
                if result.get("code") == 0:
                    logger.info(f"✅ Image sent to {user_id[:8]}...")
                    return {"success": True, "image_key": image_key}
                return {"success": False, "message": result.get("msg", "")}
        except Exception as e:
            return {"success": False, "message": f"Send error: {e}"}

    async def on_message(self, handler):
        """Required by IMAdapter — use start_ws() instead for WebSocket mode"""
        self._message_handler = handler

    async def close(self):
        self.stop_ws()
        if self._session:
            await self._session.close()

from src.im_gateway.base import IMAdapter, Message, Card


class WechatAdapter(IMAdapter):
    async def send_message(self, user_id: str, content: str):
        raise NotImplementedError("WeChat adapter is not yet implemented")

    async def send_card(self, user_id: str, card: Card):
        raise NotImplementedError("WeChat adapter is not yet implemented")

    async def on_message(self, handler):
        raise NotImplementedError("WeChat adapter is not yet implemented")

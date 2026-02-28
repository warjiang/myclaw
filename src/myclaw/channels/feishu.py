import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from enum import Enum

import lark_oapi as lark
from aiohttp import web


logger = logging.getLogger(__name__)


class FeishuMode(str, Enum):
  WEBSOCKET = "websocket"
  HTTP = "http"


class BaseFeishuChannel:
  def __init__(self, on_message: Callable[[str], Awaitable[None]]):
    self.on_message = on_message

  async def start(self):
    raise NotImplementedError

  async def send(self, message: str, end: str = "\n"):
    raise NotImplementedError


class WebSocketFeishuChannel(BaseFeishuChannel):
  def __init__(
    self,
    on_message: Callable[[str], Awaitable[None]],
    app_id: str,
    app_secret: str,
  ):
    super().__init__(on_message)
    self.app_id = app_id
    self.app_secret = app_secret
    self._ws_client = None
    self._pending_task: asyncio.Task | None = None
    self._loop: asyncio.AbstractEventLoop | None = None

  def _do_p2_im_message_receive_v1(self, data: lark.im.v1.P2ImMessageReceiveV1):
    logger.info(f"Received message event: {data}")
    message = data.message
    if message.msg_type == "text":
      content = json.loads(message.content)
      text = content.get("text", "")
      logger.info(f"Received text message: {text}")
      if text:
        if self._loop and self._loop.is_running():
          asyncio.run_coroutine_threadsafe(self.on_message(text), self._loop)
        else:
          logger.warning("Event loop not available, skipping message")

  async def start(self):
    logger.info(f"Starting Feishu WebSocket client with app_id: {self.app_id[:10]}...")

    self._loop = asyncio.get_running_loop()
    logger.info(f"Got event loop: {self._loop}")

    event_handler = (
      lark.EventDispatcherHandler.builder("", "")
      .register_p2_im_message_receive_v1(self._do_p2_im_message_receive_v1)
      .build()
    )

    self._ws_client = lark.ws.Client(
      self.app_id,
      self.app_secret,
      event_handler=event_handler,
      log_level=lark.LogLevel.DEBUG,
    )
    self._ws_client.start()

  async def send(self, message: str, end: str = "\n"):
    logger.info(f"WebSocket mode: message would be sent here: {message[:50]}...")


class FeishuError(Exception):
  def __init__(self, message: str):
    self.message = message
    super().__init__(message)


class HttpFeishuChannel(BaseFeishuChannel):
  def __init__(
    self,
    on_message: Callable[[str], Awaitable[None]],
    app_id: str,
    app_secret: str,
    verification_token: str,
    encrypt_key: str,
    webhook_url: str = "",
    host: str = "0.0.0.0",
    port: int = 8089,
  ):
    super().__init__(on_message)
    self.app_id = app_id
    self.app_secret = app_secret
    self.verification_token = verification_token
    self.encrypt_key = encrypt_key
    self.webhook_url = webhook_url
    self.host = host
    self.port = port
    self._server = None
    self._conf = None

  def _get_conf(self):
    if self._conf is None:
      self._conf = lark.Config.new_internal_app_settings(
        app_id=self.app_id,
        app_secret=self.app_secret,
        verification_token=self.verification_token,
        encrypt_key=self.encrypt_key,
      )
    return self._conf

  async def start(self):
    async def handle_webhook(request: web.Request) -> web.Response:
      body = await request.read()
      oapi_request = lark.OapiRequest(
        uri=request.path,
        body=body,
        header=lark.OapiHeader(dict(request.headers)),
      )
      oapi_resp = lark.handle_event(self._get_conf(), oapi_request)

      if oapi_resp.status_code == 200:
        try:
          data = json.loads(oapi_resp.body)
          event_type = data.get("header", {}).get("event_type", "")
          if event_type == "im.message.receive_v1":
            event_data = data.get("event", {})
            message = event_data.get("message", {})
            if message.get("msg_type") == "text":
              content = message.get("content", "")
              if content:
                try:
                  content_data = json.loads(content)
                  text = content_data.get("text", "")
                  if text:
                    await self.on_message(text)
                except json.JSONDecodeError:
                  await self.on_message(content)
        except Exception:
          logger.exception("Error parsing message")

      return web.Response(
        text=oapi_resp.body,
        content_type=oapi_resp.content_type,
        status=oapi_resp.status_code,
      )

    app = web.Application()
    app.router.add_post("/webhook/event", handle_webhook)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, self.host, self.port)
    await site.start()
    logger.info(f"Feishu HTTP server started on {self.host}:{self.port}")

    self._server = runner
    await asyncio.Event().wait()

  async def send(self, message: str, end: str = "\n"):
    logger.info(f"HTTP mode: message would be sent here: {message[:50]}...")


class FeishuChannel(BaseFeishuChannel):
  def __init__(
    self,
    on_message: Callable[[str], Awaitable[None]],
    app_id: str,
    app_secret: str,
    verification_token: str = "",
    encrypt_key: str = "",
    mode: str = "websocket",
    webhook_url: str = "",
    http_host: str = "0.0.0.0",
    http_port: int = 8089,
  ):
    super().__init__(on_message)
    self.app_id = app_id
    self.app_secret = app_secret
    self.verification_token = verification_token
    self.encrypt_key = encrypt_key
    self.mode = FeishuMode(mode)
    self.webhook_url = webhook_url
    self.http_host = http_host
    self.http_port = http_port
    self._channel: BaseFeishuChannel | None = None

  async def start(self):
    if self.mode == FeishuMode.WEBSOCKET:
      self._channel = WebSocketFeishuChannel(
        self.on_message,
        self.app_id,
        self.app_secret,
      )
    else:
      self._channel = HttpFeishuChannel(
        self.on_message,
        self.app_id,
        self.app_secret,
        self.verification_token,
        self.encrypt_key,
        self.webhook_url,
        self.http_host,
        self.http_port,
      )

    await self._channel.start()

  async def send(self, message: str, end: str = "\n"):
    if self._channel:
      await self._channel.send(message, end)


class FeishuClient:
  def __init__(self, app_id: str, app_secret: str):
    self.app_id = app_id
    self.app_secret = app_secret
    self._client = None

  def _get_client(self) -> lark.Client:
    if self._client is None:
      base_config = lark.Config(
        app_id=self.app_id,
        app_secret=self.app_secret,
      )
      self._client = lark.Client(base_config)
    return self._client

  def send_message(
    self,
    receive_id: str,
    message: str,
    msg_type: str = "text",
    receive_id_type: str = "open_id",
  ) -> dict:
    client = self._get_client()
    resp = client.im.v1.message.create(
      params=lark.CreateMessageParams(receive_id_type=receive_id_type),
      request=lark.CreateMessageRequest(
        receive_id=receive_id,
        msg_type=msg_type,
        content=lark.JSON.marshal({"text": message}),
      ),
    )
    if resp.code == 0:
      return {"message_id": resp.data.message_id}
    msg = f"Failed to send message: {resp.msg}"
    raise FeishuError(msg)

  def send_message_with_card(
    self,
    receive_id: str,
    card_content: str,
    receive_id_type: str = "open_id",
  ) -> dict:
    client = self._get_client()
    resp = client.im.v1.message.create(
      params=lark.CreateMessageParams(receive_id_type=receive_id_type),
      request=lark.CreateMessageRequest(
        receive_id=receive_id,
        msg_type="interactive",
        content=card_content,
      ),
    )
    if resp.code == 0:
      return {"message_id": resp.data.message_id}
    msg = f"Failed to send card message: {resp.msg}"
    raise FeishuError(msg)


async def send_message(
  app_id: str,
  app_secret: str,
  receive_id: str,
  message: str,
  receive_id_type: str = "open_id",
) -> dict:
  client = FeishuClient(app_id, app_secret)
  return client.send_message(receive_id, message, receive_id_type=receive_id_type)

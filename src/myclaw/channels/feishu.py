import asyncio
import contextvars
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import lark_oapi as lark
from aiohttp import web


_current_sender_id_var = contextvars.ContextVar("current_sender_id", default="")


logger = logging.getLogger(__name__)


@dataclass
class MessageInfo:
  text: str
  sender_id: str
  message_id: str = ""
  chat_id: str = ""


class FeishuMode(str, Enum):
  WEBSOCKET = "websocket"
  HTTP = "http"


class BaseFeishuChannel:
  def __init__(self, on_message: Callable[[MessageInfo], Awaitable[None]]):
    self.on_message = on_message

  async def start(self):
    raise NotImplementedError

  async def send(self, message: str, end: str = "\n"):
    raise NotImplementedError

  async def send_stream(self, stream: AsyncIterator[str]):
    raise NotImplementedError


class WebSocketFeishuChannel(BaseFeishuChannel):
  def __init__(
    self,
    on_message: Callable[[MessageInfo], Awaitable[None]],
    app_id: str,
    app_secret: str,
    log_level: int = logging.INFO,
  ):
    super().__init__(on_message)
    self.app_id = app_id
    self.app_secret = app_secret
    self.log_level = log_level
    self._ws_client = None
    self._pending_task: asyncio.Task | None = None
    self._loop: asyncio.AbstractEventLoop | None = None

  def _do_p2_im_message_receive_v1(self, data: lark.im.v1.P2ImMessageReceiveV1):
    logger.info(f"Received message event: {data}")
    message = data.event.message
    if message and message.message_type == "text":
      content = json.loads(message.content)
      text = content.get("text", "")
      logger.info(f"Received text message: {text}")
      sender_id = ""
      if data.event.sender and data.event.sender.sender_id:
        sender_id = data.event.sender.sender_id.open_id
      message_id = message.message_id if message else ""
      chat_id = message.chat_id if message else ""
      if text:
        msg_info = MessageInfo(
          text=text,
          sender_id=sender_id,
          message_id=message_id,
          chat_id=chat_id,
        )
        if self._loop and self._loop.is_running():
          asyncio.run_coroutine_threadsafe(self.on_message(msg_info), self._loop)
        else:
          logger.warning("Event loop not available, skipping message")

  async def start(self):
    logging.getLogger("lark_oapi").setLevel(self.log_level)
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
    logger.info("Feishu WebSocket client started")

  async def send(self, message: str, end: str = "\n"):
    logger.info(f"WebSocket mode: message would be sent here: {message[:50]}...")

  async def send_stream(self, stream: AsyncIterator[str]):
    logger.info("WebSocket mode: stream would be handled here")


class FeishuError(Exception):
  def __init__(self, message: str):
    self.message = message
    super().__init__(message)


class HttpFeishuChannel(BaseFeishuChannel):
  def __init__(
    self,
    on_message: Callable[[MessageInfo], Awaitable[None]],
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
              sender_id = ""
              sender_info = event_data.get("sender", {})
              sender_id_info = sender_info.get("sender_id", {})
              sender_id = sender_id_info.get("user_id", "")
              message_id = message.get("message_id", "")
              chat_id = message.get("chat_id", "")
              if content:
                try:
                  content_data = json.loads(content)
                  text = content_data.get("text", "")
                  if text:
                    msg_info = MessageInfo(
                      text=text,
                      sender_id=sender_id,
                      message_id=message_id,
                      chat_id=chat_id,
                    )
                    await self.on_message(msg_info)
                except json.JSONDecodeError:
                  msg_info = MessageInfo(
                    text=content,
                    sender_id=sender_id,
                    message_id=message_id,
                    chat_id=chat_id,
                  )
                  await self.on_message(msg_info)
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

  async def send_stream(self, stream: AsyncIterator[str]):
    logger.info("HTTP mode: stream would be handled here")


class FeishuChannel(BaseFeishuChannel):
  def __init__(
    self,
    on_message: Callable[[MessageInfo], Awaitable[None]],
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
    self._current_sender_id: str = ""
    self._feishu_client: FeishuClient | None = None

  def _wrap_on_message(
    self, original_callback: Callable[[MessageInfo], Awaitable[None]]
  ) -> Callable[[MessageInfo], Awaitable[None]]:
    async def wrapper(msg_info: MessageInfo):
      self._current_sender_id = msg_info.sender_id
      token = _current_sender_id_var.set(msg_info.sender_id)
      try:
        await original_callback(msg_info)
      finally:
        _current_sender_id_var.reset(token)

    return wrapper

  async def start(self):
    self._feishu_client = FeishuClient(self.app_id, self.app_secret)
    wrapped_callback = self._wrap_on_message(self.on_message)

    if self.mode == FeishuMode.WEBSOCKET:
      self._channel = WebSocketFeishuChannel(
        wrapped_callback,
        self.app_id,
        self.app_secret,
      )
    else:
      self._channel = HttpFeishuChannel(
        wrapped_callback,
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
    sender_id = _current_sender_id_var.get() or self._current_sender_id
    if self._feishu_client and sender_id:
      try:
        full_message = message + end
        self._feishu_client.send_message(
          receive_id=sender_id,
          message=full_message,
        )
        logger.info(f"Message sent to {sender_id}: {message[:50]}...")
      except FeishuError as e:
        logger.exception(f"Failed to send message: {e.message}")
      except Exception:
        logger.exception("Error sending message")
    else:
      logger.warning("No sender_id available, cannot send message")

  def _build_markdown_card(self, text: str) -> str:
    card = {"elements": [{"tag": "markdown", "content": text}]}
    return json.dumps(card)

  async def send_stream(self, stream: AsyncIterator[str]):
    sender_id = _current_sender_id_var.get() or self._current_sender_id
    if not self._feishu_client or not sender_id:
      logger.warning("Feishu client or sender_id not available, cannot stream message")
      return

    full_message = ""
    message_id = None
    last_update_time = time.time()
    update_interval = 0.5  # seconds

    try:
      async for chunk in stream:
        full_message += chunk
        current_time = time.time()

        # Debounce the updates
        if current_time - last_update_time >= update_interval:
          card_content = self._build_markdown_card(full_message + "▌")
          if message_id is None:
            # First send
            resp = self._feishu_client.send_message_with_card(
              receive_id=sender_id,
              card_content=card_content,
            )
            message_id = resp.get("message_id")
          else:
            # Patch existing message
            self._feishu_client.patch_message_with_card(
              message_id=message_id,
              card_content=card_content,
            )
          last_update_time = current_time

      # Final update without the cursor
      if full_message:
        card_content = self._build_markdown_card(full_message)
        if message_id is None:
          self._feishu_client.send_message_with_card(
            receive_id=sender_id,
            card_content=card_content,
          )
        else:
          self._feishu_client.patch_message_with_card(
            message_id=message_id,
            card_content=card_content,
          )

    except Exception:
      logger.exception("Error during stream sending")


class FeishuClient:
  def __init__(self, app_id: str, app_secret: str):
    self.app_id = app_id
    self.app_secret = app_secret
    self._client = None

  def _get_client(self) -> lark.Client:
    if self._client is None:
      self._client = (
        lark.Client.builder()
        .app_id(self.app_id)
        .app_secret(self.app_secret)
        .log_level(lark.LogLevel.DEBUG)
        .build()
      )
    return self._client

  def send_message(
    self,
    receive_id: str,
    message: str,
    msg_type: str = "text",
    receive_id_type: str = "open_id",
  ) -> dict:
    client = self._get_client()
    request = (
      lark.im.v1.CreateMessageRequest.builder()
      .receive_id_type(receive_id_type)
      .request_body(
        lark.im.v1.CreateMessageRequestBody.builder()
        .receive_id(receive_id)
        .msg_type(msg_type)
        .content(lark.JSON.marshal({"text": message}))
        .build()
      )
      .build()
    )
    resp = client.im.v1.message.create(request)
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
    request = (
      lark.im.v1.CreateMessageRequest.builder()
      .receive_id_type(receive_id_type)
      .request_body(
        lark.im.v1.CreateMessageRequestBody.builder()
        .receive_id(receive_id)
        .msg_type("interactive")
        .content(card_content)
        .build()
      )
      .build()
    )
    resp = client.im.v1.message.create(request)
    if resp.code == 0:
      return {"message_id": resp.data.message_id}
    msg = f"Failed to send card message: {resp.msg}"
    raise FeishuError(msg)

  def patch_message_with_card(
    self,
    message_id: str,
    card_content: str,
  ) -> dict:
    client = self._get_client()
    request = (
      lark.im.v1.PatchMessageRequest.builder()
      .message_id(message_id)
      .request_body(lark.im.v1.PatchMessageRequestBody.builder().content(card_content).build())
      .build()
    )
    resp = client.im.v1.message.patch(request)
    if resp.code == 0:
      return {}
    msg = f"Failed to patch message: {resp.msg}"
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

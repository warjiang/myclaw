import logging
import os

import lark_oapi as lark
from dotenv import load_dotenv


logging.basicConfig(
  level=logging.DEBUG,
  format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def do_p2_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
  logger.debug(
    "[ do_p2_im_message_receive_v1 access ], data: %s",
    lark.JSON.marshal(data, indent=4),
  )


def do_message_event(data: lark.CustomizedEvent) -> None:
  logger.debug(
    "[ do_customized_event access ], type: message, data: %s",
    lark.JSON.marshal(data, indent=4),
  )


event_handler = (
  lark.EventDispatcherHandler.builder("", "")
  .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
  .build()
)


def main():
  load_dotenv()
  cli = lark.ws.Client(
    os.environ.get("FEISHU_APP_ID"),
    os.environ.get("FEISHU_APP_SECRET"),
    event_handler=event_handler,
    log_level=lark.LogLevel.DEBUG,
  )
  cli.start()


if __name__ == "__main__":
  main()

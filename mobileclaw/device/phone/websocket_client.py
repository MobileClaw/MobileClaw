import websocket
import threading
import time
import structlog

logger = structlog.get_logger(__name__)


def default_on_error(ws, error):
    logger.debug(f"WebSocket错误发生: {error}")
    # print(f"WebSocket错误发生: {error}")


# 默认 on_close：打印关闭原因，异常关闭时触发重启
def default_on_close(ws, close_status_code, close_msg):
    reason = f"code={close_status_code}, msg={close_msg}"
    client = getattr(ws, "client_instance", None)
    if close_status_code == 1000:
        logger.debug(f"手机端 WebSocket 连接正常关闭，关闭原因: {reason}")
    else:
        logger.debug(f"手机端 WebSocket 连接异常关闭，尝试重新连接，关闭原因: {reason}")
        # 若不是主动关闭且存在客户端实例，则在后台尝试重启连接（带重试）
        if client and not getattr(client, "_closing", False):
            threading.Thread(
                target=client.restart_with_retry,
                kwargs={"max_retries": 3, "delay_seconds": 2, "timeout_seconds": 10},
                daemon=True,
            ).start()


class WebSocketClient:
    def __init__(self, server_address=None, on_start_message=None, on_error=default_on_error,
                 on_close=default_on_close):
        self.on_start_message = on_start_message
        self.server_address = server_address
        self.response_event = threading.Event()  # 用于同步
        self.is_running = threading.Event()
        self.response_message = None  # 用于存储服务器返回的信息
        # 记录回调，方便重建连接
        self.on_error_handler = on_error
        self.on_close_handler = on_close
        # 主动关闭标记，避免主动关闭后被误重连
        self._closing = False
        # 重连并发保护
        self._reconnecting = False
        self._reconnecting_lock = threading.Lock()
        # 创建 WebSocketApp 与线程
        self._create_ws_app()

    def _create_ws_app(self):
        self.ws = websocket.WebSocketApp(self.server_address,
                                         on_open=self.on_open,
                                         on_message=self.on_message,
                                         on_error=self.on_error_handler,
                                         on_close=self.on_close_handler)
        self.ws.client_instance = self  # 将当前实例传递给 WebSocketApp
        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)

    def on_message(self, ws, message):
        # print(f"收到服务器消息: {message}")
        # 将消息存入 WebSocketClient 实例中
        self.response_message = message
        # 解除阻塞
        self.response_event.set()

    def on_open(self, ws):
        # print("WebSocket连接已打开")
        self.is_running.set()

    def start(self):
        # print(f"连接到服务器: {self.server_address}")
        self.is_running.clear()
        self.thread.start()
        self.is_running.wait()

    def restart(self, delay_seconds: int = 2):
        """在后台用于异常关闭后的重启。"""
        if delay_seconds and delay_seconds > 0:
            time.sleep(delay_seconds)
        if self._closing:
            return
        # 清理运行状态，重建连接与线程
        self.is_running.clear()
        self._create_ws_app()
        self.thread.start()
        # 可选等待，避免阻塞调用线程过久，这里不强制等待
        # self.is_running.wait(timeout=10)

    def restart_with_retry(self, max_retries: int = 3, delay_seconds: int = 2, timeout_seconds: int = 10) -> bool:
        """带重试的重连流程。返回是否成功重连。"""
        if self._closing:
            return False
        with self._reconnecting_lock:
            if self._reconnecting:
                # 已有重连在进行中
                return False
            self._reconnecting = True
        try:
            for attempt_index in range(1, max_retries + 1):
                if self._closing:
                    return False
                logger.debug(f"尝试重新连接 WebSocket（第{attempt_index}/{max_retries}次）...")
                # 重建并启动
                self.is_running.clear()
                self._create_ws_app()
                self.thread.start()
                # 等待连接打开
                if self.is_running.wait(timeout=timeout_seconds):
                    logger.debug("手机端 WebSocket 重新连接成功")
                    return True
                logger.debug(f"第{attempt_index}次重连失败，将在{delay_seconds}秒后重试")
                if delay_seconds > 0:
                    time.sleep(delay_seconds)
            logger.debug("手机端 WebSocket 重连失败，请重启任务")
            logger.debug("手机端重连失败，请尝试重启任务")
            return False
        finally:
            with self._reconnecting_lock:
                self._reconnecting = False

    def send_message(self, message):
        # 发送消息并等待服务器的响应
        # print("重置事件...")
        self.response_event.clear()  # 重置事件
        self.response_message = None  # 清空之前的响应消息
        # print(f"发送消息: {message}")
        self.ws.send(message)
        # print("等待服务器响应...")
        self.response_event.wait()  # 阻塞，直到事件被设置
        # print("收到服务器响应")
        return self.response_message  # 返回服务器的响应

    def close(self):
        self._closing = True
        self.ws.close()


if __name__ == "__main__":
    import PIL.Image
    import base64
    import io
    import json
    # 替换成你的服务器地址
    # server_address = "ws://192.168.20.83:6666"
    server_address = "ws://127.0.0.1:51825"

    # 创建WebSocket客户端实例
    client = WebSocketClient(server_address)

    try:
        # 启动WebSocket连接
        client.start()

        # res = client.send_message("view_hierarchy")
        # print(res)
        
        # res = client.send_message("open_app,Contacts")
        # print(res)
        # input()
        #
        # res = client.send_message("question,你好，请问你是谁？")
        # print(res)
        # input()
        #
        # res = client.send_message("log,你好，我是ruyi")
        # print(res)
        # input()
        #
        # client.send_message("show_highlight,500,500,300")
        # input()
        # client.send_message("hide_highlight")
        # input()
        
        # client.send_message("expand_notification")
        # input()
        
        # client.send_message("set_clipboard,haha")
        # input()
        # res = client.send_message("get_clipboard")
        # print(res)
        # input()
        
        
        
        # 发送命令并等待响应
        # res = client.send_message("click,1000,210")
        # time.sleep(1)
        # res = client.send_message("back")
        # time.sleep(1)
        # res = client.send_message("home")
        # time.sleep(1)
        # res = client.send_message("drag, 500, 500, 1000, 500")
        # time.sleep(1)
        # res = client.send_message("drag, 500, 500, 1000, 500")
        # time.sleep(1)
        # res = client.send_message("drag, 500, 500, 1000, 500")
        # time.sleep(1)
        # res = client.send_message("drag, 500, 500, 1000, 500")
        # time.sleep(1)
        # res = client.send_message("drag, 500, 500, 1000, 500")
        # time.sleep(1)
        # res = client.send_message("click,500, 430")
        # time.sleep(1)
        # res = client.send_message("input,haha")
        # time.sleep(1)
        # res = client.send_message("input,lala")
        # time.sleep(1)
        # res = client.send_message("clear")
        # time.sleep(1)
        # res = client.send_message("screenshot")
        # res = json.loads(res)["data"]
        # res = base64.b64decode(res)

        # img = PIL.Image.open(io.BytesIO(res))
        # img.show()
        # print(f"收到的响应: {res}")
    except Exception as e:
        raise e

from mobileclaw.device.device_base import DeviceControllerBase
import requests
from typing import Optional, Tuple, Any
# from config import config
from PIL import Image
import io
import base64
import urllib.parse
import time
import structlog

logger = structlog.get_logger(__name__)

# Search Engine Configuration
SEARCH_ENGINES = {
    'google': {
        'id': 'google',
        'name': 'Google',
        'searchUrl': 'https://www.google.com/search?q=',
        'homepage': 'https://www.google.com'
    },
    'baidu': {
        'id': 'baidu',
        'name': '百度',
        'searchUrl': 'https://www.baidu.com/s?wd=',
        'homepage': 'https://www.baidu.com'
    },
    'bing': {
        'id': 'bing',
        'name': 'Bing',
        'searchUrl': 'https://www.bing.com/search?q=',
        'homepage': 'https://www.bing.com'
    },
    'sougou': {
        'id': 'sougou',
        'name': '搜狗',
        'searchUrl': 'https://www.sogou.com/web?query=',
        'homepage': 'https://www.sogou.com'
    }
}

def get_search_engine(engine_id: str) -> dict:
    """获取搜索引擎配置"""
    return SEARCH_ENGINES.get(engine_id, SEARCH_ENGINES['baidu'])

def generate_search_url(query: str, engine_id: str = 'baidu') -> str:
    """生成搜索URL"""
    engine = get_search_engine(engine_id)
    return engine['searchUrl'] + urllib.parse.quote(query)

class BrowserDeviceController(DeviceControllerBase):
    def __init__(self, agent, device_name: str = "浏览器1", device_id: str = "browser-001"):
        super().__init__(agent, device_name, device_id)
        self._setup_browser_communication()
        self.device_bound = (0, 0, 0, 0)

    def __str__(self) -> str:
        return f"浏览器设备: {self.device_name}"

    def _setup_browser_communication(self):
        """设置浏览器通信"""
        # 通过 Flask API 与 Electron 通信
        self.api_base_url = f"http://localhost:{self.config.flask_port}"

    def _open(self):
        """打开浏览器设备"""
        self.width, self.height = self.get_width_height()

    def _close_device(self):
        """关闭浏览器设备"""
        try:
            self._send_command("destroy")
        except Exception as e:
            logger.error(f"关闭浏览器设备失败: {e}")

    def take_screenshot_impl(self, save_path: Optional[str] = None) -> Image.Image:
        """截取浏览器视图的截图，返回PIL Image对象"""
        try:
            # 通过 API 获取截图
            response = self._send_command("capturePage")

            # Log if this was a background capture
            if response.get("background_capture"):
                logger.debug("Screenshot captured in background mode")

            # Check if we got a fallback placeholder due to capture failure
            if response.get("fallback_placeholder"):
                logger.debug(f"Screenshot capture failed, using placeholder: {response.get('error', 'Unknown error')}")
                # Return a minimal placeholder image only if capture completely failed
                placeholder = Image.new('RGB', (1, 1), color='white')
                if save_path:
                    placeholder.save(save_path)
                return placeholder

            # Process the actual screenshot data
            screenshot_data_url = response["data"]
            screenshot_data = screenshot_data_url.split(',')[1]
            screenshot_bytes = base64.b64decode(screenshot_data)
            image = Image.open(io.BytesIO(screenshot_bytes))

            if save_path:
                image.save(save_path)
            
            return image

        except Exception as e:
            logger.info(f"❌ 获取浏览器截图失败")
            logger.debug(f"获取浏览器截图失败: {e}")
            # Return placeholder on error to prevent crashes
            placeholder = Image.new('RGB', (1, 1), color='white')
            if save_path:
                placeholder.save(save_path)
            return placeholder

    def key_press(self, key: str):
        """模拟键盘按键"""
        self._send_command("keyPress", {"key": key})

    def enter(self) -> bool:
        """在当前浏览器设备界面按下回车键"""
        self.key_press('Enter')
        return True

    def back(self):
        """模拟返回操作"""
        self._send_command("goBack")

    def home(self):
        """模拟主页操作，返回用户在 IDE 中设定的浏览器默认首页"""
        self._send_command("goHome")

    def open_url(self, url: str) -> bool:
        """打开指定的URL

        Args:
            url: 要打开的URL地址

        Returns:
            bool: 操作是否成功

        Raises:
            RuntimeError: 当URL加载失败时
        """
        if not url:
            raise ValueError("URL cannot be empty")

        # 确保URL有协议前缀
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            result = self._send_command("loadURL", {"url": url})

            if result and result.get("status") == "success":
                # logger.debug(f"成功加载URL: {url}")
                time.sleep(2)
                # Record action for video if recording
                self.record_action_if_recording(
                    "open_url",
                    url=url
                )
                return True
            else:
                error_msg = result.get("message", "Unknown error") if result else "No response from loadURL command"
                logger.error(f"加载 \"{url}\" 失败，错误原因: {error_msg}")
                return False

        except Exception as e:
            logger.error(f"加载 \"{url}\" 失败，错误原因: {str(e)}")
            raise RuntimeError(f"Failed to load URL {url}: {str(e)}")

    def get_url(self) -> str:
        """获取当前页面的URL

        Returns:
            str: 当前页面的URL地址

        Raises:
            RuntimeError: 当获取URL失败时
        """
        try:
            result = self._send_command("getCurrentURL")

            if result and result.get("status") == "success":
                current_url = result.get("url", "")
                # logger.debug(f"[BrowserDevice.get_url] Current URL: {current_url}")
                return current_url
            else:
                error_msg = result.get("message", "Unknown error") if result else "No response from getCurrentURL command"
                logger.debug(f"[BrowserDevice.get_url] Failed to get current URL: {error_msg}")
                # raise RuntimeError(f"Failed to get current URL: {error_msg}")
                raise RuntimeError(f"获取当前浏览器设备的 URL 失败，错误原因: {error_msg}")

        except Exception as e:
            logger.error(f"获取当前浏览器设备的 URL 失败，错误原因: {str(e)}")
            raise RuntimeError(f"Failed to get current URL: {str(e)}")

    def web_search(self, query: str) -> bool:
        """使用配置的默认搜索引擎执行网络搜索

        Args:
            query: 搜索查询词

        Returns:
            bool: 搜索操作是否成功

        Raises:
            ValueError: 当查询词为空时
            RuntimeError: 当搜索失败时
        """
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")

        query = query.strip()
        
        try:
            # 获取当前配置的默认搜索引擎
            search_engine_response = requests.get(f"{self.api_base_url}/get_search_engine_config", timeout=5)
            
            if search_engine_response.status_code == 200:
                search_engine_data = search_engine_response.json()
                search_engine = search_engine_data.get('search_engine', 'baidu')
            else:
                logger.error("获取搜索引擎配置失败，使用默认搜索引擎 (baidu)")
                search_engine = 'baidu'
                
        except Exception as e:
            logger.error(f"获取搜索引擎配置失败，错误原因: {e}, 使用默认搜索引擎 (baidu)")
            search_engine = 'baidu'

        # 生成搜索URL
        search_url = generate_search_url(query, search_engine)
        logger.debug(f"Generated search URL: {search_url} for query: '{query}' using engine: {search_engine}")

        # 使用现有的open_url方法执行搜索
        try:
            # Record action for video if recording
            self.record_action_if_recording(
                "web_search",
                query=query,
                search_engine=search_engine,
                search_url=search_url
            )
            result = self.open_url(search_url)
            if result:
                logger.info(f"🌐 成功执行网络搜索，搜索词: '{query}'")
                return True
            else:
                logger.error(f"执行网络搜索失败，搜索词: '{query}'")
                return False
        except Exception as e:
            logger.error(f"执行网络搜索失败，搜索词: '{query}'，错误原因: {str(e)}")
            raise RuntimeError(f"Failed to execute web search for query '{query}': {str(e)}")

    def long_touch(self, x: int, y: int, duration: Optional[float] = None):
        """模拟长按操作
        Args:
            x: 水平坐标（像素）
            y: 垂直坐标（像素）
            duration: 长按持续时间（毫秒）
        """
        # Record action for video if recording
        self.record_action_if_recording(
            "long_touch",
            coordinates=(x, y),
            duration=duration,
            device_type="browser"
        )
        self._send_command("longTouch", {
            "x": int(x),
            "y": int(y),
            "duration": int(duration) if duration else 1000
        })
        # logger.debug(f"Long touch at ({x}, {y}) for {duration}ms")
        return (x, y)

    def click(self, x: int, y: int):
        """模拟点击操作"""
        # Record action for video if recording
        self.record_action_if_recording(
            "click",
            coordinates=(x, y),
            device_type="browser"
        )
        self._send_command("click", {
            "x": int(x),
            "y": int(y),
            "duration": 200,
        })
        return (x, y)

    def snap_click(self, x: int, y: int, duration: Optional[float] = None):
        """
        坐标吸附点击操作
        根据给定的坐标找到最近的可点击元素并执行点击
        
        Args:
            x: 水平坐标（像素）
            y: 垂直坐标（像素）
            
        Returns:
            Tuple[int, int]: 实际点击（吸附后）的坐标（返回到调用方坐标系，乘以2）
        """
        result = self._send_command("snapClick", {
            "x": int(x),
            "y": int(y),
            "duration": int(duration) if duration else 200
        })
        
        if result.get("status") != "success":
            logger.debug(f"Snap click failed at ({x}, {y}): {result.get('message', 'Unknown error')}")
            raise RuntimeError(f"Failed to perform snap click at ({x}, {y}): {result.get('message', 'Unknown error')}")

        # 提取吸附后的坐标
        snapped_coords = {}
        try:
            snapped_coords = (result.get("result", {}) or {}).get("coordinates", {}) or {}
        except Exception:
            snapped_coords = {}
        
        if isinstance(snapped_coords, dict):
            sx = snapped_coords.get("x")
            sy = snapped_coords.get("y")
            if sx is not None and sy is not None:
                try:
                    return (int(sx), int(sy))
                except Exception:
                    pass
        
        # 兜底返回入参（未能解析吸附后的坐标时）
        return (x, y)

    def long_snap_touch(self, x: int, y: int, duration: Optional[float] = None):
        """
        坐标吸附后，再执行长按操作。（根据给定的坐标找到最近的可长按元素并执行长按）
        TODO: 现在还不够稳定，有时候点击会无效果。
        
        Args:
            x: 水平坐标（像素）
            y: 垂直坐标（像素）
            duration: 长按持续时间（毫秒），默认为1000ms
            
        Returns:
            Tuple[int, int]: 实际长按（吸附后）的坐标（返回到调用方坐标系，乘以2）
        """
        result = self._send_command("longSnapTouch", {
            "x": int(x),
            "y": int(y),
            "duration": int(duration) if duration else 1000
        })
        
        if result.get("status") != "success":
            logger.debug(f"Long snap touch failed at ({x}, {y}): {result.get('message', 'Unknown error')}")
            raise RuntimeError(f"Failed to perform long snap touch at ({x}, {y}): {result.get('message', 'Unknown error')}")
        
        logger.debug(f"Long snap touch successful at ({x}, {y}) for {duration if duration else 1000}ms")
        # 提取吸附后的坐标
        snapped_coords = {}
        try:
            snapped_coords = (result.get("result", {}) or {}).get("coordinates", {}) or {}
        except Exception:
            snapped_coords = {}
        
        if isinstance(snapped_coords, dict):
            sx = snapped_coords.get("x")
            sy = snapped_coords.get("y")
            if sx is not None and sy is not None:
                try:
                    return (int(sx), int(sy))
                except Exception:
                    pass
        
        # 兜底返回入参（未能解析吸附后的坐标时）
        return (x, y)

    def _do_drag(
        self,
        start_xy: Tuple[int, int],
        end_xy: Tuple[int, int],
        duration: Optional[float] = None,
    ):
        """执行拖拽操作
        Args:
            start_xy: 起始坐标 (x, y)
            end_xy: 结束坐标 (x, y)
            duration: 拖拽持续时间（毫秒）
        Returns:
            拖拽操作的结果
        """
        result = self._send_command(
            "drag",
            {
                "startX": int(start_xy[0]),
                "startY": int(start_xy[1]),
                "endX": int(end_xy[0]),
                "endY": int(end_xy[1]),
                "duration": int(duration) if duration else 1000,
            },
        )
        self.agent.sleep(int(duration) / 1000)
        if result.get("status") != "success":
            raise RuntimeError(f"Failed to perform drag: {result.get('message', 'Unknown error')}")
        
        logger.debug(f"Drag from ({start_xy[0]}, {start_xy[1]}) to ({end_xy[0]}, {end_xy[1]}) completed")
        return result

    def scroll(self, *args, **kwargs):
        """执行滚动操作 - 使用浏览器原生滚动
        支持两种调用方式：
        1. scroll(direction, start_xy=None, duration=1000) - 方向版本
        2. scroll(start_xy, end_xy, duration=1000) - 坐标版本

        Args:
            direction 或 start_xy: 方向字符串('up', 'down', 'left', 'right') 或起始坐标元组
            start_xy 或 end_xy: 起始坐标元组 或 结束坐标元组
            duration: 滚动持续时间（毫秒）
        Returns:
            滚动操作的结果
        """
        # 获取屏幕尺寸
        width, height = self.get_width_height()

        if len(args) == 1 and isinstance(args[0], str):
            # 方向版本调用: scroll(direction, start_xy=None, duration=1000)
            direction = args[0]
            start_xy = kwargs.get('start_xy')
            duration = kwargs.get('duration', 1000)

            if start_xy is None:
                # 如果没有指定起始坐标，使用屏幕中心
                start_xy = (width // 2, height // 2)

            # 根据方向计算结束坐标（滑动 1/3 屏幕距离）
            if direction == 'up':
                distance = height // 3
                end_xy = (start_xy[0], start_xy[1] + distance)
            elif direction == 'down':
                distance = height // 3
                end_xy = (start_xy[0], start_xy[1] - distance)
            elif direction == 'left':
                distance = width // 3
                end_xy = (start_xy[0] + distance, start_xy[1])
            elif direction == 'right':
                distance = width // 3
                end_xy = (start_xy[0] - distance, start_xy[1])
            else:
                logger.error(f"不支持的滚动方向: {direction}")
                raise ValueError(f"Unsupported scroll direction: {direction}")

        elif len(args) >= 2:
            # 坐标版本调用: scroll(start_xy, end_xy, duration=1000)
            start_xy = args[0]
            end_xy = args[1]
            duration = args[2] if len(args) > 2 else kwargs.get('duration', 1000)
        else:
            logger.error("scroll 方法调用参数错误")
            raise ValueError("Invalid scroll arguments")

        # 确保坐标在屏幕范围内
        start_xy = (max(0, min(start_xy[0], width - 1)),
                   max(0, min(start_xy[1], height - 1)))
        end_xy = (max(0, min(end_xy[0], width - 1)),
                 max(0, min(end_xy[1], height - 1)))

        start_x, start_y = start_xy
        end_x, end_y = end_xy
        
        # Calculate scroll delta from start and end coordinates
        deltaX = end_x - start_x
        deltaY = end_y - start_y
        
        # Use the center point between start and end as the scroll position
        scroll_x = (start_x + end_x) // 2
        scroll_y = (start_y + end_y) // 2
        
        params = {
            "x": int(scroll_x),
            "y": int(scroll_y),
            "deltaX": deltaX,
            "deltaY": deltaY,
            "duration": duration
        }
        
        result = self._send_command("scroll", params)

        self.agent.sleep(int(duration) / 1000)
        
        if result.get("status") != "success":
            raise RuntimeError(f"Failed to perform scroll: {result.get('message', 'Unknown error')}")
        
        logger.debug(f"Scroll from {start_xy} to {end_xy} over {duration}ms completed")
        return result

    def get_current_state(self):
        """获取当前页面状态"""
        return self._send_command("getPageState")

    def view_set_text(self, text: str, x: int = None, y: int = None):
        """设置输入框文本"""
        params = {"text": text}
        if x is not None and y is not None:
            params["x"] = int(x)
            params["y"] = int(y)
        
        result = self._send_command("setText", params)
        if result.get("status") != "success":
            raise RuntimeError(f"Failed to set text: {result.get('message', 'Unknown error')}")
        return result

    def view_append_text(self, text: str, x: int = None, y: int = None):
        """追加文本到输入框
        Args:
            text: 要追加的文本
            x: 目标输入框的水平坐标（像素，可选）
            y: 目标输入框的垂直坐标（像素，可选）
        Returns:
            追加操作的结果
        """
        params = {"text": text}
        if x is not None and y is not None:
            params["x"] = int(x)
            params["y"] = int(y)
        
        result = self._send_command("appendText", params)
        if result.get("status") != "success":
            raise RuntimeError(f"Failed to append text: {result.get('message', 'Unknown error')}")
        
        logger.debug(f"Appended text '{text}' at ({x or 'current focus'}, {y or 'current focus'})")
        return result

    def check_focus(self):
        """检查当前焦点状态"""
        return self._send_command("checkFocus")

    def shell(self, cmd: str):
        """执行 shell 命令（浏览器设备不支持）"""
        raise NotImplementedError("Browser device does not support shell commands")

    def start_screen_record(self):
        """开始屏幕录制"""
        self._send_command("startRecording")

    def stop_screen_record(self):
        """停止屏幕录制"""
        return self._send_command("stopRecording")

    def hide_highlight(self):
        """隐藏高亮标记"""
        self._send_command("hideHighlight")

    def log(self, message: str) -> bool:
        """记录日志"""
        return self._send_command("log", {"message": message})

    def open_web_browser(self):
        """Opens the web browser."""
        return self.open_url("https://www.baidu.com")


    def go_forward(self):
        """模拟前进操作"""
        self._send_command("goForward")

    def click_at(self, x: int, y: int):
        """在指定坐标点击（兼容 Computer Use API）
        
        Args:
            x: 水平坐标（像素）
            y: 垂直坐标（像素）
            
        Returns:
            Tuple[int, int]: 点击的坐标
        """
        return self.click(x, y)

    def hover_at(self, x: int, y: int):
        """在指定坐标悬停鼠标
        
        Args:
            x: 水平坐标（像素）
            y: 垂直坐标（像素）
            
        Returns:
            Tuple[int, int]: 悬停的坐标
        """
        # Record action for video if recording
        self.record_action_if_recording(
            "hover",
            coordinates=(x, y),
            device_type="browser"
        )
        self._send_command("hover", {
            "x": int(x),
            "y": int(y)
        })
        return (x, y)

    def type_text_at(
        self,
        x: int,
        y: int,
        text: str,
        press_enter: bool = False,
        clear_before_typing: bool = True
    ):
        """在指定坐标位置输入文本
        
        Args:
            x: 水平坐标（像素）
            y: 垂直坐标（像素）
            text: 要输入的文本
            press_enter: 输入后是否按回车键
            clear_before_typing: 输入前是否清空现有文本
            
        Returns:
            dict: 操作结果
        """
        # Record action for video if recording
        self.record_action_if_recording(
            "type_text_at",
            coordinates=(x, y),
            text=text,
            press_enter=press_enter,
            clear_before_typing=clear_before_typing,
            device_type="browser"
        )
        
        # 先点击目标位置以获取焦点
        self.click(x, y)
        time.sleep(0.3)  # 等待焦点切换
        
        # 根据 clear_before_typing 选择设置或追加文本
        if clear_before_typing:
            result = self.view_set_text(text, x, y)
        else:
            result = self.view_append_text(text, x, y)
        
        # 如果需要按回车
        if press_enter:
            time.sleep(0.1)
            self.key_press('Enter')
        
        return result

    def scroll_document(self, direction: str):
        """滚动整个文档
        
        Args:
            direction: 滚动方向 ('up', 'down', 'left', 'right')
            
        Returns:
            dict: 操作结果
        """
        # Record action for video if recording
        self.record_action_if_recording(
            "scroll_document",
            direction=direction,
            device_type="browser"
        )
        
        # 使用屏幕中心点进行滚动
        width, height = self.get_width_height()
        center_x = width // 2
        center_y = height // 2
        
        return self.scroll(direction, start_xy=(center_x, center_y), duration=500)

    def scroll_at(self, x: int, y: int, direction: str, magnitude: int = 800):
        """在指定位置滚动
        
        Args:
            x: 水平坐标（像素）
            y: 垂直坐标（像素）
            direction: 滚动方向 ('up', 'down', 'left', 'right')
            magnitude: 滚动距离（像素）
            
        Returns:
            dict: 操作结果
        """
        # Record action for video if recording
        self.record_action_if_recording(
            "scroll_at",
            coordinates=(x, y),
            direction=direction,
            magnitude=magnitude,
            device_type="browser"
        )
        
        # 根据方向计算滚动的结束坐标
        if direction == 'up':
            end_xy = (x, y + magnitude)
        elif direction == 'down':
            end_xy = (x, y - magnitude)
        elif direction == 'left':
            end_xy = (x + magnitude, y)
        elif direction == 'right':
            end_xy = (x - magnitude, y)
        else:
            raise ValueError(f"Unsupported scroll direction: {direction}")
        
        return self.scroll((x, y), end_xy, duration=500)

    def wait_5_seconds(self):
        """等待5秒钟
        
        Returns:
            bool: 操作完成
        """
        # Record action for video if recording
        self.record_action_if_recording(
            "wait",
            duration=5,
            device_type="browser"
        )
        
        time.sleep(5)
        return True

    def search(self):
        """打开浏览器的搜索功能（Ctrl/Cmd + F）
        
        Returns:
            bool: 操作完成
        """
        # Record action for video if recording
        self.record_action_if_recording(
            "search",
            device_type="browser"
        )
        
        return self.open_url("https://www.baidu.com")

    def navigate(self, url: str):
        """Navigates directly to a specified URL."""
        return self.open_url(url)

    def key_combination(self, keys: list):
        """执行组合键操作
        
        Args:
            keys: 按键列表，如 ['Control', 'c'] 或 ['Meta', 'v']
            
        Returns:
            dict: 操作结果
        """
        # Record action for video if recording
        self.record_action_if_recording(
            "key_combination",
            keys=keys,
            device_type="browser"
        )
        
        result = self._send_command("keyCombination", {"keys": keys})
        if isinstance(result, dict) and result.get("status") == "error":
            raise RuntimeError(f"Failed to execute key combination: {result.get('message', 'Unknown error')}")
        return result

    def drag_and_drop(
        self,
        x: int,
        y: int,
        destination_x: int,
        destination_y: int,
        duration: Optional[float] = None
    ):
        """拖放操作（从起始坐标拖动到目标坐标）
        
        Args:
            x: 起始水平坐标（像素）
            y: 起始垂直坐标（像素）
            destination_x: 目标水平坐标（像素）
            destination_y: 目标垂直坐标（像素）
            duration: 拖拽持续时间（毫秒）
            
        Returns:
            dict: 操作结果
        """
        # Record action for video if recording
        self.record_action_if_recording(
            "drag_and_drop",
            start_coordinates=(x, y),
            end_coordinates=(destination_x, destination_y),
            duration=duration,
            device_type="browser"
        )
        
        return self._do_drag(
            start_xy=(x, y),
            end_xy=(destination_x, destination_y),
            duration=duration or 1000
        )

    def get_clipboard(self) -> str:
        """获取剪贴板内容"""
        result = self._send_command("getClipboard")
        if result.get("status") != "success":
            raise RuntimeError(f"Failed to get clipboard: {result.get('message', 'Unknown error')}")
        return result.get("text", "")

    def set_clipboard(self, text: str) -> bool:
        """设置剪贴板内容"""
        result = self._send_command("setClipboard", {"text": text})
        if result.get("status") != "success":
            raise RuntimeError(f"Failed to set clipboard: {result.get('message', 'Unknown error')}")
        return True

    def get_input_field_text(self) -> str:
        """获取当前聚焦输入框的文本内容"""
        result = self._send_command("getInputFieldText")
        if result.get("status") != "success":
            raise RuntimeError(f"Failed to get input field text: {result.get('message', 'Unknown error')}")
        return result.get("text", "")

    def get_ui_tree(self, mode: str = "full") -> str:
        """获取当前页面的HTML内容

        Args:
            mode: 提取模式
                - "full": 完整的HTML文档 (默认)
                - "body": 仅body标签内容
                - "visible": 仅可见元素
                - "text": 纯文本内容
                - "structured": 结构化的元素树

        Returns:
            str: 根据指定模式返回的HTML内容或结构化数据
        """
        result = self._send_command("getUITree", {"mode": mode})

        if result.get("status") != "success":
            raise RuntimeError(f"Failed to get UI tree: {result.get('message', 'Unknown error')}")

        return result.get("content", "")

    def select(self, selector_or_coords, text: str):
        """从下拉菜单或选择元素中选择一个选项（按文本内容选择）

        Args:
            selector_or_coords: CSS选择器字符串或坐标元组(x, y)
            text: 要选择的选项文本内容（用户可见的文本）

        Returns:
            dict: 包含状态和详细信息的结果

        Raises:
            RuntimeError: 选择操作失败时抛出异常
        """
        if isinstance(selector_or_coords, tuple):
            x, y = selector_or_coords
            params = {
                "x": int(x),
                "y": int(y),
                "text": text
            }
        else:
            params = {
                "selector": selector_or_coords,
                "text": text
            }

        result = self._send_command("select", params)
        if result.get("status") != "success":
            raise RuntimeError(f"Failed to select option: {result.get('message', 'Unknown error')}")

        logger.debug(f"Selected option with text '{text}' successfully")
        return result

    def get_width_height_from_electron(self) -> Tuple[int, int]:
        """
        获取浏览器视图的宽度和高度
        使用 Electron 原生接口获取浏览器视图的宽度和高度（但是这个获取到的宽高相对较小，不知道是什么原因，因此不予使用）
        Returns:
            Tuple[int, int]: (width, height) 浏览器视图的宽度和高度
        """
        bounds = self._send_command("getBounds")
        width = bounds.get('width', 0)
        height = bounds.get('height', 0)
        self.device_bound = (0, 0, width, height)
        return (width, height)

    def get_width_height(self) -> Tuple[int, int]:
        """
        获取浏览器截图得到的实际宽高
        Returns:
            Tuple[int, int]: 电脑的宽度和高度
        """
        if not self.width or not self.height:
            self.width, self.height = self.take_screenshot(hide_overlay=False).size
        return self.width, self.height

    def expand_notification_panel(self):
        """展开通知面板（浏览器设备不支持）"""
        raise NotImplementedError("Browser device does not support notification panel")

    def _do_device_switch(self, device_name: str, device_id: str) -> bool:
        """执行浏览器设备的切换操作 - 只更新内部变量，不切换界面显示"""
        # 更新内部设备变量，不切换界面显示
        old_device_name = self.device_name
        old_device_id = self.device_id
        
        # 更新设备信息
        self.device_name = device_name
        self.device_id = device_id
        
        logger.debug(f"[BrowserDevice] 内部切换浏览器设备: {old_device_name}({old_device_id}) -> {device_name}({device_id})")

    def _send_command(self, command: str, params: Optional[dict] = None) -> Any:
        """发送命令到浏览器视图"""
        # 构建命令消息
        message = {"command": command, "params": params or {}}
        
        # 使用实例变量中的设备ID，确保命令发送到正确的浏览器设备
        message["deviceId"] = self.device_id

        # 通过 Flask API 发送命令到 Electron
        response = requests.post(f"{self.api_base_url}/browser/command", json=message)

        if response.status_code != 200:
            raise RuntimeError(f"Failed to send command: {response.text}")

        # 尝试解析 JSON 响应
        try:
            return response.json()
        except ValueError:
            # 如果不是 JSON 格式，返回原始文本
            return response.text

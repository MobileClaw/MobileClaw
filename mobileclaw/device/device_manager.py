import sys
import structlog
from PIL import Image
from mobileclaw.utils.image_utils import (
    resize_to_height,
    annotate_image_with_top_text,
    horizontally_concat_images,
)
from typing import Dict, Optional, Tuple

from mobileclaw.utils.interface import UniInterface
from mobileclaw.device.browser.browser_device import BrowserDeviceController
from mobileclaw.device.phone.websocket_device import WebsocketController
from mobileclaw.device.computer.mac_device import MacComputerDevice
from mobileclaw.device.computer.windows_device import WindowsComputerDevice


logger = structlog.get_logger(__name__)

class DeviceManager(UniInterface):
    """
    设备管理器：根据设备名称（支持中英文与编号后缀）创建并缓存对应设备实例。

    - 继承自 RuyiInterface，初始化需传入 agent
    - get_device(name): 返回 Browser/Websocket/Mac/Windows 的设备实例
    - 针对设备名称做双语匹配，并从 agent.config.device_mappings 中取 device_id
    - 已创建过的设备会缓存并复用
    """

    def __init__(self, agent):
        super().__init__(agent)
        self._tag = 'device_manager'
        self._device_instances: Dict[str, object] = {}


    def __str__(self) -> str:
        return "设备管理器"

    @staticmethod
    def _normalize_name(name: str) -> str:
        return (name or '').lower().replace('_', ' ').replace('-', ' ').strip()

    @staticmethod
    def _parse_device_name(name: str) -> Tuple[str, str]:
        """
        解析设备名称，返回 (设备类型, 数字后缀)
        例如：'浏览器1' -> ('浏览器', '1'), 'browser' -> ('browser','')
        """
        import re
        n = (name or '').lower().strip()
        m = re.match(r'^(.+?)(\d*)$', n)
        if m:
            device_type = m.group(1).strip()
            number = m.group(2) if m.group(2) else ''
            return device_type, number
        return n, ''

    @staticmethod
    def _canonical_device_type(type_str: str) -> Optional[str]:
        """
        将多语言/多写法的类型映射到标准类型：browser/phone/computer
        返回 None 表示无法识别
        """
        if not type_str:
            return None
        t = type_str.strip().lower()
        # 中文/英文/变体同义映射
        mapping = {
            # 浏览器
            '浏览器': 'browser',
            'browser': 'browser',
            # 手机（含云手机归为 phone）
            '手机': 'phone',
            'phone': 'phone',
            '云手机': 'phone',
            'cloud phone': 'phone',
            'cloudphone': 'phone',
            'cloud_phone': 'phone',
            # 电脑
            '电脑': 'computer',
            'computer': 'computer',
            'pc': 'computer',
            'desktop': 'computer',
        }
        return mapping.get(t)

    def _find_device_with_bilingual_match(self, input_device_name: str, device_mappings: dict) -> Optional[str]:
        """
        双语匹配设备名称（参考 DeviceControllerBase._find_device_with_bilingual_match 的实现思路）
        返回匹配到的配置中的设备名称；未匹配返回 None。
        """
        if not input_device_name:
            return None
        normalized_input = self._normalize_name(input_device_name)

        # 直接命中
        if input_device_name in device_mappings:
            return input_device_name

        # 解析类型与编号
        input_type, input_number = self._parse_device_name(normalized_input)
        candidate_numbers = ['1', ''] if input_number == '' else [input_number]

        for candidate_number in candidate_numbers:
            for config_device_name in device_mappings.keys():
                config_type_raw, config_number = self._parse_device_name(config_device_name)
                # 数字后缀需一致
                if (config_number or '') != (candidate_number or ''):
                    continue
                # 类型同义匹配（先直接比对原词）
                if input_type == config_type_raw:
                    return config_device_name
                # 再用规范化类型映射比较
                input_canon = self._canonical_device_type(input_type)
                config_canon = self._canonical_device_type(config_type_raw)
                if input_canon and config_canon and input_canon == config_canon:
                    return config_device_name
        return None

    def _infer_device_type_from_name(self, device_name: str) -> Optional[str]:
        device_type_raw, _ = self._parse_device_name(device_name)
        return self._canonical_device_type(device_type_raw)

    @staticmethod
    def _pick_computer_device_class():
        if sys.platform == 'darwin':
            return MacComputerDevice
        if sys.platform.startswith('win'):
            return WindowsComputerDevice

        logger.info(f"⚠️ 当前类型的电脑系统尚未适配，执行时可能报错: {sys.platform}")
        logger.debug(f"⚠️ 当前使用的电脑系统为: {sys.platform}")
        return MacComputerDevice

    def get_device(self, device_name: str):
        """
        根据传入的设备名称（支持中英文）返回对应设备实例：
        - 浏览器 -> BrowserDeviceController
        - 手机/云手机 -> WebsocketController
        - 电脑 -> MacComputerDevice / WindowsComputerDevice（按平台）

        已创建过的设备（按匹配后的配置名）将从缓存中直接返回。
        """
        try:
            # 前置校验配置
            config = self.agent.config

            # 双语匹配配置中的设备名
            matched_device_name = self._find_device_with_bilingual_match(device_name, config.device_mappings)
            # TODO: 没找到的时候，使用设备列表中的第一个设备来执行任务；或者调用 LLM 来分析一个最可能的设备名
            if matched_device_name is None:
                available = list(config.device_mappings.keys())
                raise ValueError(
                    f"设备 '{device_name}' 未在配置中找到. "
                    f"可用的设备: {available}. "
                    f"支持双语匹配: 浏览器/browser, 手机/phone, 云手机/cloud phone, 电脑/computer"
                )

            # 命中缓存直接返回
            if matched_device_name in self._device_instances:
                return self._device_instances[matched_device_name]

            # 取设备 ID 并推断类型
            device_id = config.device_mappings[matched_device_name]
            canonical_type = self._infer_device_type_from_name(matched_device_name)

            # 按类型构造实例
            if canonical_type == 'browser':
                instance = BrowserDeviceController(self.agent, matched_device_name, device_id)
            elif canonical_type == 'phone':
                instance = WebsocketController(self.agent, matched_device_name, device_id)
            elif canonical_type == 'computer':
                DeviceCls = self._pick_computer_device_class()
                instance = DeviceCls(self.agent, matched_device_name, device_id)

            # 缓存并返回
            self._device_instances[matched_device_name] = instance
            
            instance._open()

            logger.info(f"✅ 将使用: \"{device_name}\" 执行任务")
            # self.agent.user._notify_with_template('set_device', device_name)
            return instance
        except Exception as e:
            logger.error(f"❌ 设置执行设备为 \"{device_name}\" 失败")
            # self.agent.user._notify_with_template('error', device_name)
            logger.debug(f"❌ 设置执行设备为 \"{device_name}\" 失败: {e}")
            raise 

    def get_first_device(self):
        if len(self._device_instances) == 0:
            return None
        return self._device_instances[list(self._device_instances.keys())[0]]

    def get_available_devices(self):
        """
        Get a list of available devices with descriptions.

        Returns:
            list: List of (name, description) tuples for each configured device
        """
        devices = []
        config = self.agent.config

        if not hasattr(config, 'device_mappings') or not config.device_mappings:
            return devices

        for device_name, device_id in config.device_mappings.items():
            # Infer device type from name
            canonical_type = self._infer_device_type_from_name(device_name)

            # Create description based on type
            if canonical_type == 'browser':
                description = f"Browser"
            elif canonical_type == 'phone':
                description = f"Phone"
            elif canonical_type == 'computer':
                description = f"Computer"
            else:
                description = f"Undefined Device"

            devices.append((device_name, description))

        return devices

    def get_all_browser_urls(self) -> str:
        """
        获取当前缓存的所有浏览器设备的 URL，并按行拼接返回。
        """

        browser_entries: list[str] = []
        for device_name, instance in self._device_instances.items():
            if isinstance(instance, BrowserDeviceController):
                try:
                    current_url = instance.get_url()
                except Exception as exc:
                    logger.debug(f"获取浏览器设备 '{device_name}' 的 URL 失败: {exc}")
                    current_url = ""
                if current_url:
                    browser_entries.append(f"{device_name}：{current_url}")

        return "\n".join(browser_entries)


    def compose_all_devices_screenshots(self) -> Image.Image:
        """
        获取当前已创建并缓存的所有设备截图：
        - 统一缩放到相同高度（使用最小高度）
        - 为每张图的上方添加设备名称文字条
        - 将所有图片横向拼接并返回
        """
        if not self._device_instances:
            return None

        screenshots: list[tuple[str, Image.Image]] = []
        for device_name, instance in self._device_instances.items():
            try:
                img = instance.take_screenshot()
                if isinstance(img, Image.Image):
                    screenshots.append((device_name, img.convert("RGB")))
                else:
                    logger.debug(f"设备 '{device_name}' 截图结果无效，已跳过")
            except Exception as e:
                logger.debug(f"获取设备 '{device_name}' 截图失败: {e}")

        if not screenshots:
            return None

        min_h = min(img.height for _, img in screenshots)

        processed_images: list[Image.Image] = []
        for device_name, img in screenshots:
            try:
                resized = resize_to_height(img, min_h)
                annotated = annotate_image_with_top_text(resized, device_name)
                processed_images.append(annotated)
            except Exception as e:
                logger.debug(f"处理设备 '{device_name}' 截图失败: {e}")

        if not processed_images:
            return None

        return horizontally_concat_images(processed_images, gap=20)

    def get_phone1_screenshot(self) -> Image.Image:
        return self.get_device('phone1').take_screenshot()
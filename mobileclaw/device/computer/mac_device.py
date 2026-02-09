from .base import ComputerDeviceBase
from typing import Tuple, Optional, List, Dict
import time
import structlog

logger = structlog.get_logger(__name__)

try:
    from pynput.mouse import Controller as Mouse, Button
    from pynput.keyboard import Controller as Keyboard, Key
    import mss
    import pyperclip
    import AppKit
    import Quartz
    # 新增：用于短暂刷新事件循环，确保绘制
    from Foundation import NSRunLoop, NSDate
    # 用于检查辅助功能权限
    from ApplicationServices import AXIsProcessTrusted
except Exception:
    Mouse = None  # type: ignore
    Keyboard = None  # type: ignore
    Button = None  # type: ignore
    mss = None  # type: ignore
    pyperclip = None  # type: ignore
    AppKit = None  # type: ignore
    Quartz = None  # type: ignore
    NSRunLoop = None  # type: ignore
    NSDate = None  # type: ignore
    AXIsProcessTrusted = None  # type: ignore

from PIL import Image
import subprocess
import requests
import io
import base64
import tempfile
import sys
import os

# 在模块级定义绘制视图类，避免多次在运行时重复注册同名 ObjC 类导致后续 drawRect_ 不触发
if 'AppKit' in globals() and AppKit is not None:
    class CircleOverlayView(AppKit.NSView):
        def isFlipped(self):
            return True

        def drawRect_(self, r):
            try:
                # 清透明背景（容错处理）
                AppKit.NSColor.clearColor().set()
                AppKit.NSBezierPath.fillRect_(self.bounds())
            except Exception:
                pass
            line_width = 3.0
            bounds = self.bounds()
            inset_rect = AppKit.NSInsetRect(bounds, line_width / 2.0, line_width / 2.0)
            # 先填充浅红色
            fill_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.0, 0.0, 0.2)
            fill_color.set()
            fill_path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(inset_rect)
            fill_path.fill()
            # 再用较深红色描边
            stroke_color = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.0, 0.0, 0.8)
            stroke_color.set()
            stroke_path = AppKit.NSBezierPath.bezierPathWithOvalInRect_(inset_rect)
            stroke_path.setLineWidth_(line_width)
            stroke_path.stroke()
else:
    CircleOverlayView = None  # type: ignore

class MacComputerDevice(ComputerDeviceBase):
    def __init__(self, agent, device_name: str, device_id: str):
        super().__init__(agent, device_name, device_id)
        self.mouse = Mouse() if Mouse else None
        self.keyboard = Keyboard() if Keyboard else None
        # 高亮窗口引用（支持多个高亮）
        self._highlight_windows = []
        # 坐标缩放因子（初始化时计算一次）
        self._coordinate_scale_factor = self._calculate_coordinate_scale_factor()

    def _open(self):
        """打开电脑设备"""
        self.width, self.height = self.get_width_height()

    def _ensure_nsapp(self):
        try:
            if AppKit is None:
                return False
            app = AppKit.NSApp
            if app is None:
                app = AppKit.NSApplication.sharedApplication()
            # 使用 accessory 模式，避免 Dock 图标与切换焦点，但可显示窗口
            try:
                app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _check_accessibility_permission(self) -> bool:
        """
        检查是否有辅助功能权限。
        在 macOS 上，发送鼠标和键盘事件需要辅助功能权限。
        
        Returns:
            bool: 是否有辅助功能权限
        """
        try:
            if AXIsProcessTrusted is not None:
                trusted = AXIsProcessTrusted()
                if not trusted:
                    # 获取当前进程信息，帮助用户确定需要授权的应用
                    process_info = self._get_process_info_for_accessibility()
                    logger.warning(
                        f"❌ macOS 辅助功能权限未授予！\n"
                        f"   请在 系统设置 -> 隐私与安全性 -> 辅助功能 中添加以下应用：\n"
                        f"   {process_info}\n"
                        f"\n"
                        f"   💡 推荐解决方案（如果无法添加 Python）：\n"
                        f"   添加终端应用到辅助功能权限中，所有通过该终端启动的程序都会继承权限：\n"
                        f"   • 如果使用 Terminal.app：添加 /System/Applications/Utilities/Terminal.app\n"
                        f"   • 如果使用 iTerm：添加 /Applications/iTerm.app\n"
                        f"   • 如果使用 VS Code 终端：添加 /Applications/Visual Studio Code.app\n"
                        f"   • 如果使用 Cursor 终端：添加 /Applications/Cursor.app\n"
                        f"   添加后请重启终端/应用，然后重新运行程序（建议优先使用终端进行启动）。"
                    )
                return trusted
            else:
                # 如果无法导入 AXIsProcessTrusted，假设有权限（让后续操作尝试）
                logger.debug("无法检查辅助功能权限（AXIsProcessTrusted 不可用）")
                return True
        except Exception as e:
            logger.debug(f"检查辅助功能权限时出错: {e}")
            return True  # 假设有权限，让后续操作尝试

    def _get_process_info_for_accessibility(self) -> str:
        """
        获取当前进程信息，帮助用户确定需要为哪个应用授予辅助功能权限。
        
        Returns:
            str: 进程信息字符串
        """
        try:
            import psutil
            
            current_process = psutil.Process()
            current_exe = current_process.exe()
            current_name = current_process.name()
            
            # 尝试获取父进程信息（可能是 Electron/Node）
            parent_info = ""
            try:
                parent = current_process.parent()
                if parent:
                    parent_name = parent.name()
                    parent_exe = parent.exe()
                    
                    # 检查是否是 Electron 应用
                    if 'Electron' in parent_exe or 'node' in parent_name.lower():
                        # 尝试找到 Electron 应用的 .app 包
                        app_path = self._find_electron_app_path(parent_exe)
                        if app_path:
                            parent_info = f"\n   或者添加 Electron 应用: {app_path}"
                        else:
                            parent_info = f"\n   父进程: {parent_name} ({parent_exe})"
            except Exception:
                pass
            
            # 检查当前进程是否是 Python
            if 'python' in current_name.lower():
                # 获取 Python 解释器路径，并解析符号链接获取真实路径
                python_path = sys.executable
                real_python_path = os.path.realpath(python_path)
                
                # 如果是符号链接，显示真实路径
                if python_path != real_python_path:
                    return (
                        f"Python 解释器（符号链接）: {python_path}\n"
                        f"   ⚠️  注意：上述路径是符号链接（替身），macOS 不接受符号链接！\n"
                        f"   ✅ 请添加真实路径: {real_python_path}{parent_info}"
                    )
                else:
                    return f"Python 解释器: {python_path}{parent_info}"
            else:
                return f"应用: {current_name} ({current_exe}){parent_info}"
                
        except ImportError:
            # psutil 不可用，使用基本方法
            python_path = sys.executable
            real_python_path = os.path.realpath(python_path)
            if python_path != real_python_path:
                return (
                    f"Python 解释器（符号链接）: {python_path}\n"
                    f"   ⚠️  注意：上述路径是符号链接（替身），macOS 不接受符号链接！\n"
                    f"   ✅ 请添加真实路径: {real_python_path}"
                )
            return f"Python 解释器: {python_path}"
        except Exception as e:
            python_path = sys.executable
            real_python_path = os.path.realpath(python_path)
            if python_path != real_python_path:
                return (
                    f"Python 解释器（符号链接）: {python_path}\n"
                    f"   ⚠️  注意：上述路径是符号链接（替身），macOS 不接受符号链接！\n"
                    f"   ✅ 请添加真实路径: {real_python_path}"
                )
            return f"Python 解释器: {python_path} (获取详细信息失败: {e})"

    def _find_electron_app_path(self, exe_path: str) -> Optional[str]:
        """
        从可执行文件路径查找 Electron 应用的 .app 包路径。
        
        Args:
            exe_path: 可执行文件路径
            
        Returns:
            Optional[str]: .app 包路径，如果找不到则返回 None
        """
        try:
            # 在 macOS 上，Electron 应用的可执行文件通常在 .app/Contents/MacOS/ 目录下
            # 例如: /Applications/MyApp.app/Contents/MacOS/MyApp
            path_parts = exe_path.split('/')
            for i, part in enumerate(path_parts):
                if part.endswith('.app'):
                    # 找到 .app 包，返回完整路径
                    return '/'.join(path_parts[:i+1])
            return None
        except Exception:
            return None

    def _calculate_coordinate_scale_factor(self) -> float:
        """
        计算坐标缩放因子，用于将截图坐标转换为系统逻辑坐标。
        
        截图使用 screencapture 命令获取的是物理像素分辨率，
        而系统坐标使用的是逻辑分辨率，在 Retina 显示屏上两者不一致。
        """
        try:
            # 获取逻辑屏幕尺寸
            logical_width, logical_height = self.get_system_width_height()
            if logical_width <= 0 or logical_height <= 0:
                logger.warning("获取逻辑屏幕尺寸失败，使用默认缩放因子 1.0")
                return 1.0
            
            # 使用现有的截图方法获取截图
            screenshot = self.take_screenshot(hide_overlay=False)
            screenshot_width, screenshot_height = screenshot.size
            
            # 计算缩放因子（截图尺寸 / 逻辑尺寸）
            width_scale = screenshot_width / logical_width
            height_scale = screenshot_height / logical_height
            
            # 使用平均缩放因子，通常在 Retina 显示屏上应该接近 2.0
            scale_factor = (width_scale + height_scale) / 2.0
            
            # 合理性检查
            if scale_factor < 0.5 or scale_factor > 4.0:
                logger.warning(f"计算出的坐标缩放因子 {scale_factor:.2f} 异常，使用默认值 1.0")
                return 1.0
            else:
                logger.debug(f"坐标缩放因子: {scale_factor:.2f} (截图: {screenshot_width}x{screenshot_height}, 逻辑: {logical_width}x{logical_height})")
            
            return scale_factor
            
        except Exception as e:
            logger.warning(f"计算坐标缩放因子失败: {e}，使用默认值 1.0")
            return 1.0
    
    def _transform_coordinate(self, x: int, y: int) -> tuple[int, int]:
        """
        将截图坐标转换为系统逻辑坐标。
        
        Args:
            x, y: 基于截图的坐标
            
        Returns:
            转换后的系统逻辑坐标
        """
        if self._coordinate_scale_factor == 1.0:
            return int(x), int(y)
        
        # 将截图坐标缩放到逻辑坐标
        logical_x = int(x / self._coordinate_scale_factor)
        logical_y = int(y / self._coordinate_scale_factor)
        
        return logical_x, logical_y

    def recalculate_coordinate_scale_factor(self) -> float:
        """
        重新计算坐标缩放因子，用于显示器设置发生变化时更新缩放因子。
        
        Returns:
            新的坐标缩放因子
        """
        self._coordinate_scale_factor = self._calculate_coordinate_scale_factor()
        logger.info(f"重新计算坐标缩放因子: {self._coordinate_scale_factor:.2f}")
        return self._coordinate_scale_factor

    def _get_all_installed_apps(self) -> list[dict]:
        """
        Get all installed applications on macOS.
        
        Returns:
            list[dict]: List of installed apps with keys: name, path, bundle_id
        """
        installed_apps = []
        
        # Common application directories
        app_dirs = [
            '/Applications',
            '/System/Applications',
            os.path.expanduser('~/Applications'),
        ]
        
        for app_dir in app_dirs:
            if not os.path.exists(app_dir):
                continue
            try:
                for item in os.listdir(app_dir):
                    if item.endswith('.app'):
                        app_path = os.path.join(app_dir, item)
                        app_name = item.replace('.app', '')
                        bundle_id = ''
                        
                        # Try to get bundle ID from Info.plist
                        info_plist_path = os.path.join(app_path, "Contents", "Info.plist")
                        if os.path.exists(info_plist_path):
                            try:
                                import plistlib
                                with open(info_plist_path, 'rb') as f:
                                    plist_data = plistlib.load(f)
                                bundle_id = plist_data.get("CFBundleIdentifier", "")
                                # Also get display name if available
                                display_name = plist_data.get("CFBundleDisplayName", "") or plist_data.get("CFBundleName", "")
                                if display_name:
                                    app_name = display_name
                            except Exception:
                                pass
                        
                        installed_apps.append({
                            "name": app_name,
                            "path": app_path,
                            "bundle_id": bundle_id
                        })
            except Exception as e:
                logger.debug(f"Error scanning {app_dir}: {e}")

        return installed_apps

    def _find_app_with_llm(self, app_name: str, installed_apps: list[dict]) -> Optional[str]:
        """
        Use LLM to find the best matching app when direct matching fails.
        
        Args:
            app_name: The user-provided app name
            installed_apps: List of installed apps from _get_all_installed_apps
            
        Returns:
            Optional[str]: The path to the matched app, or None if not found
        """
        try:
            import json
            prompt = f"""You are an expert macOS application developer. The user wants to launch an application by name, but the exact name doesn't match any installed application. Your task is to find the best matching application.

User requested app name: "{app_name}"

List of installed applications on this Mac (name, path, bundle_id):
```
{json.dumps(installed_apps, indent=2, ensure_ascii=False)}
```

Instructions:
1. Analyze the user's requested app name and find the best matching application from the installed apps list.
2. Consider common abbreviations, alternative names, and partial matches:
   - "Chrome" should match "Google Chrome"
   - "VS Code" or "VSCode" should match "Visual Studio Code"
   - "Word" should match "Microsoft Word"
   - Partial names like "Photoshop" should match "Adobe Photoshop"
3. If you find a matching app, return the exact path to the .app bundle.
4. If no reasonable match is found, return an empty string "".

Note: Be conservative - only return a match if you're confident the user meant that application. Consider both the display name and bundle_id when matching.
"""
            # Call fm.query to get the best matching app path
            result = self.agent.fm.call_func(
                'query_model_formatted',
                params={'query': prompt, 'returns': [("app_path", str)]},
            )
            
            if result and isinstance(result, str) and result.strip():
                matched_path = result.strip()
                # Verify the path exists and is a valid .app bundle
                if os.path.exists(matched_path) and matched_path.endswith('.app'):
                    return matched_path
                # Also check if it might be just the app name without path
                for app in installed_apps:
                    if app['name'].lower() == matched_path.lower() or app['path'] == matched_path:
                        return app['path']
            
            return None
        except Exception as e:
            logger.debug(f"LLM app matching failed: {e}")
            return None

    def _start_app_by_path(self, app_path: str, app_name: str) -> bool:
        """
        Start an app by its path.
        
        Args:
            app_path: Full path to the .app bundle
            app_name: Original app name for logging
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            launch_result = subprocess.run(
                ["open", "-a", app_path],
                capture_output=True,
                text=True,
                check=False
            )
            
            if launch_result.returncode == 0:
                time.sleep(0.5)
                logger.info(f"✅ 成功启动应用程序 \"{app_name}\"")
                self._notify_app_started(app_name)
                return True
            return False
        except Exception as e:
            logger.debug(f"Failed to start app by path: {e}")
            return False

    def start_app(self, app_name: str) -> bool:
        try:
            # 使用 mdfind 通过显示名称查找应用
            result = subprocess.run(
                ["mdfind", f'kMDItemDisplayName == "{app_name}"'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            app_found_directly = result.returncode == 0 and result.stdout.strip()
            target_path = None
            
            if app_found_directly:
                # 解析搜索结果，查找 .app 包
                lines = result.stdout.strip().split('\n')
                app_paths = [line.strip() for line in lines if line.strip().endswith('.app')]
                
                if app_paths:
                    # 如果有多个路径，优先选择 /Applications/ 开头的
                    for path in app_paths:
                        if path.startswith('/Applications/'):
                            target_path = path
                            break
                    
                    # 如果没有 /Applications/ 开头的，使用第一个
                    if target_path is None:
                        target_path = app_paths[0]
            
            # If direct matching failed, try using LLM to find the app
            if target_path is None:
                logger.info(f"🔁 未能直接在 Mac 上找到 \"{app_name}\" 应用，正在智能分析本地应用信息...")
                
                # Get all installed apps
                installed_apps = self._get_all_installed_apps()
                
                if installed_apps:
                    # Use LLM to find the best match
                    matched_path = self._find_app_with_llm(app_name, installed_apps)
                    
                    if matched_path:
                        target_path = matched_path
                    else:
                        logger.error(f"❌ 未找到与 \"{app_name}\" 匹配的应用程序")
                        return False
                else:
                    logger.error(f"❌ 未在本机找到任何已安装的应用程序")
                    return False
            
            logger.debug(f"✅ 找到应用路径: {target_path}")
            
            # 使用找到的路径启动应用
            if self._start_app_by_path(target_path, app_name):
                return True
            
            # 如果 open 命令失败，尝试使用 AppleScript 作为备选方案
            logger.debug(f"open 命令启动 {app_name} 失败，尝试使用 AppleScript")
            try:
                # Extract the app name from path for AppleScript
                script_app_name = os.path.basename(target_path).replace('.app', '')
                applescript_result = subprocess.run(
                    ["osascript", "-e", f'tell application "{script_app_name}" to activate'],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if applescript_result.returncode == 0:
                    time.sleep(0.5)
                    logger.info(f"✅ 成功启动应用程序 \"{app_name}\"")
                    self._notify_app_started(app_name)
                    return True
                else:
                    logger.error(f"❌ 启动应用程序 \"{app_name}\" 失败")
                    return False
            except Exception:
                logger.error(f"❌ 启动应用程序 \"{app_name}\" 失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 启动应用程序 \"{app_name}\" 失败: {e}")
            return False

    def kill_app(self, app_name: str) -> bool:
        try:
            subprocess.run(["pkill", "-x", app_name], check=False)
            return True
        except Exception:
            return False
    
    def _get_app_info(self, app_name: str, **kwargs) -> dict:
        """获取MAC应用信息
        
        Args:
            app_name: 应用名称
            **kwargs: 可选参数
            
        Returns:
            dict: 应用信息字典
        """
        app_info = {
            "bundle_id": "",
            "category": "",
            "developer": "",
            "description": "",
            "display_name": "",
            "icon": "",
            "name": app_name,
            "type": 1,  # 电脑端固定为1
            "version": ""
        }
        
        try:
            # 使用 mdfind 查找应用路径
            result = subprocess.run(
                ["mdfind", f'kMDItemDisplayName == "{app_name}"'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                app_paths = [line.strip() for line in lines if line.strip().endswith('.app')]
                
                if app_paths:
                    # 优先选择 /Applications/ 开头的
                    app_path = None
                    for path in app_paths:
                        if path.startswith('/Applications/'):
                            app_path = path
                            break
                    if app_path is None:
                        app_path = app_paths[0]
                    
                    # 读取 Info.plist 获取详细信息
                    info_plist_path = os.path.join(app_path, "Contents", "Info.plist")
                    if os.path.exists(info_plist_path):
                        try:
                            import plistlib
                            with open(info_plist_path, 'rb') as f:
                                plist_data = plistlib.load(f)
                            
                            # 提取信息
                            app_info["bundle_id"] = plist_data.get("CFBundleIdentifier", "")
                            app_info["version"] = plist_data.get("CFBundleShortVersionString", "") or plist_data.get("CFBundleVersion", "")
                            app_info["display_name"] = plist_data.get("CFBundleDisplayName", "") or plist_data.get("CFBundleName", "") or app_name
                            app_info["category"] = plist_data.get("LSApplicationCategoryType", "")
                            
                            # 尝试获取描述信息
                            description = plist_data.get("CFBundleGetInfoString", "") or plist_data.get("NSHumanReadableCopyright", "")
                            app_info["description"] = description
                            
                            # 从代码签名获取开发者信息
                            try:
                                sign_result = subprocess.run(
                                    ["codesign", "-dvv", app_path],
                                    capture_output=True,
                                    text=True,
                                    timeout=3
                                )
                                sign_output = sign_result.stderr  # codesign 输出到 stderr
                                
                                # 尝试提取 Authority (签名证书)
                                for line in sign_output.split('\n'):
                                    if 'Authority=' in line and 'Authority=(unavailable)' not in line:
                                        authority = line.split('Authority=', 1)[1].strip()
                                        if authority:
                                            app_info["developer"] = authority
                                            break
                                
                                # 如果没有找到 Authority，使用 TeamIdentifier
                                if not app_info["developer"]:
                                    for line in sign_output.split('\n'):
                                        if 'TeamIdentifier=' in line:
                                            team_id = line.split('TeamIdentifier=', 1)[1].strip()
                                            if team_id:
                                                app_info["developer"] = f"Team ID: {team_id}"
                                            break
                            except Exception as e:
                                logger.debug(f"获取代码签名信息失败: {str(e)}")
                            
                            # 提取图标并转换为 base64
                            try:
                                icon_file = plist_data.get("CFBundleIconFile", "")
                                if icon_file:
                                    # 确保文件名包含扩展名
                                    if not icon_file.endswith('.icns'):
                                        icon_file += '.icns'
                                    
                                    icon_path = os.path.join(app_path, "Contents", "Resources", icon_file)
                                    if os.path.exists(icon_path):
                                        # 使用 sips 工具将 icns 转换为 png
                                        temp_png = tempfile.mktemp(suffix=".png")
                                        sips_result = subprocess.run(
                                            ["sips", "-s", "format", "png", "-Z", "128", icon_path, "--out", temp_png],
                                            capture_output=True,
                                            text=True,
                                            timeout=5
                                        )
                                        
                                        if sips_result.returncode == 0 and os.path.exists(temp_png):
                                            # 读取 PNG 文件并转换为 base64
                                            with open(temp_png, 'rb') as icon_file_obj:
                                                icon_bytes = icon_file_obj.read()
                                                icon_base64 = base64.b64encode(icon_bytes).decode('utf-8')
                                                app_info["icon"] = f"data:image/png;base64,{icon_base64}"
                                            
                                            # 清理临时文件
                                            try:
                                                os.remove(temp_png)
                                            except Exception:
                                                pass
                            except Exception as e:
                                logger.debug(f"提取图标失败: {str(e)}")
                            
                        except Exception as e:
                            logger.debug(f"读取 Info.plist 失败: {str(e)}")
                            
        except Exception as e:
            logger.debug(f"获取MAC应用信息失败: {str(e)}")
        
        return app_info

    def click(self, x: int, y: int, duration: int = 1000):
        if not self.mouse and Quartz is None:
            raise RuntimeError("pynput not available")
        
        # 检查辅助功能权限
        self._check_accessibility_permission()
        
        # 将截图坐标转换为系统逻辑坐标
        logical_x, logical_y = self._transform_coordinate(x, y)
        logger.debug(f"click: 原始坐标 ({x}, {y}) -> 逻辑坐标 ({logical_x}, {logical_y})")
        
        # 点击前高亮 - 先移动到位置再显示高亮
        self.mouse.position = (logical_x, logical_y)
        try:
            self.show_highlight(x, y, radius=24)
            # 短暂延迟确保高亮显示完成
            time.sleep(0.05)
        except Exception as e:
            logger.debug(f"click: show_highlight 失败: {e}")
        
        # 开启悬浮窗穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception as e:
            logger.debug(f"click: overlay_clickthrough_on 失败: {e}")
        
        try:
            # 使用转换后的逻辑坐标进行点击
            self.mouse.position = (logical_x, logical_y)
            self.mouse.click(Button.left, 1)
            if duration:
                time.sleep(duration / 1000.0)
        except Exception as e:
            logger.error(f"❌ 在电脑中执行点击操作失败: {e}")
        finally:
            # 关闭穿透
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass
        # 点击后隐藏高亮
        try:
            self.hide_highlight()
        except Exception:
            pass
            
        if duration:
            time.sleep(duration / 1000.0)
            
        # 返回转换前的坐标，便于和截图对应
        return (x, y)

    def right_click(self, x: int, y: int, duration: int = 200):
        if not self.mouse and Quartz is None:
            raise RuntimeError("pynput not available")
            
        # 将截图坐标转换为系统逻辑坐标
        logical_x, logical_y = self._transform_coordinate(x, y)
            
        # 先移动到目标位置再显示高亮
        try:
            if Quartz is not None:
                move_event = Quartz.CGEventCreateMouseEvent(
                    None,
                    Quartz.kCGEventMouseMoved,
                    (int(logical_x), int(logical_y)),
                    Quartz.kCGMouseButtonRight,
                )
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, move_event)
            elif self.mouse is not None:
                self.mouse.position = (logical_x, logical_y)
            time.sleep(0.02)
        except Exception:
            pass
        
        # 开启悬浮窗穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass
        
        try:
            if Quartz is not None:
                # 使用 Quartz 右击
                right_down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseDown, (int(logical_x), int(logical_y)), Quartz.kCGMouseButtonRight)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, right_down)
                time.sleep(0.01)
                right_up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventRightMouseUp, (int(logical_x), int(logical_y)), Quartz.kCGMouseButtonRight)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, right_up)
            elif self.mouse is not None:
                self.mouse.click(Button.right, 1)
            if duration:
                time.sleep(duration / 1000.0)
        finally:
            # 关闭穿透
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass
        
        # 点击后隐藏高亮
        try:
            self.hide_highlight()
        except Exception:
            pass
        return (x, y)

    def double_click(self, x: int, y: int, interval_ms: int = 50):
        if not self.mouse and Quartz is None:
            raise RuntimeError("pynput not available")
        
        logical_x, logical_y = self._transform_coordinate(x, y)
        try:
            self.show_highlight(x, y, radius=24)
        except Exception:
            pass
        
        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass
        
        try:
            if Quartz is not None:
                # 两次左键点击（Quartz）
                down1 = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (int(logical_x), int(logical_y)), Quartz.kCGMouseButtonLeft)
                up1 = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (int(logical_x), int(logical_y)), Quartz.kCGMouseButtonLeft)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down1)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up1)
                time.sleep(max(0, interval_ms) / 1000.0)
                down2 = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (int(logical_x), int(logical_y)), Quartz.kCGMouseButtonLeft)
                up2 = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (int(logical_x), int(logical_y)), Quartz.kCGMouseButtonLeft)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down2)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up2)
            else:
                self.mouse.position = (logical_x, logical_y)
                self.mouse.click(Button.left, 1)
                time.sleep(max(0, interval_ms) / 1000.0)
                self.mouse.click(Button.left, 1)
        finally:
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass
        
        try:
            self.hide_highlight()
        except Exception:
            pass
        return (x, y)

    def move_mouse(self, x: int, y: int):
        if not self.mouse:
            raise RuntimeError("pynput not available")
        
        # 将截图坐标转换为系统逻辑坐标
        logical_x, logical_y = self._transform_coordinate(x, y)
        
        self.mouse.position = (logical_x, logical_y)
        return (logical_x, logical_y)

    def long_touch(self, x: int, y: int, duration: Optional[float] = None):
        if not self.mouse and Quartz is None:
            raise RuntimeError("pynput not available")
        
        logical_x, logical_y = self._transform_coordinate(x, y)
        
        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass
        
        try:
            if Quartz is not None:
                down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (int(logical_x), int(logical_y)), Quartz.kCGMouseButtonLeft)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
                time.sleep((duration or 1000) / 1000.0)
                up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (int(logical_x), int(logical_y)), Quartz.kCGMouseButtonLeft)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            else:
                self.mouse.position = (logical_x, logical_y)
                self.mouse.press(Button.left)
                time.sleep((duration or 1000) / 1000.0)
                self.mouse.release(Button.left)
        finally:
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass
        return (x, y)

    def _do_drag(self, start_xy: Tuple[int, int], end_xy: Tuple[int, int], duration: Optional[float] = None):
        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass
        
        try:
            start_x, start_y = self._transform_coordinate(start_xy[0], start_xy[1])
            end_x, end_y = self._transform_coordinate(end_xy[0], end_xy[1])
            if Quartz is not None:
                down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (int(start_x), int(start_y)), Quartz.kCGMouseButtonLeft)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
                steps = max(1, int(((duration or 1000) / 1000.0) * 60))
                for i in range(1, steps + 1):
                    nx = start_x + (end_x - start_x) * i / steps
                    ny = start_y + (end_y - start_y) * i / steps
                    drag = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDragged, (int(nx), int(ny)), Quartz.kCGMouseButtonLeft)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, drag)
                    time.sleep(1/60)
                up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (int(end_x), int(end_y)), Quartz.kCGMouseButtonLeft)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
            else:
                if not self.mouse:
                    raise RuntimeError("pynput not available")
                self.mouse.position = (int(start_x), int(start_y))
                self.mouse.press(Button.left)
                steps = max(1, int(((duration or 1000) / 1000.0) * 60))
                for i in range(1, steps + 1):
                    nx = start_x + (end_x - start_x) * i / steps
                    ny = start_y + (end_y - start_y) * i / steps
                    self.mouse.position = (int(nx), int(ny))
                    time.sleep(1/60)
                self.mouse.release(Button.left)
            return True
        finally:
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass

    def scroll_wheel(self, dx: int = 0, dy: int = -1):
        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.02)
        except Exception:
            pass
        try:
            if Quartz is not None:
                # 使用 Quartz 发送滚轮事件（dy>0 上，dy<0 下）
                # 这里使用单位步进，macOS 自身会处理平滑
                event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 2, int(dy), int(dx))
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                return True
            else:
                if not self.mouse:
                    raise RuntimeError("pynput not available")
                self.mouse.scroll(dx, dy)
                return True
        finally:
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass

    def scroll(self, start_xy: Tuple[int, int], end_xy: Tuple[int, int], duration: int = 1000):
        """
        根据起止坐标使用滚轮事件模拟滚动（忽略 duration，scroll_wheel 中未支持）。
        - 单次调用 scroll_wheel，按距离换算幅度（行数）并一次性发送
        - 竖向：使用 dy（>0 向上，<0 向下）
        - 横向：使用 dx（>0 向右，<0 向左）；为与 UI 层方向语义对齐，做适配映射
        """
        try:
            sx, sy = int(start_xy[0]), int(start_xy[1])
            ex, ey = int(end_xy[0]), int(end_xy[1])
        except Exception:
            return self._do_drag(start_xy, end_xy, duration)

        total_dx = ex - sx
        total_dy = ey - sy

        # 判定主轴：优先按绝对变化更大的轴滚动
        is_vertical = abs(total_dy) >= abs(total_dx)
        magnitude_px = abs(total_dy) if is_vertical else abs(total_dx)

        # 将像素距离映射为“行数”幅度；限制范围，避免过大
        # 经验比例：约 80px ≈ 1 行
        try:
            lines = int(magnitude_px / 80) if magnitude_px > 0 else 1
        except Exception:
            lines = 1
        lines = max(1, min(50, lines))

        if is_vertical:
            # UI 中：向上 => end_y > start_y（total_dy > 0）→ dy 正；向下 => dy 负
            dy = lines if total_dy > 0 else -lines
            dx = 0
        else:
            # UI 中 left 语义：total_dx > 0 需映射为向左滚（dx 负）
            dx = -lines if total_dx > 0 else lines
            dy = 0

        ok = False
        try:
            self.scroll_wheel(dx=dx, dy=dy)
            ok = True
        except Exception:
            ok = False

        if not ok:
            return self._do_drag(start_xy, end_xy, duration)
        return True

    def view_set_text(self, text: str):
        if not self.keyboard:
            raise RuntimeError("pynput not available")
        
        # 先全选当前输入框中的所有文本
        try:
            self.keyboard.press(Key.cmd)
            self.keyboard.press('a')
            self.keyboard.release('a')
            self.keyboard.release(Key.cmd)
            # 短暂延迟确保全选完成
            time.sleep(0.05)
            logger.debug("执行 Cmd+A 全选操作")
        except Exception as e:
            logger.debug(f"全选操作失败: {e}")
        
        # 1) 优先使用 Quartz 直接注入 Unicode，绕过 IME
        try:
            if self._type_text_via_quartz(text):
                logger.debug(f"view_set_text quartz typing success (覆盖模式)")
                return True
        except Exception as e:
            logger.debug(f"view_set_text quartz typing failed: {e}")
        # 2) 其次使用剪贴板 + 粘贴（粘贴后恢复原剪贴板，避免污染）
        try:
            if pyperclip is not None:
                original_clip = None
                try:
                    original_clip = pyperclip.paste()
                except Exception:
                    original_clip = None
                try:
                    pyperclip.copy(text or "")
                except Exception:
                    # 若复制失败，回退为逐字输入
                    raise
                # 给系统一点时间同步剪贴板
                time.sleep(0.05)
                # Cmd+V 粘贴
                self.keyboard.press(Key.cmd)
                self.keyboard.press('v')
                self.keyboard.release('v')
                self.keyboard.release(Key.cmd)
                logger.debug(f"view_set_text paste success (覆盖模式)")
                # 粘贴完成后，尽量恢复原剪贴板；若无法读取旧值，则清空
                try:
                    if original_clip is None:
                        pyperclip.copy("")
                    else:
                        pyperclip.copy(original_clip)
                except Exception:
                    pass
                return True
        except Exception as e:
            logger.debug(f"view_set_text paste failed, fallback to typing: {e}")
        # 3) 回退到逐字输入（可能受 IME 影响）
        logger.debug(f"view_set_text fallback to typing (覆盖模式)")
        self.keyboard.type(text)
        return True

    def view_append_text(self, text: str):
        return self.view_set_text(text)

    def view_clear_text(self) -> bool:
        """
        清除当前已选中输入框中的所有文本
        使用 Cmd+A 全选然后删除的方式
        Returns:
            bool: 清除操作是否成功
        """
        if not self.keyboard:
            raise RuntimeError("pynput not available")
        try:
            # 方法1: Cmd+A 全选，然后按 Delete 键删除
            self.keyboard.press(Key.cmd)
            self.keyboard.press('a')
            self.keyboard.release('a')
            self.keyboard.release(Key.cmd)
            
            # 短暂延迟确保全选完成
            time.sleep(0.05)
            
            # 按 Delete 键删除选中的文本
            self.keyboard.press(Key.delete)
            self.keyboard.release(Key.delete)
            
            logger.debug("使用 Cmd+A + Delete 成功清除文本")
            return True
        except Exception as e:
            logger.debug(f"清除文本失败: {e}")
            # 备用方法1：使用剪贴板设置为空字符串然后粘贴
            try:
                if pyperclip is not None:
                    # 保存原剪贴板内容
                    original_clip = None
                    try:
                        original_clip = pyperclip.paste()
                    except Exception:
                        original_clip = None
                    
                    # 先全选
                    self.keyboard.press(Key.cmd)
                    self.keyboard.press('a')
                    self.keyboard.release('a')
                    self.keyboard.release(Key.cmd)
                    time.sleep(0.02)
                    
                    # 设置剪贴板为空字符串并粘贴
                    pyperclip.copy("")
                    time.sleep(0.02)
                    self.keyboard.press(Key.cmd)
                    self.keyboard.press('v')
                    self.keyboard.release('v')
                    self.keyboard.release(Key.cmd)
                    
                    # 恢复原剪贴板内容
                    try:
                        if original_clip is not None:
                            pyperclip.copy(original_clip)
                        else:
                            pyperclip.copy("")
                    except Exception:
                        pass
                    
                    logger.debug("使用剪贴板方式成功清除文本")
                    return True
            except Exception as e2:
                logger.debug(f"剪贴板清除方法失败: {e2}")
            
            # 备用方法2：使用 Backspace 多次删除
            try:
                for _ in range(100):  # 删除100个字符，应该足够清除大多数文本
                    self.keyboard.press(Key.backspace)
                    self.keyboard.release(Key.backspace)
                    time.sleep(0.001)  # 很短的延迟
                logger.debug("使用备用方法（多次 Backspace）清除文本")
                return True
            except Exception as e3:
                logger.debug(f"备用清除方法也失败: {e3}")
                return False

    def key_press(self, key: str):
        if not self.keyboard:
            raise RuntimeError("pynput not available")
        special = {
            'enter': Key.enter,
            'esc': Key.esc,
            'tab': Key.tab,
            'backspace': Key.backspace,
            'delete': Key.delete,
            'shift': Key.shift,
            'ctrl': Key.ctrl,
            'alt': Key.alt,
            'cmd': Key.cmd,
        }
        k = special.get(key.lower(), key)
        self.keyboard.press(k)
        self.keyboard.release(k)
        return True

    def enter(self) -> bool:
        return self.key_press('enter') or True

    def take_screenshot_impl(self, save_path: Optional[str] = None, screen: Optional[object] = None, hide_overlay: bool = True) -> Image.Image:
        """
        通过后端 /get_screenshot（computer 分支）获取截图
        """
        api_base_url = f"http://localhost:{self.agent.config.flask_port}"
        try:
            # 传递 hide_overlay 参数，隐藏悬浮窗以确保截图不包含悬浮窗
            resp = requests.post(
                f"{api_base_url}/computer/get_screenshot",
                json={'hide_overlay': hide_overlay},
                timeout=5
            )
            if resp.status_code != 200:
                logger.error(f"❌ 获取电脑截图失败")
                raise RuntimeError(f"get_screenshot获取截图失败，接口返回：HTTP {resp.status_code}: {resp.text}")

            payload = resp.json()
            data_url = payload.get('screenshot')

            if not data_url or not isinstance(data_url, str) or ',' not in data_url:
                raise RuntimeError(f"Invalid screenshot data from /get_screenshot, data_url: {data_url}")

            b64_part = data_url.split(',', 1)[1]
            img_bytes = base64.b64decode(b64_part)
            image = Image.open(io.BytesIO(img_bytes))

            if save_path:
                image.save(save_path)

            # 保存截图到桌面
            # import os, time
            # desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            # save_path = os.path.join(desktop_path, f"screenshot_time_{time.time()}.png")
            # image.save(save_path)

            return image
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 获取电脑截图失败")
            logger.debug(f"❌ 获取电脑截图失败: {e}")
            raise RuntimeError(f"Failed to get screenshot from API: {e}") from e
        except (RuntimeError, KeyError, base64.binascii.Error) as e:
            logger.error(f"❌ 获取电脑截图失败")
            logger.debug(f"❌ 获取电脑截图失败: {e}")
            raise

    def start_screen_record(self):
        # 可通过 ffmpeg 或 AVFoundation 实现；此处占位
        raise NotImplementedError("Not implemented on macOS")

    def stop_screen_record(self):
        raise NotImplementedError("Not implemented on macOS")

    def show_highlight(self, x: int, y: int, radius: int):
        """在 macOS 上通过透明无边框 NSWindow 绘制一个圆圈（仅主屏）。"""
        try:
            if AppKit is None:
                return True
            if not self._ensure_nsapp():
                return False
            # 使用主屏（菜单栏所在屏幕）坐标
            screens = AppKit.NSScreen.screens()
            primary = screens[0] if screens and len(screens) > 0 else AppKit.NSScreen.mainScreen()
            frame = primary.frame()
            screen_h_pt = int(frame.size.height)
            
            # 将传入的截图坐标转换为系统逻辑坐标
            logical_x, logical_y = self._transform_coordinate(x, y)
            x_pt = logical_x
            y_pt = logical_y
            r_pt = radius
            diameter = int(r_pt * 2)
            
            # Cocoa 坐标系转换：从左上角原点转为左下角原点
            cocoa_y = screen_h_pt - int(y_pt) - r_pt
            rect = AppKit.NSMakeRect(int(x_pt) - r_pt, cocoa_y, diameter, diameter)

            # 使用模块级定义的视图，避免重复注册类问题
            if CircleOverlayView is None:
                return False

            window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                rect,
                AppKit.NSWindowStyleMaskBorderless,
                AppKit.NSBackingStoreBuffered,
                False
            )
            window.setOpaque_(False)
            window.setBackgroundColor_(AppKit.NSColor.clearColor())
            # 出现在所有空间上、覆盖全屏应用
            try:
                behavior = AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
                if hasattr(AppKit, 'NSWindowCollectionBehaviorFullScreenAuxiliary'):
                    behavior |= AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
                try:
                    behavior |= AppKit.NSWindowCollectionBehaviorStationary
                except Exception:
                    pass
                window.setCollectionBehavior_(behavior)
            except Exception:
                pass
            # 提升层级：优先 ScreenSaver，其次 Status，再退回 Floating
            try:
                level = getattr(AppKit, 'NSScreenSaverWindowLevel', None)
                if level is None:
                    level = getattr(AppKit, 'NSStatusWindowLevel', None)
                if level is None:
                    level = AppKit.NSFloatingWindowLevel
                window.setLevel_(level)
            except Exception:
                try:
                    window.setLevel_(AppKit.NSFloatingWindowLevel)
                except Exception:
                    pass
            content = CircleOverlayView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, diameter, diameter))
            window.setContentView_(content)
            window.setIgnoresMouseEvents_(True)
            # 显示且不抢焦点
            try:
                window.orderFrontRegardless()
            except Exception:
                window.makeKeyAndOrderFront_(None)
            # 刷新渲染
            try:
                content.setNeedsDisplay_(True)
            except Exception:
                pass
            try:
                window.displayIfNeeded()
            except Exception:
                try:
                    window.display()
                except Exception:
                    pass
            try:
                AppKit.NSApp.activateIgnoringOtherApps_(False)
            except Exception:
                pass
            # 最小事件循环以确保绘制
            try:
                if NSRunLoop and NSDate:
                    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.01))
            except Exception:
                pass
            try:
                self._highlight_windows.append(window)
            except Exception:
                # 容错：若属性不存在则初始化
                self._highlight_windows = [window]
            return True
        except Exception:
            return False

    def hide_highlight(self):
        try:
            windows = getattr(self, '_highlight_windows', None)
            if not windows:
                return True
            for win in list(windows):
                try:
                    win.orderOut_(None)
                except Exception:
                    pass
                try:
                    win.close()
                except Exception:
                    pass
            self._highlight_windows = []
            # 轻刷事件循环，加速移除
            try:
                if NSRunLoop and NSDate:
                    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.005))
            except Exception:
                pass
            return True
        except Exception:
            return False

    def show_highlight_rect(self, x1: int, y1: int, x2: int, y2: int):
        return True

    def hide_highlight_rect(self, x1: int, y1: int, x2: int, y2: int):
        return True

    def get_clipboard(self) -> str:
        if not pyperclip:
            raise RuntimeError("pyperclip not available")
        return pyperclip.paste() or ""

    def set_clipboard(self, text: str) -> bool:
        if not pyperclip:
            raise RuntimeError("pyperclip not available")
        pyperclip.copy(text or "")
        return True

    def expand_notification_panel(self):
        # AppleScript 打开通知中心
        try:
            script = 'tell application "System Events" to tell process "Control Center" to click menu bar item 1 of menu bar 1'
            subprocess.run(["osascript", "-e", script], check=False)
            return True
        except Exception:
            return False

    def get_system_width_height(self) -> Tuple[int, int]:
        """
        获取电脑的宽度和高度，此处为系统逻辑宽高，比截图的实际宽高要小
        Returns:
            Tuple[int, int]: 电脑的宽度和高度
        """
        if not AppKit:
            if not mss:
                return (0, 0)
            with mss.mss() as sct:
                mon = sct.monitors[0]
                return int(mon["width"]), int(mon["height"])
        screen = AppKit.NSScreen.mainScreen().frame()
        return int(screen.size.width), int(screen.size.height)

    def get_width_height(self) -> Tuple[int, int]:
        """
        获取电脑截图得到的实际宽高
        Returns:
            Tuple[int, int]: 电脑的宽度和高度
        """
        if not self.width or not self.height:
            self.width, self.height = self.take_screenshot(hide_overlay=False).size
        return self.width, self.height

    def get_ui_tree(self) -> List[Dict]:
        """
        macOS 未直接开放完整 AX 树（需要辅助功能权限且实现较大）。
        这里返回前台窗口的粗略可见区域作为一个节点，供 snap_click 近似吸附。
        如需更强能力，可后续改为 PyObjC + AXUIElement 遍历。
        """
        try:
            if Quartz is None:
                return []
            # 获取前台应用窗口区域
            ws = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID) or []
            # 选择层级最高的前台窗口
            focused = None
            for w in ws:
                if w.get('kCGWindowLayer') == 0 and w.get('kCGWindowOwnerName'):
                    focused = w
                    break
            nodes: List[Dict] = []
            if focused:
                bounds = focused.get('kCGWindowBounds') or {}
                x = int(bounds.get('X', 0))
                y = int(bounds.get('Y', 0))
                w = int(bounds.get('Width', 0))
                h = int(bounds.get('Height', 0))
                nodes.append({
                    'temp_id': 1,
                    'bounds': ((x, y), (x + w, y + h)),
                    'clickable': True,
                    'visible': True,
                    'enabled': True,
                    'children': [],
                    'class': 'Window',
                    'resource_id': focused.get('kCGWindowName') or ''
                })
            return nodes
        except Exception:
            return []

    def snap_click(self, x: int, y: int, duration: int = 200):
        try:
            ui_tree = self.get_ui_tree()
            if not ui_tree:
                return self.click(x, y, duration)
            # 仅窗口级别：如果点在窗口内，点击窗口中心，作为粗略吸附
            n = ui_tree[0]
            (x1,y1),(x2,y2) = n.get('bounds', ((x,y),(x,y)))
            inside = (x1 <= x <= x2) and (y1 <= y <= y2)
            if inside:
                cx, cy = ((x1 + x2)//2, (y1 + y2)//2)
                return self.click(cx, cy, duration)
            return self.click(x, y, duration)
        except Exception:
            return self.click(x, y, duration) 

    def _type_text_via_quartz(self, text: str) -> bool:
        """
        使用 Quartz 直接注入 Unicode 字符，尽量绕过输入法组合干扰。
        返回 True 表示已成功注入；False 表示不支持或失败。
        """
        if Quartz is None:
            return False
        try:
            for ch in text:
                # key down
                ev_down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
                Quartz.CGEventKeyboardSetUnicodeString(ev_down, len(ch), ch)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_down)
                # key up
                ev_up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
                Quartz.CGEventKeyboardSetUnicodeString(ev_up, len(ch), ch)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev_up)
                time.sleep(0.001)
            return True
        except Exception:
            return False

    def hotkey(self, keys: str) -> bool:
        """
        模拟组合键按下
        Args:
            keys: 空格分隔的按键组合，如 'ctrl c', 'alt tab'
        Returns:
            bool: 操作是否成功
        """
        if not self.keyboard:
            raise RuntimeError("pynput not available")

        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass

        try:
            key_list = keys.lower().split()
            if len(key_list) > 3:
                logger.warning(f"hotkey 组合键过多 ({len(key_list)} 个)，只支持最多 3 个按键")
                return False

            # 特殊键映射
            key_map = {
                'ctrl': Key.ctrl,
                'ctrl_l': Key.ctrl_l,
                'ctrl_r': Key.ctrl_r,
                'cmd': Key.cmd,
                'cmd_l': Key.cmd_l,
                'cmd_r': Key.cmd_r,
                'alt': Key.alt,
                'alt_l': Key.alt_l,
                'alt_r': Key.alt_r,
                'alt_gr': Key.alt_gr,
                'shift': Key.shift,
                'shift_l': Key.shift_l,
                'shift_r': Key.shift_r,
                'enter': Key.enter,
                'esc': Key.esc,
                'tab': Key.tab,
                'backspace': Key.backspace,
                'delete': Key.delete,
                'space': Key.space,
                'up': Key.up,
                'down': Key.down,
                'left': Key.left,
                'right': Key.right,
                'pageup': Key.page_up,
                'pagedown': Key.page_down,
                'home': Key.home,
                'end': Key.end,
                'caps_lock': Key.caps_lock,
                # 功能键
                'f1': Key.f1,
                'f2': Key.f2,
                'f3': Key.f3,
                'f4': Key.f4,
                'f5': Key.f5,
                'f6': Key.f6,
                'f7': Key.f7,
                'f8': Key.f8,
                'f9': Key.f9,
                'f10': Key.f10,
                'f11': Key.f11,
                'f12': Key.f12,
                'f13': Key.f13,
                'f14': Key.f14,
                'f15': Key.f15,
                'f16': Key.f16,
                'f17': Key.f17,
                'f18': Key.f18,
                'f19': Key.f19,
                'f20': Key.f20,
                # 媒体键
                'media_play_pause': Key.media_play_pause,
                'media_volume_mute': Key.media_volume_mute,
                'media_volume_down': Key.media_volume_down,
                'media_volume_up': Key.media_volume_up,
                'media_previous': Key.media_previous,
                'media_next': Key.media_next,
            }
            # 安全地添加 insert 键（某些平台可能不支持）
            if hasattr(Key, 'insert'):
                key_map['insert'] = Key.insert
            if hasattr(Key, 'num_lock'):
                key_map['num_lock'] = Key.num_lock
            if hasattr(Key, 'scroll_lock'):
                key_map['scroll_lock'] = Key.scroll_lock
            if hasattr(Key, 'pause'):
                key_map['pause'] = Key.pause
            if hasattr(Key, 'print_screen'):
                key_map['print_screen'] = Key.print_screen
                key_map['printscreen'] = Key.print_screen
            if hasattr(Key, 'menu'):
                key_map['menu'] = Key.menu

            # 转换按键
            pynput_keys = []
            for key in key_list:
                if key in key_map:
                    pynput_keys.append(key_map[key])
                else:
                    # 单字符按键
                    pynput_keys.append(key)

            # 按下所有按键
            for key in pynput_keys:
                self.keyboard.press(key)

            # 短暂延迟
            time.sleep(0.05)

            # 释放所有按键（反序）
            for key in reversed(pynput_keys):
                self.keyboard.release(key)

            return True
        finally:
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass 
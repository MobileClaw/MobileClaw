from .base import ComputerDeviceBase
from typing import Tuple, Optional, List, Dict
import time
import os
import glob
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)

try:
    from pynput.mouse import Controller as Mouse, Button
    from pynput.keyboard import Controller as Keyboard, Key
    import mss
    import pyperclip
    import uiautomation as auto
except Exception:
    Mouse = None  # type: ignore
    Keyboard = None  # type: ignore
    Button = None  # type: ignore
    mss = None  # type: ignore
    pyperclip = None  # type: ignore
    auto = None  # type: ignore

from PIL import Image, ImageDraw
import ctypes

ClickableTypes = {
    'Button', 'Hyperlink', 'ListItem', 'MenuItem', 'TabItem', 'TreeItem',
    'CheckBox', 'RadioButton', 'Edit', 'ComboBox', 'DataItem'
}

class WindowsComputerDevice(ComputerDeviceBase):
    def __init__(self, agent, device_name: str, device_id: str):
        super().__init__(agent, device_name, device_id)
        self.mouse = Mouse() if Mouse else None
        self.keyboard = Keyboard() if Keyboard else None
        # 高亮状态：保存最后一次高亮的参数，便于用 XOR 绘制再次擦除
        self._highlight_state: Optional[Tuple[int, int, int]] = None
        # 多实例分层窗口列表（每个元素包含 hwnd/hdc/hbmp）
        self._highlight_windows: List[Dict[str, int]] = []
        # 关闭 uiautomation 的文件日志，避免生成 AutomationLog.txt
        try:
            if auto is not None and hasattr(auto, 'Logger'):
                try:
                    auto.Logger.SetLogFile('NUL')  # Windows 空设备，阻止写文件
                except Exception:
                    try:
                        auto.Logger.SetLogFile('')
                    except Exception:
                        try:
                            auto.Logger.SetLogFile(None)
                        except Exception:
                            pass
        except Exception:
            pass

    def _get_start_menu_programs_dirs(self):
        """Return robust Start Menu 'Programs' directories for current Windows.

        Prefer environment variables and fall back to conventional locations.
        Only return directories that actually exist.
        """
        candidate_dirs = []

        # Current user Start Menu Programs: %APPDATA%\Microsoft\Windows\Start Menu\Programs
        appdata = os.environ.get("APPDATA")
        if appdata:
            user_programs = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if user_programs.is_dir():
                candidate_dirs.append(str(user_programs))
        else:
            # Fallback if APPDATA is missing (e.g., service context)
            fallback_user = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if fallback_user.is_dir():
                candidate_dirs.append(str(fallback_user))

        # All users Start Menu Programs: %ProgramData%\Microsoft\Windows\Start Menu\Programs
        program_data_root = os.environ.get("ProgramData", r"C:\\ProgramData")
        common_programs = Path(program_data_root) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if common_programs.is_dir():
            candidate_dirs.append(str(common_programs))

        # De-duplicate while preserving order
        return list(dict.fromkeys(candidate_dirs))

    def start_app(self, app_name: str) -> bool:
        apps_list = [
            s
            for p in self._get_start_menu_programs_dirs()
            for s in glob.glob(os.path.join(p, "**", "*.lnk"), recursive=True)
        ]

        for app in apps_list:
            name = os.path.basename(app)
            if name == f"{app_name}.lnk":
                os.startfile(app)
                logger.info(f"✅ 成功启动应用程序 \"{app_name}\"")
                time.sleep(0.5)
                # 通知应用启动成功
                self._notify_app_started(app_name)
                return True
        
        logger.info(f"未找到应用程序 \"{app_name}\"，启动失败")
        return False

    def kill_app(self, app_name: str) -> bool:
        try:
            import subprocess
            subprocess.run(["taskkill", "/IM", app_name, "/F"], check=False)
            return True
        except Exception:
            return False
    
    def _get_app_info(self, app_name: str, **kwargs) -> dict:
        """获取Windows应用信息
        
        Args:
            app_name: 应用名称
            **kwargs: 可选参数
            
        Returns:
            dict: 应用信息字典
        """
        app_info = {
            "bundle_id": "",
            "developer": "",
            "description": "",
            "display_name": "",
            "icon": "",
            "name": app_name,
            "type": 1,  # 电脑端固定为1
            "version": ""
        }
        
        try:
            # 查找应用的 .lnk 文件
            apps_list = [
                s
                for p in self._get_start_menu_programs_dirs()
                for s in glob.glob(os.path.join(p, "**", "*.lnk"), recursive=True)
            ]
            
            app_lnk_path = None
            for app_path in apps_list:
                name = os.path.basename(app_path)
                if name == f"{app_name}.lnk":
                    app_lnk_path = app_path
                    break
            
            if app_lnk_path:
                try:
                    # 尝试解析 .lnk 文件获取目标路径
                    import win32com.client
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shortcut = shell.CreateShortcut(app_lnk_path)
                    target_path = shortcut.TargetPath
                    
                    if target_path and os.path.exists(target_path):
                        # 使用 TargetPath 作为 bundle_id 的替代
                        app_info["bundle_id"] = target_path
                        app_info["display_name"] = app_name
                        
                        # 尝试获取文件版本信息
                        try:
                            import win32api
                            info = win32api.GetFileVersionInfo(target_path, "\\")
                            ms = info['FileVersionMS']
                            ls = info['FileVersionLS']
                            version = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
                            app_info["version"] = version
                            
                            # 尝试获取公司名称（开发者）
                            try:
                                lang, codepage = win32api.GetFileVersionInfo(target_path, '\\VarFileInfo\\Translation')[0]
                                str_info_key = f'\\StringFileInfo\\{lang:04X}{codepage:04X}\\'
                                
                                company_name = win32api.GetFileVersionInfo(target_path, str_info_key + 'CompanyName')
                                if company_name:
                                    app_info["developer"] = company_name
                                
                                file_description = win32api.GetFileVersionInfo(target_path, str_info_key + 'FileDescription')
                                if file_description:
                                    app_info["description"] = file_description
                            except Exception:
                                pass
                                
                        except Exception as e:
                            logger.debug(f"获取Windows应用版本信息失败: {str(e)}")
                            
                except Exception as e:
                    logger.debug(f"解析Windows快捷方式失败: {str(e)}")
                    # 如果无法解析，至少设置基本信息
                    app_info["bundle_id"] = app_lnk_path
                    app_info["display_name"] = app_name
                    
        except Exception as e:
            logger.debug(f"获取Windows应用信息失败: {str(e)}")
        
        return app_info

    def click(self, x: int, y: int, duration: int = 1000):
        if not self.mouse:
            raise RuntimeError("pynput not available")
        # 点击前高亮
        try:
            self.show_highlight(x, y, radius=24)
            # 短暂延迟确保高亮显示完成
            time.sleep(0.05)
        except Exception:
            pass
        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass
        try:
            self.mouse.position = (x, y)
            self.mouse.click(Button.left, 1)
            if duration:
                time.sleep(duration / 1000.0)
        finally:
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

    def right_click(self, x: int, y: int, duration: int = 200):
        if not self.mouse:
            raise RuntimeError("pynput not available")
        try:
            self.show_highlight(x, y, radius=24)
            # 短暂延迟确保高亮显示完成
            time.sleep(0.05)
        except Exception:
            pass
        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass
        try:
            self.mouse.position = (x, y)
            self.mouse.click(Button.right, 1)
            if duration:
                time.sleep(duration / 1000.0)
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

    def double_click(self, x: int, y: int, interval_ms: int = 50):
        if not self.mouse:
            raise RuntimeError("pynput not available")
        try:
            self.show_highlight(x, y, radius=24)
            # 短暂延迟确保高亮显示完成
            time.sleep(0.05)
        except Exception:
            pass
        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass
        try:
            self.mouse.position = (x, y)
            # 两次左键点击
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
        # 开启短暂穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.01)
        except Exception:
            pass
        try:
            self.mouse.position = (x, y)
            return (x, y)
        finally:
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass

    def long_touch(self, x: int, y: int, duration: Optional[float] = None):
        if not self.mouse:
            raise RuntimeError("pynput not available")
        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass
        try:
            self.mouse.position = (x, y)
            self.mouse.press(Button.left)
            time.sleep((duration or 1000) / 1000.0)
            self.mouse.release(Button.left)
            return (x, y)
        finally:
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass

    def _do_drag(self, start_xy: Tuple[int, int], end_xy: Tuple[int, int], duration: Optional[float] = None):
        if not self.mouse:
            raise RuntimeError("pynput not available")
        # 开启穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.03)
        except Exception:
            pass
        try:
            self.mouse.position = (start_xy[0], start_xy[1])
            self.mouse.press(Button.left)
            # 简单线性插值移动
            steps = max(1, int(((duration or 1000) / 1000.0) * 60))
            for i in range(1, steps + 1):
                nx = start_xy[0] + (end_xy[0] - start_xy[0]) * i / steps
                ny = start_xy[1] + (end_xy[1] - start_xy[1]) * i / steps
                self.mouse.position = (int(nx), int(ny))
                time.sleep(1 / 60)
            self.mouse.release(Button.left)
            return True
        finally:
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass

    def scroll_wheel(self, dx: int = 0, dy: int = -1):
        # pynput 鼠标滚轮：scroll(dx, dy)，dy>0 向上，dy<0 向下
        if not self.mouse:
            raise RuntimeError("pynput not available")
        # 开启短暂穿透
        try:
            self.overlay_clickthrough_on()
            time.sleep(0.02)
        except Exception:
            pass
        try:
            # 不显示高亮，滚轮通常不需要
            try:
                self.mouse.scroll(dx, dy)
            except Exception:
                return False
            return True
        finally:
            try:
                self.overlay_clickthrough_off()
            except Exception:
                pass

    def view_set_text(self, text: str):
        if not self.keyboard:
            raise RuntimeError("pynput not available")
        
        # 0) 首选：通过 UIAutomation 的 ValuePattern 直接设置文本，完全绕过输入法
        try:
            if auto is not None:
                try:
                    with auto.UIAutomationInitializerInThread():
                        focused = auto.GetFocusedControl()
                        try:
                            vp = focused.GetPattern(auto.PatternId.ValuePatternId)
                        except Exception:
                            vp = None
                        if vp is not None:
                            try:
                                vp.SetValue(text)
                                logger.debug("使用 UIAutomation ValuePattern.SetValue 设置文本")
                                return True
                            except Exception as e_vp:
                                logger.debug(f"ValuePattern.SetValue 失败: {e_vp}")
                except Exception:
                    # 兼容性兜底：未能初始化时尝试直接调用
                    try:
                        focused = auto.GetFocusedControl()
                        try:
                            vp = focused.GetPattern(auto.PatternId.ValuePatternId)
                        except Exception:
                            vp = None
                        if vp is not None:
                            try:
                                vp.SetValue(text)
                                logger.debug("使用 UIAutomation ValuePattern.SetValue 设置文本（无初始化兜底）")
                                return True
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass

        # 1) 次选：Ctrl+A 全选 + 可靠剪贴板设置 + Ctrl+V 粘贴（需确保粘贴的是传入 text 而非旧剪贴板）
        try:
            self.keyboard.press(Key.ctrl)
            self.keyboard.press('a')
            self.keyboard.release('a')
            self.keyboard.release(Key.ctrl)
        except Exception:
            pass
        time.sleep(0.05)

        previous_clipboard: Optional[str] = None
        clipboard_supported = (pyperclip is not None)
        if clipboard_supported:
            try:
                previous_clipboard = pyperclip.paste()
            except Exception:
                previous_clipboard = None

        def _robust_copy_to_clipboard(value: str) -> bool:
            # 优先 pyperclip，写后读校验，多次重试；失败则走 Win32 API 兜底
            if pyperclip is not None:
                for _ in range(3):
                    try:
                        pyperclip.copy(value)
                        time.sleep(0.03)
                        pasted = pyperclip.paste()
                        if pasted == value:
                            return True
                    except Exception:
                        time.sleep(0.03)
                        continue
            # Win32 兜底
            try:
                return self._set_clipboard_win32(value)
            except Exception:
                return False

        if _robust_copy_to_clipboard(text):
            try:
                self.keyboard.press(Key.ctrl)
                self.keyboard.press('v')
                self.keyboard.release('v')
                self.keyboard.release(Key.ctrl)
                # 等待粘贴完成再恢复剪贴板，避免竞态导致粘错内容
                time.sleep(0.06)
                logger.debug("使用 Ctrl+A + Ctrl+V 粘贴文本，已验证剪贴板为传入文本")
                return True
            except Exception as e_kbd:
                logger.debug(f"Ctrl+V 粘贴失败，将回退到逐字键入: {e_kbd}")
            finally:
                if clipboard_supported and previous_clipboard is not None:
                    try:
                        pyperclip.copy(previous_clipboard)
                    except Exception:
                        pass

        # 2) 最终兜底：逐字键入（可能触发输入法候选）
        try:
            self.keyboard.type(text)
            logger.debug("回退为逐字键入文本")
            return True
        except Exception as e2:
            logger.debug(f"逐字键入失败: {e2}")
            return False

    def _set_clipboard_win32(self, text: str) -> bool:
        """使用 Win32 API 设置系统剪贴板为给定 Unicode 文本。"""
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002

            if not user32.OpenClipboard(0):
                # 某些情况下需要多次尝试打开剪贴板
                for _ in range(3):
                    time.sleep(0.02)
                    if user32.OpenClipboard(0):
                        break
                else:
                    return False
            try:
                user32.EmptyClipboard()
                # 创建包含 NUL 终止的宽字符缓冲区
                data = ctypes.create_unicode_buffer(text)
                size_bytes = ctypes.sizeof(ctypes.c_wchar) * len(data)
                h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, size_bytes)
                if not h_global:
                    return False
                locked = kernel32.GlobalLock(h_global)
                if not locked:
                    kernel32.GlobalFree(h_global)
                    return False
                try:
                    ctypes.memmove(locked, ctypes.addressof(data), size_bytes)
                finally:
                    kernel32.GlobalUnlock(h_global)
                if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
                    kernel32.GlobalFree(h_global)
                    return False
                # 成功后，内存由系统接管，不可再释放 h_global
                return True
            finally:
                user32.CloseClipboard()
        except Exception:
            return False

    def view_append_text(self, text: str):
        return self.view_set_text(text)

    def view_clear_text(self) -> bool:
        """
        清除当前已选中输入框中的所有文本
        使用 Ctrl+A 全选然后删除的方式
        Returns:
            bool: 清除操作是否成功
        """
        if not self.keyboard:
            raise RuntimeError("pynput not available")
        try:
            # 方法1: Ctrl+A 全选，然后按 Delete 键删除
            self.keyboard.press(Key.ctrl)
            self.keyboard.press('a')
            self.keyboard.release('a')
            self.keyboard.release(Key.ctrl)
            
            # 短暂延迟确保全选完成
            time.sleep(0.05)
            
            # 按 Delete 键删除选中的文本
            self.keyboard.press(Key.delete)
            self.keyboard.release(Key.delete)
            
            logger.debug("使用 Ctrl+A + Delete 成功清除文本")
            return True
        except Exception as e:
            logger.debug(f"清除文本失败: {e}")
            # 备用方法：使用 Backspace 多次删除
            try:
                for _ in range(100):  # 删除100个字符，应该足够清除大多数文本
                    self.keyboard.press(Key.backspace)
                    self.keyboard.release(Key.backspace)
                    time.sleep(0.001)  # 很短的延迟
                logger.debug("使用备用方法（多次 Backspace）清除文本")
                return True
            except Exception as e2:
                logger.debug(f"备用清除方法也失败: {e2}")
                return False

    def key_press(self, key: str):
        if not self.keyboard:
            raise RuntimeError("pynput not available")
        # 处理常见特殊键
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
            'win': Key.cmd,
        }
        k = special.get(key.lower(), key)
        self.keyboard.press(k)
        self.keyboard.release(k)
        return True

    def enter(self) -> bool:
        return self.key_press('enter') or True

    def take_screenshot_impl(self, save_path: Optional[str] = None, screen: Optional[object] = None, hide_overlay: bool = True) -> Image.Image:
        """
        screen: None/'primary' -> 主屏；'all' -> 全部；int -> 指定编号（mss 为 1-based）
        """
        if not mss:
            raise RuntimeError("mss not available")

        with mss.mss() as sct:
            if hide_overlay:
                self.hide_execution_overlay()
            
            if screen is None or screen == 'primary':
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            elif screen == 'all':
                monitor = sct.monitors[0]
            elif isinstance(screen, int):
                idx = screen
                if idx < 0:
                    idx = 1
                if idx >= len(sct.monitors):
                    idx = 1
                monitor = sct.monitors[idx]
            else:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            raw = sct.grab(monitor)
            img = Image.frombytes("RGB", raw.size, raw.rgb)
            if save_path:
                img.save(save_path)
            
            if hide_overlay:
                self.show_execution_overlay()
            return img

    def start_screen_record(self):
        raise NotImplementedError("Not implemented on Windows")

    def stop_screen_record(self):
        raise NotImplementedError("Not implemented on Windows")

    def show_highlight(self, x: int, y: int, radius: int):
        """在 Windows 上使用分层置顶透明窗口绘制高亮圆圈。"""
        try:
            # logger.info("show_highlight:start", x=x, y=y, radius=radius, pid=os.getpid())
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            kernel32 = ctypes.windll.kernel32

            # --- Ensure proper ctypes signatures to support 64-bit handles ---
            try:
                VOIDP = ctypes.c_void_p
                UINT = ctypes.c_uint
                INT = ctypes.c_int
                DWORD = ctypes.c_uint32

                # gdi32
                gdi32.CreateCompatibleDC.restype = VOIDP
                gdi32.CreateCompatibleDC.argtypes = [VOIDP]

                gdi32.CreateDIBSection.restype = VOIDP
                gdi32.CreateDIBSection.argtypes = [
                    VOIDP,               # hdc
                    ctypes.c_void_p,     # const BITMAPINFO* (we pass byref)
                    UINT,                # usage
                    ctypes.POINTER(VOIDP), # void** bits
                    VOIDP,               # hSection
                    DWORD,               # offset
                ]

                gdi32.SelectObject.restype = VOIDP
                gdi32.SelectObject.argtypes = [VOIDP, VOIDP]

                gdi32.DeleteObject.restype = INT
                gdi32.DeleteObject.argtypes = [VOIDP]

                gdi32.DeleteDC.restype = INT
                gdi32.DeleteDC.argtypes = [VOIDP]

                gdi32.CreatePen.restype = VOIDP
                gdi32.CreatePen.argtypes = [INT, INT, DWORD]

                gdi32.GetStockObject.restype = VOIDP
                gdi32.GetStockObject.argtypes = [INT]

                gdi32.Ellipse.restype = INT
                gdi32.Ellipse.argtypes = [VOIDP, INT, INT, INT, INT]

                gdi32.SetROP2.restype = INT
                gdi32.SetROP2.argtypes = [VOIDP, INT]

                # user32
                user32.DestroyWindow.restype = INT
                user32.DestroyWindow.argtypes = [VOIDP]

                user32.ShowWindow.restype = INT
                user32.ShowWindow.argtypes = [VOIDP, INT]

                user32.UpdateLayeredWindow.restype = INT
                # Keep argtypes unspecified for UpdateLayeredWindow to avoid mismatch complexities
            except Exception:
                # If setting signatures fails, continue with best-effort defaults
                pass

            diameter = max(8, int(radius) * 2)
            left = int(x - diameter // 2)
            top = int(y - diameter // 2)
            # logger.info("show_highlight:geometry", diameter=diameter, left=left, top=top)

            # 创建分层窗口（点击穿透、置顶、工具窗不显示在任务栏）
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOPMOST = 0x00000008
            WS_EX_TOOLWINDOW = 0x00000080
            WS_POPUP = 0x80000000

            hInstance = kernel32.GetModuleHandleW(None)
            hwnd = user32.CreateWindowExW(
                WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
                ctypes.c_wchar_p("Static"),
                ctypes.c_wchar_p(None),
                WS_POPUP,
                left,
                top,
                diameter,
                diameter,
                None,
                None,
                hInstance,
                None,
            )
            if not hwnd:
                # logger.info("show_highlight:CreateWindowExW_failed")
                return False
            # else:
            #     try:
            #         logger.info("show_highlight:CreateWindowExW_ok", hwnd=int(hwnd))
            #     except Exception:
            #         logger.info("show_highlight:CreateWindowExW_ok")

            # 准备 32 位带 Alpha 的 DIB 位图内存并绘制圆
            class BITMAPINFOHEADER(ctypes.Structure):
                _fields_ = [
                    ("biSize", ctypes.c_uint32),
                    ("biWidth", ctypes.c_int32),
                    ("biHeight", ctypes.c_int32),
                    ("biPlanes", ctypes.c_uint16),
                    ("biBitCount", ctypes.c_uint16),
                    ("biCompression", ctypes.c_uint32),
                    ("biSizeImage", ctypes.c_uint32),
                    ("biXPelsPerMeter", ctypes.c_int32),
                    ("biYPelsPerMeter", ctypes.c_int32),
                    ("biClrUsed", ctypes.c_uint32),
                    ("biClrImportant", ctypes.c_uint32),
                ]

            class BITMAPINFO(ctypes.Structure):
                _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 1)]

            DIB_RGB_COLORS = 0
            BI_RGB = 0

            bmi = BITMAPINFO()
            ctypes.memset(ctypes.byref(bmi), 0, ctypes.sizeof(bmi))
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = diameter
            # 负高度，使用 top-down 位图，避免倒置
            bmi.bmiHeader.biHeight = -diameter
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = BI_RGB

            ppv_bits = ctypes.c_void_p()
            hdc_mem = gdi32.CreateCompatibleDC(ctypes.c_void_p(0))
            hbitmap = gdi32.CreateDIBSection(ctypes.c_void_p(0), ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(ppv_bits), ctypes.c_void_p(0), 0)
            if not hbitmap or not hdc_mem:
                if hdc_mem:
                    gdi32.DeleteDC(ctypes.c_void_p(hdc_mem))
                user32.DestroyWindow(hwnd)
                # logger.info("show_highlight:create_dib_or_dc_failed", hdc_ok=bool(hdc_mem), hbitmap_ok=bool(hbitmap))
                return False

            old_obj = gdi32.SelectObject(ctypes.c_void_p(hdc_mem), ctypes.c_void_p(hbitmap))
            # try:
            #     logger.info("show_highlight:dc_bitmap_ready", hdc=int(hdc_mem), hbitmap=int(hbitmap))
            # except Exception:
            #     logger.info("show_highlight:dc_bitmap_ready")

            # 使用 PIL 绘制半透明红色圆圈，BGRA 顺序写入 DIB
            try:
                img = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                # 填充淡红 + 深红描边
                outline_width = max(2, int(diameter * 0.08))
                bbox = (outline_width // 2, outline_width // 2, diameter - outline_width // 2 - 1, diameter - outline_width // 2 - 1)
                draw.ellipse(bbox, fill=(255, 0, 0, 64), outline=(255, 0, 0, 220), width=outline_width)
                # 将像素写入 DIB（BGRA）
                buf = img.tobytes("raw", "BGRA")
                ctypes.memmove(ppv_bits, buf, len(buf))
                # logger.info("show_highlight:draw_pil_ok", outline_width=outline_width)
            except Exception:
                # 回退为简单边框，避免完全失败
                PS_SOLID = 0
                NULL_BRUSH = 5
                red = 0x000000FF
                pen = gdi32.CreatePen(PS_SOLID, 3, red)
                old_pen2 = gdi32.SelectObject(ctypes.c_void_p(hdc_mem), pen)
                old_brush2 = gdi32.SelectObject(ctypes.c_void_p(hdc_mem), gdi32.GetStockObject(NULL_BRUSH))
                gdi32.Ellipse(ctypes.c_void_p(hdc_mem), 1, 1, diameter - 1, diameter - 1)
                gdi32.SelectObject(ctypes.c_void_p(hdc_mem), old_pen2)
                gdi32.SelectObject(ctypes.c_void_p(hdc_mem), old_brush2)
                gdi32.DeleteObject(pen)
                # logger.info("show_highlight:draw_pil_failed_fallback_gdi")

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            class SIZE(ctypes.Structure):
                _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]

            class BLENDFUNCTION(ctypes.Structure):
                _fields_ = [
                    ("BlendOp", ctypes.c_ubyte),
                    ("BlendFlags", ctypes.c_ubyte),
                    ("SourceConstantAlpha", ctypes.c_ubyte),
                    ("AlphaFormat", ctypes.c_ubyte),
                ]

            ULW_ALPHA = 0x00000002
            AC_SRC_OVER = 0x00
            AC_SRC_ALPHA = 0x01

            pt_dst = POINT(left, top)
            sz = SIZE(diameter, diameter)
            pt_src = POINT(0, 0)
            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

            # 将位图作为分层窗口内容
            ok = user32.UpdateLayeredWindow(
                ctypes.c_void_p(hwnd),
                0,
                ctypes.byref(pt_dst),
                ctypes.byref(sz),
                ctypes.c_void_p(hdc_mem),
                ctypes.byref(pt_src),
                0,
                ctypes.byref(blend),
                ULW_ALPHA,
            )
            if not ok:
                # 清理
                gdi32.SelectObject(ctypes.c_void_p(hdc_mem), ctypes.c_void_p(old_obj))
                gdi32.DeleteObject(ctypes.c_void_p(hbitmap))
                gdi32.DeleteDC(ctypes.c_void_p(hdc_mem))
                user32.DestroyWindow(hwnd)
                # logger.info("show_highlight:update_layered_window_failed")
                return False
            # else:
                # logger.info("show_highlight:update_layered_window_ok")

            # 显示窗口
            SW_SHOW = 5
            user32.ShowWindow(ctypes.c_void_p(hwnd), SW_SHOW)
            # logger.info("show_highlight:show_window")

            # 保存当前高亮的窗口与 GDI 资源，供统一销毁
            try:
                prev_len = len(self._highlight_windows)
                self._highlight_windows.append({
                    'hwnd': int(hwnd),
                    'hdc': int(hdc_mem),
                    'hbitmap': int(hbitmap),
                    'old_obj': int(old_obj),
                    'x': int(x),
                    'y': int(y),
                    'radius': int(radius),
                })
                # logger.info("show_highlight:record_window", count_before=prev_len, count_after=len(self._highlight_windows))
            except Exception:
                # 如果无法记录，尽力清理避免泄露
                try:
                    gdi32.SelectObject(ctypes.c_void_p(hdc_mem), ctypes.c_void_p(old_obj))
                except Exception:
                    pass
                gdi32.DeleteObject(ctypes.c_void_p(hbitmap))
                gdi32.DeleteDC(ctypes.c_void_p(hdc_mem))
                user32.DestroyWindow(hwnd)
                # logger.info("show_highlight:record_window_failed_cleanup")
                return False
            self._highlight_state = (x, y, radius)
            # logger.info("show_highlight:success", state=self._highlight_state)
            return True
        except Exception:
            # try:
            #     import traceback
            #     logger.info("show_highlight:exception", err=traceback.format_exc())
            # except Exception:
            #     logger.info("show_highlight:exception")
            return False

    def hide_highlight(self):
        """销毁所有分层窗口，移除全部高亮。"""
        try:
            # logger.info("hide_highlight:start", windows_count=len(getattr(self, '_highlight_windows', [])))
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            windows = getattr(self, '_highlight_windows', [])
            if windows:
                for w in list(windows):
                    try:
                        hdc = ctypes.c_void_p(w.get('hdc') or 0)
                        hbmp = ctypes.c_void_p(w.get('hbitmap') or 0)
                        old_obj = ctypes.c_void_p(w.get('old_obj') or 0)
                        hwnd = ctypes.c_void_p(w.get('hwnd') or 0)
                        try:
                            # logger.info(
                            #     "hide_highlight:destroy_window_resources",
                            #     hwnd=int(hwnd.value or 0),
                            #     hdc=int(hdc.value or 0),
                            #     hbitmap=int(hbmp.value or 0),
                            # )
                            pass
                        except Exception:
                            # logger.info("hide_highlight:destroy_window_resources")
                            pass
                        if int(hdc.value or 0) != 0 and int(old_obj.value or 0) != 0:
                            try:
                                gdi32.SelectObject(hdc, old_obj)
                            except Exception:
                                pass
                        if int(hbmp.value or 0) != 0:
                            try:
                                gdi32.DeleteObject(hbmp)
                            except Exception:
                                pass
                        if int(hdc.value or 0) != 0:
                            try:
                                gdi32.DeleteDC(hdc)
                            except Exception:
                                pass
                        if int(hwnd.value or 0) != 0:
                            try:
                                user32.DestroyWindow(hwnd)
                            except Exception:
                                pass
                    except Exception:
                        pass
            self._highlight_windows = []
            self._highlight_state = None
            # logger.info("hide_highlight:done")
            return True
        except Exception:
            # try:
            #     import traceback
            #     logger.info("hide_highlight:exception", err=traceback.format_exc())
            # except Exception:
            #     logger.info("hide_highlight:exception")
            return False

    def show_highlight_rect(self, x1: int, y1: int, x2: int, y2: int):
        """备用：显示矩形高亮（未使用）。"""
        try:
            user32 = ctypes.windll.user32
            gdi32 = ctypes.windll.gdi32
            hdc = user32.GetDC(0)
            if not hdc:
                return False
            PS_SOLID = 0
            R2_NOTXORPEN = 10
            NULL_BRUSH = 5
            green = 0x0000FF00
            pen = gdi32.CreatePen(PS_SOLID, 2, green)
            old_pen = gdi32.SelectObject(hdc, pen)
            old_brush = gdi32.SelectObject(hdc, gdi32.GetStockObject(NULL_BRUSH))
            gdi32.SetROP2(hdc, R2_NOTXORPEN)
            gdi32.Rectangle(hdc, int(x1), int(y1), int(x2), int(y2))
            gdi32.SelectObject(hdc, old_pen)
            gdi32.SelectObject(hdc, old_brush)
            gdi32.DeleteObject(pen)
            user32.ReleaseDC(0, hdc)
            return True
        except Exception:
            return False

    def hide_highlight_rect(self, x1: int, y1: int, x2: int, y2: int):
        try:
            return bool(self.show_highlight_rect(x1, y1, x2, y2))
        except Exception:
            return False

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
        # Windows Action Center 可用 Win + A 快捷键
        if not self.keyboard:
            raise RuntimeError("pynput not available")
        self.keyboard.press(Key.cmd)
        self.keyboard.press('a')
        self.keyboard.release('a')
        self.keyboard.release(Key.cmd)
        return True

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
                'win': Key.cmd,  # Windows 中 cmd 映射为 win 键
                'cmd': Key.cmd,  # 也支持 cmd 别名
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
                'pause': Key.pause,
                'print_screen': Key.print_screen,
                'printscreen': Key.print_screen,
                'menu': Key.menu,
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

    def get_width_height(self) -> Tuple[int, int]:
        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))

    # ======= UI Tree & Snap Click =======
    def get_ui_tree(self) -> List[Dict]:
        """
        返回当前屏幕的简化 UI 树结构（Windows）
        字段对齐 websocket_device 的使用：
        - temp_id: 节点ID
        - bounds: [(x1,y1),(x2,y2)]
        - clickable: bool
        - visible: bool
        - enabled: bool
        - children: [temp_id,...]
        - class: 控件类型
        - resource_id: AutomationId
        """
        if auto is None:
            return []
        try:
            with auto.UIAutomationInitializerInThread():
                root = auto.GetRootControl()
        except Exception:
            try:
                root = auto.GetRootControl()
            except Exception:
                return []
        nodes: List[Dict] = []
        id_counter = [0]
        def next_id() -> int:
            id_counter[0] += 1
            return id_counter[0]
        def rect_to_bounds(rect) -> Tuple[Tuple[int,int],Tuple[int,int]]:
            try:
                return (int(rect.left), int(rect.top)), (int(rect.right), int(rect.bottom))
            except Exception:
                return ((0,0),(0,0))
        def is_visible(c) -> bool:
            try:
                r = c.BoundingRectangle
                if r is None:
                    return False
                w = max(0, int(r.right) - int(r.left))
                h = max(0, int(r.bottom) - int(r.top))
                return (not c.IsOffscreen) and w > 0 and h > 0
            except Exception:
                return False
        def is_clickable(c) -> bool:
            try:
                t = c.ControlTypeName or ''
                invokable = False
                try:
                    invokable = c.GetPattern(auto.PatternId.InvokePatternId) is not None
                except Exception:
                    invokable = False
                return (t in ClickableTypes) or invokable
            except Exception:
                return False
        def build_node(c) -> int:
            nid = next_id()
            try:
                rect = c.BoundingRectangle
                bounds = rect_to_bounds(rect) if rect else ((0,0),(0,0))
                node = {
                    'temp_id': nid,
                    'bounds': bounds,
                    'clickable': is_clickable(c),
                    'visible': is_visible(c),
                    'enabled': bool(c.IsEnabled),
                    'children': [],
                    'class': c.ControlTypeName or '',
                    'resource_id': getattr(c, 'AutomationId', '') or ''
                }
                nodes.append(node)
                # 限制深度与数量，避免过大
                children = []
                try:
                    children = c.GetChildren()
                except Exception:
                    children = []
                for ch in children[:50]:
                    child_id = build_node(ch)
                    node['children'].append(child_id)
            except Exception:
                pass
            return nid
        build_node(root)
        return nodes

    def _distance(self, x1, y1, x2, y2) -> float:
        dx = x1 - x2
        dy = y1 - y2
        return (dx*dx + dy*dy) ** 0.5

    def _pick_nearest_clickable(self, ui_tree: List[Dict], x: int, y: int) -> Optional[Dict]:
        candidates = [e for e in ui_tree if e.get('visible') and e.get('enabled')]
        clickable = [e for e in candidates if e.get('clickable')]
        def center(b):
            (x1,y1),(x2,y2) = b
            return ( (x1+x2)//2, (y1+y2)//2 )
        best = None
        best_dist = float('inf')
        pool = clickable if clickable else candidates
        for e in pool:
            b = e.get('bounds')
            if not b or not isinstance(b, (list, tuple)):
                continue
            cx, cy = center(b)
            dist = self._distance(cx, cy, x, y)
            # 优先考虑点在元素内
            inside = (b[0][0] <= x <= b[1][0]) and (b[0][1] <= y <= b[1][1])
            if inside:
                dist *= 0.1
            if dist < best_dist:
                best = e
                best_dist = dist
        return best

    def snap_click(self, x: int, y: int, duration: int = 200):
        try:
            ui_tree = self.get_ui_tree()
            if not ui_tree:
                return self.click(x, y, duration)
            target = self._pick_nearest_clickable(ui_tree, x, y)
            if not target:
                return self.click(x, y, duration)
            (x1,y1),(x2,y2) = target.get('bounds', ((x,y),(x,y)))
            cx, cy = ( (x1+x2)//2, (y1+y2)//2 )
            return self.click(cx, cy, duration)
        except Exception:
            return self.click(x, y, duration)

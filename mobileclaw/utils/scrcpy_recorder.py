"""
Native scrcpy Video Recording Service

This service provides a Python wrapper around the native scrcpy command-line tool
for high-performance video recording of Android devices.
"""

import os
import subprocess
import signal
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
import structlog

logger = structlog.get_logger()


class ScrcpyRecorder:
    """
    Python wrapper for native scrcpy video recording

    Provides high-performance video recording by directly using the scrcpy command-line tool
    instead of frame-by-frame capture methods.
    """

    # Recording quality presets
    RECORDING_PRESETS = {
        'low': {
            'max_size': '720',
            'max_fps': '15',
            'video_bitrate': '2M',
            'description': 'Low quality - maximum performance'
        },
        'medium': {
            'max_size': '1080',
            'max_fps': '30',
            'video_bitrate': '4M',
            'description': 'Medium quality - balanced performance'
        },
        'high': {
            'max_size': '1920',
            'max_fps': '60',
            'video_bitrate': '8M',
            'description': 'High quality - maximum quality'
        }
    }

    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.recording_file: Optional[str] = None
        self.is_recording: bool = False
        self.start_time: Optional[float] = None
        self.stop_time: Optional[float] = None
        self.device_id: Optional[str] = None
        self.scrcpy_path: Optional[str] = None
        self.recording_thread: Optional[threading.Thread] = None
        self.error_occurred: bool = False
        self.error_message: Optional[str] = None

        # Auto-detect scrcpy installation
        self._detect_scrcpy()

    def _detect_scrcpy(self) -> bool:
        """
        Detect scrcpy installation on the system

        Returns:
            bool: True if scrcpy is found and usable
        """
        try:
            # Common scrcpy installation paths
            scrcpy_paths = [
                'scrcpy',  # In PATH
                '/usr/local/bin/scrcpy',
                '/usr/bin/scrcpy',
                '/opt/homebrew/bin/scrcpy',
                '/Applications/scrcpy.app/Contents/MacOS/scrcpy',
                'C:\\Program Files\\scrcpy\\scrcpy.exe',
                'C:\\scrcpy\\scrcpy.exe'
            ]

            for path in scrcpy_paths:
                try:
                    # Test if scrcpy is available and working
                    result = subprocess.run(
                        [path, '--version'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        self.scrcpy_path = path
                        # logger.info(f"✅ Found scrcpy at: {path}")
                        # logger.info(f"📋 scrcpy version: {result.stdout.strip()}")
                        return True
                except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
                    continue

            logger.warning("❌ scrcpy not found in system PATH or common installation locations")
            self.scrcpy_path = None
            return False

        except Exception as e:
            logger.error(f"❌ Error detecting scrcpy: {str(e)}")
            self.scrcpy_path = None
            return False

    def is_available(self) -> bool:
        """Check if scrcpy recording is available"""
        return self.scrcpy_path is not None

    def get_scrcpy_info(self) -> Dict[str, Any]:
        """Get information about scrcpy installation"""
        if not self.scrcpy_path:
            return {
                'available': False,
                'path': None,
                'version': None,
                'error': 'scrcpy not found'
            }

        try:
            result = subprocess.run(
                [self.scrcpy_path, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return {
                'available': True,
                'path': self.scrcpy_path,
                'version': result.stdout.strip() if result.returncode == 0 else 'Unknown',
                'error': None
            }
        except Exception as e:
            return {
                'available': False,
                'path': self.scrcpy_path,
                'version': None,
                'error': str(e)
            }

    def start_recording(
        self,
        output_path: str,
        device_id: Optional[str] = None,
        quality: str = 'medium',
        max_duration: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Start recording using native scrcpy

        Args:
            output_path: Output video file path
            device_id: Target device serial number
            quality: Recording quality preset ('low', 'medium', 'high')
            max_duration: Maximum recording duration in seconds
            **kwargs: Additional recording options

        Returns:
            str: The output file path

        Raises:
            RuntimeError: If scrcpy is not available or recording fails to start
            ValueError: If invalid parameters provided
        """
        if not self.scrcpy_path:
            raise RuntimeError("scrcpy is not available on this system")

        if self.is_recording:
            raise RuntimeError("Recording is already in progress")

        if quality not in self.RECORDING_PRESETS:
            raise ValueError(f"Invalid quality '{quality}'. Must be one of: {list(self.RECORDING_PRESETS.keys())}")

        # Ensure output directory exists
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build scrcpy command
        cmd = self._build_scrcpy_command(
            output_path=str(output_path),
            device_id=device_id,
            quality=quality,
            max_duration=max_duration,
            **kwargs
        )

        # logger.info(f"🎬 Starting scrcpy recording: {' '.join(cmd)}")
        # logger.info(f"📁 Output file: {output_path}")
        # logger.info(f"📱 Device: {device_id or 'default'}")
        # logger.info(f"⚙️ Quality preset: {quality}")

        try:
            # Start scrcpy process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid if os.name != 'nt' else None  # Create new process group
            )

            self.recording_file = str(output_path)
            self.device_id = device_id
            self.is_recording = True
            self.start_time = time.time()
            self.error_occurred = False
            self.error_message = None

            # Start monitoring thread
            self.recording_thread = threading.Thread(target=self._monitor_recording, daemon=True)
            self.recording_thread.start()

            # Wait a moment to ensure recording started successfully
            time.sleep(1.0)

            if self.process.poll() is not None:
                # Process terminated immediately
                stdout, stderr = self.process.communicate()
                error_msg = stderr or stdout or "Unknown error"
                raise RuntimeError(f"scrcpy failed to start: {error_msg}")

            # logger.info("✅ scrcpy recording started successfully")
            return self.recording_file

        except Exception as e:
            self.is_recording = False
            if self.process:
                self.process.terminate()
                self.process = None
            raise RuntimeError(f"Failed to start scrcpy recording: {str(e)}")

    def _build_scrcpy_command(
        self,
        output_path: str,
        device_id: Optional[str] = None,
        quality: str = 'medium',
        max_duration: Optional[int] = None,
        **kwargs
    ) -> List[str]:
        """Build scrcpy command with appropriate options"""
        cmd = [self.scrcpy_path]

        # Device selection
        if device_id:
            cmd.extend(['--serial', device_id])

        # Recording options
        cmd.extend(['--record', output_path])
        cmd.extend(['--no-window'])  # Background recording
        cmd.extend(['--no-cleanup'])  # Don't cleanup server binary

        # Quality preset
        preset = self.RECORDING_PRESETS[quality]
        cmd.extend(['--max-size', preset['max_size']])
        cmd.extend(['--max-fps', preset['max_fps']])
        cmd.extend(['--video-bit-rate', preset['video_bitrate']])

        # Additional options
        if max_duration:
            cmd.extend(['--time-limit', str(max_duration)])

        # Custom options from kwargs
        custom_options = {
            'record_format': kwargs.get('record_format'),
            'record_orientation': kwargs.get('record_orientation'),
            'video_codec': kwargs.get('video_codec'),
            'video_encoder': kwargs.get('video_encoder'),
            'show_touches': kwargs.get('show_touches', False),
            'stay_awake': kwargs.get('stay_awake', True),
            'power_off_on_close': kwargs.get('power_off_on_close', False)
        }

        for option, value in custom_options.items():
            if value is not None:
                if isinstance(value, bool):
                    if value:
                        cmd.extend([f'--{option.replace("_", "-")}'])
                else:
                    cmd.extend([f'--{option.replace("_", "-")}', str(value)])

        return cmd

    def stop_recording(self) -> Optional[str]:
        """
        Stop recording gracefully

        Returns:
            Optional[str]: The recorded file path if successful, None otherwise
        """
        if not self.is_recording or not self.process:
            logger.warning("No recording in progress to stop")
            return None

        # logger.info("⏹️ Stopping scrcpy recording...")

        try:
            self.stop_time = time.time()
            self.is_recording = False

            # Send SIGTERM to gracefully stop recording
            if os.name == 'nt':
                # Windows
                self.process.terminate()
            else:
                # Unix-like systems - send to process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

            # Wait for process to finish (with timeout)
            try:
                stdout, stderr = self.process.communicate(timeout=10)

                if self.process.returncode == 0:
                    # logger.info("✅ scrcpy recording stopped successfully")
                    # logger.info(f"📁 Output file: {self.recording_file}")
                    return self.recording_file
                else:
                    error_msg = stderr or stdout or "Unknown error"
                    logger.warning(f"⚠️ scrcpy stopped with code {self.process.returncode}: {error_msg}")
                    # Still return file path as it might be valid
                    return self.recording_file

            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown failed
                logger.warning("⚠️ scrcpy did not stop gracefully, force killing...")
                if os.name == 'nt':
                    self.process.kill()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                self.process.wait()
                return self.recording_file

        except Exception as e:
            logger.error(f"❌ Error stopping scrcpy recording: {str(e)}")
            return None
        finally:
            self.process = None

    def _monitor_recording(self):
        """Monitor recording process for errors and status"""
        if not self.process:
            return

        try:
            # Monitor process
            while self.is_recording and self.process.poll() is None:
                time.sleep(0.5)

            if self.is_recording and self.process.poll() is not None:
                # Process ended unexpectedly
                self.error_occurred = True
                self.is_recording = False
                self.stop_time = time.time()

                stdout, stderr = self.process.communicate()
                self.error_message = stderr or stdout or "Process terminated unexpectedly"
                logger.error(f"❌ scrcpy recording failed: {self.error_message}")

        except Exception as e:
            self.error_occurred = True
            self.error_message = str(e)
            logger.error(f"❌ Error monitoring scrcpy recording: {str(e)}")

    def is_active(self) -> bool:
        """Check if recording is currently active"""
        return self.is_recording and self.process and self.process.poll() is None

    def get_recording_stats(self) -> Dict[str, Any]:
        """Get current recording statistics"""
        stats = {
            'is_recording': self.is_active(),
            'file_path': self.recording_file,
            'start_time': self.start_time,
            'stop_time': self.stop_time,
            'duration': None,
            'file_size': None,
            'error_occurred': self.error_occurred,
            'error_message': self.error_message
        }

        if self.start_time:
            if self.stop_time:
                stats['duration'] = self.stop_time - self.start_time
            else:
                stats['duration'] = time.time() - self.start_time

        if self.recording_file and os.path.exists(self.recording_file):
            stats['file_size'] = os.path.getsize(self.recording_file)

        return stats

    def get_available_devices(self) -> List[str]:
        """Get list of available Android devices via adb"""
        try:
            result = subprocess.run(
                ['adb', 'devices'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
                devices = []
                for line in lines:
                    if line.strip():
                        device_id = line.split('\t')[0]
                        if device_id:
                            devices.append(device_id)
                return devices
            else:
                logger.warning(f"Failed to get devices: {result.stderr}")
                return []

        except Exception as e:
            logger.error(f"Error getting devices: {str(e)}")
            return []

    def test_device_connection(self, device_id: Optional[str] = None) -> bool:
        """Test if a device is connected and accessible"""
        try:
            cmd = ['adb']
            if device_id:
                cmd.extend(['-s', device_id])
            cmd.extend(['shell', 'echo', 'test'])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )

            return result.returncode == 0 and 'test' in result.stdout

        except Exception as e:
            logger.error(f"Error testing device connection: {str(e)}")
            return False

    def get_quality_presets(self) -> Dict[str, Dict[str, str]]:
        """Get available recording quality presets"""
        return self.RECORDING_PRESETS.copy()

    def cleanup(self):
        """Clean up resources"""
        if self.is_recording:
            self.stop_recording()

        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception as _:
                try:
                    self.process.kill()
                except Exception as _:
                    pass
            finally:
                self.process = None
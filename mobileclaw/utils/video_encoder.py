"""
Video Encoder Service

This module provides high-quality video encoding functionality for converting
captured frames into MP4 video files. The service prioritizes maximum quality
and compatibility across different platforms.
"""

import os
import structlog
import tempfile
import shutil
from typing import List, Dict, Any, Optional
from PIL import Image
import numpy as np

logger = structlog.get_logger(__name__)

class VideoEncoderService:
    """High-quality video encoding service for recordings."""
    
    def __init__(self):
        """Initialize the video encoder service."""
        self.temp_dir = None
        
    def encode_frames_to_video(self, frames: List[Dict[str, Any]], output_path: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Encode captured frames into a high-quality MP4 video.
        
        Args:
            frames: List of frame dictionaries containing 'image', 'timestamp', and 'frame_number'
            output_path: Output video file path
            metadata: Optional recording metadata to include in video
            
        Returns:
            str: Path to the encoded video file
            
        Raises:
            ValueError: If no frames provided or invalid output path
            RuntimeError: If encoding fails
        """
        if not frames:
            raise ValueError("No frames provided for encoding")
            
        if not output_path:
            raise ValueError("Output path must be specified")
            
        logger.info(f"Starting to encode {len(frames)} frames to video: {output_path}")

        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            try:
                return self._encode_with_opencv(frames, output_path, metadata)
            except ImportError:
                logger.warning("OpenCV not available, falling back to imageio")
            except Exception as e:
                logger.warning(f"OpenCV encoding failed: {e}, falling back to imageio")

            try:
                return self._encode_with_imageio(frames, output_path, metadata)
            except ImportError:
                logger.warning("imageio-ffmpeg not available, falling back to PIL sequence")
            except Exception as e:
                logger.warning(f"imageio encoding failed: {e}, falling back to PIL sequence")

            try:
                return self._encode_with_pil_and_ffmpeg(frames, output_path, metadata)
            except Exception as e:
                logger.error(f"PIL + ffmpeg encoding failed: {e}")

            raise RuntimeError("All encoding methods failed. Please install OpenCV or imageio-ffmpeg.")

        except Exception as e:
            logger.error(f"Video encoding failed: {str(e)}")
            raise RuntimeError(f"Video encoding failed: {str(e)}")
            
    def _encode_with_opencv(self, frames: List[Dict[str, Any]], output_path: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Encode video using OpenCV for maximum quality.

        Args:
            frames: List of frame dictionaries.
            output_path: Output video file path.
            metadata: Optional recording metadata.

        Returns:
            str: Path to the encoded video file.

        Raises:
            ValueError: If frames are invalid.
            RuntimeError: If encoding fails.
        """
        import cv2

        if not frames:
            raise ValueError("No frames to encode")

        # Get dimensions from first frame
        first_frame = frames[0]['image']
        if hasattr(first_frame, 'size'):
            width, height = first_frame.size
        elif hasattr(first_frame, 'shape'):
            height, width = first_frame.shape[:2]
        else:
            raise ValueError("Unable to determine frame dimensions")

        fps = self._calculate_fps(frames)

        codec_options = [
            ('avc1', 'AVC1 (H.264) - Most compatible MP4 codec'),
            ('mp4v', 'MP4V - MP4 container native codec'),
            ('X264', 'x264 - Open source H.264 encoder'),
            ('H264', 'H264 - Original codec (may show warnings)'),
            ('DIVX', 'DIVX - Fallback codec'),
            ('MJPG', 'MJPG - Motion JPEG fallback')
        ]

        out = None
        used_codec = None

        for codec_name, description in codec_options:
            try:
                logger.debug(f"Trying codec: {codec_name} - {description}")
                fourcc = cv2.VideoWriter_fourcc(*codec_name)
                test_writer = cv2.VideoWriter(output_path + '.test', fourcc, fps, (width, height))

                if test_writer.isOpened():
                    test_writer.release()
                    import os
                    if os.path.exists(output_path + '.test'):
                        os.remove(output_path + '.test')

                    fourcc = cv2.VideoWriter_fourcc(*codec_name)
                    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
                    used_codec = codec_name
                    logger.info(f"Using codec: {codec_name} - {description}")
                    break
                else:
                    test_writer.release()
                    logger.debug(f"Codec {codec_name} not available")

            except Exception as e:
                logger.debug(f"Codec {codec_name} failed: {str(e)}")
                continue

        if out is None or not out.isOpened():
            raise RuntimeError("No compatible video codec found. Please install OpenCV with video codec support.")

        try:
            frame_count = 0
            for frame_data in frames:
                image = frame_data['image']

                if hasattr(image, 'convert'):
                    image = image.convert('RGB')
                    frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                elif isinstance(image, np.ndarray):
                    if len(image.shape) == 3 and image.shape[2] == 3:
                        frame = image
                    elif len(image.shape) == 2:
                        frame = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
                    else:
                        frame = image
                else:
                    raise ValueError(f"Unsupported image format: {type(image)}")

                if frame.shape[:2] != (height, width):
                    frame = cv2.resize(frame, (width, height))

                out.write(frame)
                frame_count += 1

                if frame_count % 100 == 0:
                    logger.debug(f"Encoded {frame_count}/{len(frames)} frames")

        finally:
            out.release()

        if metadata:
            self._embed_metadata_with_ffmpeg(output_path, metadata)

        if not os.path.exists(output_path):
            raise RuntimeError("Video file was not created")

        file_size = os.path.getsize(output_path)
        avg_frame_size = file_size / len(frames) if len(frames) > 0 else 0

        logger.info(f"OpenCV encoding complete: {output_path}")
        logger.info(f"   Encoding stats: {len(frames)} frames, {fps:.1f} FPS, {file_size:,} bytes")
        logger.info(f"   Using encoder: {used_codec}")
        logger.info(f"   Average frame size: {avg_frame_size:,.0f} bytes")

        return output_path
        
    def _encode_with_imageio(self, frames: List[Dict[str, Any]], output_path: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Encode video using imageio-ffmpeg.

        Args:
            frames: List of frame dictionaries.
            output_path: Output video file path.
            metadata: Optional recording metadata.

        Returns:
            str: Path to the encoded video file.

        Raises:
            ValueError: If frames are invalid.
            RuntimeError: If encoding fails.
        """
        import imageio
        
        if not frames:
            raise ValueError("No frames to encode")

        frame_arrays = []
        for frame_data in frames:
            image = frame_data['image']

            if hasattr(image, 'convert'):
                image = image.convert('RGB')
                frame_arrays.append(np.array(image))
            elif isinstance(image, np.ndarray):
                if len(image.shape) == 2:
                    frame_arrays.append(np.stack([image] * 3, axis=-1))
                else:
                    frame_arrays.append(image)
            else:
                raise ValueError(f"Unsupported image format: {type(image)}")

        fps = self._calculate_fps(frames)

        imageio.mimsave(output_path, frame_arrays, fps=fps, quality=10, macro_block_size=1)

        if metadata:
            self._embed_metadata_with_ffmpeg(output_path, metadata)

        if not os.path.exists(output_path):
            raise RuntimeError("Video file was not created")

        file_size = os.path.getsize(output_path)
        logger.info(f"ImageIO encoding complete: {output_path} ({len(frames)} frames, {fps:.1f} FPS, {file_size:,} bytes)")

        return output_path
        
    def _encode_with_pil_and_ffmpeg(self, frames: List[Dict[str, Any]], output_path: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Basic encoding using PIL to save frames and ffmpeg to combine.

        Args:
            frames: List of frame dictionaries.
            output_path: Output video file path.
            metadata: Optional recording metadata.

        Returns:
            str: Path to the encoded video file.

        Raises:
            RuntimeError: If encoding fails.
        """
        self.temp_dir = tempfile.mkdtemp(prefix='my_recording_')

        try:
            frame_files = []
            for i, frame_data in enumerate(frames):
                image = frame_data['image']

                if hasattr(image, 'convert'):
                    image = image.convert('RGB')

                frame_path = os.path.join(self.temp_dir, f'frame_{i:06d}.png')
                image.save(frame_path, 'PNG', optimize=False)
                frame_files.append(frame_path)

            fps = self._calculate_fps(frames)

            import subprocess

            cmd = [
                'ffmpeg',
                '-y',
                '-framerate', str(fps),
                '-i', os.path.join(self.temp_dir, 'frame_%06d.png'),
                '-c:v', 'libx264',
                '-preset', 'slow',
                '-crf', '18',
                '-pix_fmt', 'yuv420p',
                output_path
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            if metadata:
                self._embed_metadata_with_ffmpeg(output_path, metadata)

            if not os.path.exists(output_path):
                raise RuntimeError("Video file was not created")

            file_size = os.path.getsize(output_path)
            logger.info(f"PIL+FFmpeg encoding complete: {output_path} ({len(frames)} frames, {fps:.1f} FPS, {file_size:,} bytes)")

            return output_path

        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.temp_dir = None
                
    def _calculate_fps(self, frames: List[Dict[str, Any]]) -> float:
        """Calculate optimal FPS based on frame timestamps.

        Args:
            frames: List of frame dictionaries with timestamps.

        Returns:
            float: Calculated FPS value, limited to 1-60 FPS range.
        """
        if len(frames) < 2:
            return 10.0

        timestamps = [frame['timestamp'] for frame in frames]

        time_diffs = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]

        if not time_diffs or sum(time_diffs) == 0:
            return 10.0

        avg_interval = sum(time_diffs) / len(time_diffs)

        fps = 1.0 / avg_interval if avg_interval > 0 else 10.0
        fps = max(1.0, min(fps, 60.0))

        return fps
        
    def _embed_metadata_with_ffmpeg(self, video_path: str, metadata: Dict[str, Any]) -> None:
        """Embed metadata into video file using ffmpeg with safe in-place editing.
        
        Args:
            video_path: Path to the video file
            metadata: Dictionary of metadata to embed
        """
        try:
            import subprocess

            if video_path.lower().endswith('.mp4'):
                if video_path.endswith('.mp4'):
                    temp_path = video_path[:-4] + '_temp.mp4'
                elif video_path.endswith('.MP4'):
                    temp_path = video_path[:-4] + '_temp.MP4'
                else:
                    temp_path = video_path[:-4].lower() + '_temp.mp4'
            else:
                temp_path = video_path + '_temp'

            cmd = [
                'ffmpeg',
                '-y',
                '-i', video_path,
                '-c', 'copy',
            ]

            if 'task_name' in metadata:
                cmd.extend(['-metadata', f"title={metadata['task_name']}"])
            if 'start_time_iso' in metadata:
                import datetime
                try:
                    iso_time = metadata['start_time_iso']
                    dt = datetime.datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
                    timestamp_int = int(dt.timestamp())
                    cmd.extend(['-metadata', f"creation_time={timestamp_int}"])
                except Exception:
                    cmd.extend(['-metadata', f"creation_time={metadata['start_time_iso']}"])
            if 'device_name' in metadata:
                cmd.extend(['-metadata', f"comment=Device: {metadata['device_name']}"])
            if 'duration_seconds' in metadata:
                cmd.extend(['-metadata', f"duration={metadata['duration_seconds']:.2f}"])
            if 'frame_count' in metadata:
                cmd.extend(['-metadata', f"frame_count={metadata['frame_count']}"])

            description_parts = []
            if 'task_name' in metadata:
                description_parts.append(f"Task: {metadata['task_name']}")
            if 'device_type' in metadata:
                description_parts.append(f"Device: {metadata['device_type']}")
            if 'device_name' in metadata:
                description_parts.append(f"Name: {metadata['device_name']}")
            if 'start_time_iso' in metadata:
                import datetime
                try:
                    iso_time = metadata['start_time_iso']
                    dt = datetime.datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
                    timestamp_int = int(dt.timestamp())
                    description_parts.append(f"Start: {timestamp_int}")
                except Exception:
                    description_parts.append(f"Start: {metadata['start_time_iso']}")
            if 'stop_time_iso' in metadata and metadata['stop_time_iso']:
                import datetime
                try:
                    iso_time = metadata['stop_time_iso']
                    dt = datetime.datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
                    timestamp_int = int(dt.timestamp())
                    description_parts.append(f"Stop: {timestamp_int}")
                except Exception:
                    description_parts.append(f"Stop: {metadata['stop_time_iso']}")
            if 'duration_seconds' in metadata:
                description_parts.append(f"Duration: {metadata['duration_seconds']:.2f}s")

            if description_parts:
                description = " | ".join(description_parts)
                cmd.extend(['-metadata', f"description={description}"])

            cmd.append(temp_path)

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0 and os.path.exists(temp_path):
                try:
                    os.replace(temp_path, video_path)
                    logger.debug(f"Successfully embedded metadata into video: {video_path}")
                except Exception as replace_error:
                    logger.error(f"Failed to replace video file: {replace_error}")
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
            else:
                logger.warning(f"Failed to embed metadata: {result.stderr}")
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Failed to embed metadata in video: {str(e)}")

    def cleanup(self):
        """Clean up temporary files and resources."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None

import logging
import subprocess

logger = logging.getLogger(__name__)


class DebugScreenRecorder:
    def __init__(self, display_var, screen_dimensions, output_file_path):
        self.display_var = display_var
        self.screen_dimensions = screen_dimensions
        self.output_file_path = output_file_path
        self.ffmpeg_proc = None

    def start(self):
        logger.info(f"Starting debug screen recorder for display {self.display_var} with dimensions {self.screen_dimensions} and output file path {self.output_file_path}")
        self.ffmpeg_proc = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-f",
                "x11grab",
                "-video_size",
                f"{self.screen_dimensions[0]}x{self.screen_dimensions[1]}",
                "-i",
                self.display_var,
                "-r",
                "15",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                self.output_file_path,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop(self):
        if not self.ffmpeg_proc:
            return

        # Ask ffmpeg to quit gracefully so MP4 metadata is finalized.
        try:
            logger.info("Trying to gracefully quit ffmpeg...")
            if self.ffmpeg_proc.stdin:
                self.ffmpeg_proc.stdin.write(b"q")
                self.ffmpeg_proc.stdin.flush()
            self.ffmpeg_proc.wait(timeout=10)
        except Exception:
            try:
                self.ffmpeg_proc.terminate()
                self.ffmpeg_proc.wait(timeout=5)
            except Exception:
                self.ffmpeg_proc.kill()
                self.ffmpeg_proc.wait()

        logger.info(f"Stopped debug screen recorder for display {self.display_var} with dimensions {self.screen_dimensions} and output file path {self.output_file_path}")
        self.ffmpeg_proc = None

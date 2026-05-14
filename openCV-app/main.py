from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk

from PIL import Image, ImageTk
from moviepy import VideoFileClip
from proglog import ProgressBarLogger


QUALITY_BITRATES = {
    "Low - 800k": "800k",
    "Medium - 1500k": "1500k",
    "High - 3000k": "3000k",
    "Keep close to source": None,
}


class ConversionProgressLogger(ProgressBarLogger):
    def __init__(self, on_progress) -> None:
        super().__init__()
        self.on_progress = on_progress
        self.started_at = time.monotonic()

    def bars_callback(self, bar, attr, value, old_value=None) -> None:
        # MoviePy reports audio chunks and video frames separately. Track only
        # the video frame bar so the GUI progress does not run twice.
        if bar != "frame_index":
            return
        if attr != "index":
            return

        total = self.bars.get(bar, {}).get("total")
        if not total:
            return

        progress = min(max(value / total, 0), 1)
        elapsed = time.monotonic() - self.started_at
        eta = elapsed * (1 - progress) / progress if progress > 0 else None
        self.on_progress(progress, eta)


class VideoConverterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MP4 Video Converter")
        self.geometry("920x720")
        self.minsize(840, 660)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.quality = tk.StringVar(value="Low - 800k")
        self.fps = tk.StringVar(value="30")
        self.output_size = tk.StringVar(value="Original")
        self.trim_start = tk.StringVar(value="0.00")
        self.trim_end = tk.StringVar()
        self.status = tk.StringVar(value="Ready")
        self.preview_summary = tk.StringVar(value="Select an MP4 file to preview details.")
        self.trim_summary = tk.StringVar(value="Trim: 0.00s - end")

        self.video_duration = 0.0
        self.source_fps = 0.0
        self.source_width = 0
        self.source_height = 0
        self.source_bitrate_kbps = 0.0
        self.size_presets: dict[str, tuple[int, int]] = {}
        self._active_handle: str | None = None
        self._last_preview_path = ""
        self._preview_after_id: str | None = None
        self._frame_preview_after_id: str | None = None
        self._frame_preview_token = 0
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._syncing_trim = False
        self._layout_after_id: str | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        root = ttk.Frame(self, padding=16)
        self.root_frame = root
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        title = ttk.Label(root, text="MP4 Video Converter", font=("", 16, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 14))

        file_frame = ttk.Frame(root)
        file_frame.grid(row=1, column=0, sticky="ew")
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="Input MP4").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(file_frame, textvariable=self.input_path).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(file_frame, text="Browse", command=self.select_input).grid(row=0, column=2, sticky="ew")

        ttk.Label(file_frame, text="Output MP4").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(file_frame, textvariable=self.output_path).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(file_frame, text="Save As", command=self.select_output).grid(row=1, column=2, sticky="ew")

        content = ttk.Frame(root)
        self.content_frame = content
        content.grid(row=2, column=0, sticky="nsew", pady=(16, 8))
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=0)
        content.rowconfigure(1, weight=1, minsize=210)

        preview = ttk.LabelFrame(content, text="Input Preview", padding=12)
        preview.grid(row=0, column=0, columnspan=2, sticky="ew")
        preview.columnconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(
            preview,
            width=320,
            height=150,
            bg="#202020",
            highlightthickness=1,
            highlightbackground="#999999",
        )
        self.preview_canvas.grid(row=0, column=0, sticky="ew")
        self.preview_canvas.create_text(160, 90, text="No preview", fill="#eeeeee")

        ttk.Label(preview, textvariable=self.preview_summary, justify="left").grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(10, 0),
        )

        options = ttk.LabelFrame(content, text="Conversion Settings", padding=12)
        options.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(12, 0))
        options.columnconfigure(1, weight=1)
        options.columnconfigure(3, weight=1)

        ttk.Label(options, text="Quality").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(
            options,
            textvariable=self.quality,
            values=list(QUALITY_BITRATES),
            state="readonly",
        ).grid(row=0, column=1, columnspan=3, sticky="ew", padx=8)

        ttk.Label(options, text="FPS").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(options, textvariable=self.fps, width=12).grid(row=1, column=1, sticky="ew", padx=8)

        ttk.Label(options, text="Output size").grid(row=2, column=0, sticky="w", pady=6)
        self.size_combo = ttk.Combobox(
            options,
            textvariable=self.output_size,
            values=["Original"],
            state="readonly",
        )
        self.size_combo.grid(row=2, column=1, columnspan=3, sticky="ew", padx=8)

        trim_box = ttk.LabelFrame(content, text="Trim Timeline", padding=12)
        self.trim_box = trim_box
        trim_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(12, 0))
        trim_box.columnconfigure(1, weight=1)
        trim_box.columnconfigure(3, weight=1)
        trim_box.rowconfigure(1, weight=1, minsize=126)

        ttk.Label(trim_box, text="Start sec").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(trim_box, textvariable=self.trim_start, width=12).grid(row=0, column=1, sticky="ew", padx=8)

        ttk.Label(trim_box, text="End sec").grid(row=0, column=2, sticky="w", pady=6, padx=(12, 0))
        ttk.Entry(trim_box, textvariable=self.trim_end, width=12).grid(row=0, column=3, sticky="ew", padx=8)

        self.timeline = tk.Canvas(
            trim_box,
            height=126,
            bg="#f7f8fa",
            highlightthickness=1,
            highlightbackground="#c9ced6",
        )
        self.timeline.grid(row=1, column=0, columnspan=4, sticky="nsew", pady=(10, 6))
        self.timeline.bind("<Configure>", lambda _event: self._draw_timeline())
        self.timeline.bind("<Button-1>", self._on_timeline_press)
        self.timeline.bind("<B1-Motion>", self._on_timeline_drag)
        self.timeline.bind("<ButtonRelease-1>", self._on_timeline_release)

        ttk.Label(trim_box, textvariable=self.trim_summary).grid(row=2, column=0, columnspan=4, sticky="w")

        self.trim_start.trace_add("write", self._on_trim_entry_changed)
        self.trim_end.trace_add("write", self._on_trim_entry_changed)
        self.input_path.trace_add("write", self._schedule_input_preview)

        hint = ttk.Label(
            root,
            text="Drag timeline handles or type seconds directly. Leave end empty to export until the original end.",
            foreground="#555555",
        )
        hint.grid(row=3, column=0, sticky="w", pady=(8, 12))

        self.convert_button = ttk.Button(root, text="Convert", command=self.start_conversion)
        self.convert_button.grid(row=4, column=0, sticky="ew", pady=(6, 12))

        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.progress.grid(row=5, column=0, sticky="ew")

        ttk.Label(root, textvariable=self.status).grid(row=6, column=0, sticky="w", pady=(10, 0))
        self.bind("<Configure>", self._schedule_layout_refresh)
        self._draw_timeline()
        self.after(80, self._refresh_dynamic_layout)

    def select_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Select MP4 file",
            filetypes=[("MP4 files", "*.mp4"), ("All files", "*.*")],
        )
        if not path:
            return

        self.input_path.set(path)
        if not self.output_path.get():
            source = Path(path)
            self.output_path.set(str(source.with_name(f"{source.stem}_converted.mp4")))

        self._load_input_preview(path)

    def _schedule_layout_refresh(self, _event: tk.Event | None = None) -> None:
        if self._layout_after_id is not None:
            self.after_cancel(self._layout_after_id)
        self._layout_after_id = self.after(40, self._refresh_dynamic_layout)

    def _refresh_dynamic_layout(self) -> None:
        self._layout_after_id = None
        window_height = max(self.winfo_height(), 1)

        # Give timeline priority. When the window is short, shrink preview
        # instead of letting the timeline canvas collapse and hide handles.
        preview_height = max(95, min(180, window_height - 560))
        timeline_height = max(118, min(150, window_height - 560))
        lower_row_height = max(218, timeline_height + 92)

        self.preview_canvas.configure(height=preview_height)
        self.timeline.configure(height=timeline_height)
        self.content_frame.rowconfigure(1, minsize=lower_row_height)
        self.trim_box.rowconfigure(1, minsize=timeline_height)
        self._draw_timeline()

    def select_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save converted MP4",
            defaultextension=".mp4",
            filetypes=[("MP4 files", "*.mp4")],
        )
        if path:
            self.output_path.set(path)

    def _load_input_preview(self, path: str) -> None:
        if path == self._last_preview_path:
            return
        self._last_preview_path = path
        self.status.set("Loading input preview...")
        self.preview_summary.set("Reading video metadata...")
        self.preview_canvas.delete("all")
        self.preview_canvas.create_text(160, 90, text="Loading...", fill="#eeeeee")

        worker = threading.Thread(target=self._read_video_preview, args=(path,), daemon=True)
        worker.start()

    def _schedule_input_preview(self, *_args: object) -> None:
        if self._preview_after_id is not None:
            self.after_cancel(self._preview_after_id)
        self._preview_after_id = self.after(600, self._load_typed_input_preview)

    def _load_typed_input_preview(self) -> None:
        self._preview_after_id = None
        path = self.input_path.get().strip()
        if not path:
            self._last_preview_path = ""
            self.video_duration = 0.0
            self.source_fps = 0.0
            self.source_width = 0
            self.source_height = 0
            self.source_bitrate_kbps = 0.0
            self._set_size_presets(0, 0)
            self.preview_summary.set("Select an MP4 file to preview details.")
            self.preview_canvas.delete("all")
            self.preview_canvas.create_text(160, 90, text="No preview", fill="#eeeeee")
            self._draw_timeline()
            return

        input_path = Path(path)
        if input_path.exists() and input_path.suffix.lower() == ".mp4":
            self._load_input_preview(path)

    def _read_video_preview(self, path: str) -> None:
        try:
            with VideoFileClip(path) as clip:
                frame = clip.get_frame(0)
                duration = float(clip.duration or 0)
                info = {
                    "fps": float(clip.fps or 0),
                    "width": int(clip.w),
                    "height": int(clip.h),
                    "duration": duration,
                    "bitrate_kbps": self._estimate_bitrate_kbps(path, duration),
                    "frame": frame,
                }
            self.after(0, self._preview_loaded, info, None)
        except Exception as exc:
            self.after(0, self._preview_loaded, None, str(exc))

    def _preview_loaded(self, info: dict[str, object] | None, error: str | None) -> None:
        if error or info is None:
            self.status.set("Preview failed")
            self.preview_summary.set(f"Could not read video preview: {error}")
            self.preview_canvas.delete("all")
            self.preview_canvas.create_text(160, 90, text="Preview failed", fill="#eeeeee")
            return

        fps = float(info["fps"])
        width = int(info["width"])
        height = int(info["height"])
        duration = float(info["duration"])
        bitrate_kbps = float(info["bitrate_kbps"])
        frame = info["frame"]

        self.video_duration = duration
        self.source_fps = fps
        self.source_width = width
        self.source_height = height
        self.source_bitrate_kbps = bitrate_kbps
        self._set_trim_values(0.0, duration)
        self.fps.set(self._format_number(fps))
        self._set_size_presets(width, height)

        self._show_preview_frame(frame, 0.0)

        self.preview_summary.set(
            "\n".join(
                [
                    f"FPS: {self._format_number(fps)}",
                    f"Resolution: {width} x {height}",
                    f"Duration: {self._format_number(duration)} sec",
                    f"Approx bitrate: {self._format_number(bitrate_kbps)} kbps",
                ]
            )
        )
        self.status.set("Ready")
        self._draw_timeline()
        self.after(50, self._draw_timeline)

    def _set_size_presets(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            self.size_presets = {"Original": (0, 0)}
            self.output_size.set("Original")
            self.size_combo.configure(values=["Original"])
            return

        candidates = [
            ("Original", 1.0),
            ("75%", 0.75),
            ("50%", 0.5),
            ("25%", 0.25),
        ]
        presets: dict[str, tuple[int, int]] = {}
        for label, scale in candidates:
            preset_width = max(2, int(round(width * scale / 2) * 2))
            preset_height = max(2, int(round(height * scale / 2) * 2))
            name = f"{label} - {preset_width} x {preset_height}" if label != "Original" else f"Original - {width} x {height}"
            presets[name] = (preset_width, preset_height)

        self.size_presets = presets
        values = list(presets)
        self.size_combo.configure(values=values)
        self.output_size.set(values[0])

    def _show_preview_frame(self, frame: object, seconds: float) -> None:
        image = Image.fromarray(frame)
        image.thumbnail((320, 180), Image.Resampling.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(image)

        self.preview_canvas.delete("all")
        canvas_width = max(self.preview_canvas.winfo_width(), 320)
        canvas_height = max(self.preview_canvas.winfo_height(), 180)
        self.preview_canvas.create_image(canvas_width // 2, canvas_height // 2, image=self._preview_photo)
        self.preview_canvas.create_text(
            8,
            canvas_height - 8,
            text=f"{self._format_number(seconds)}s",
            anchor="sw",
            fill="#ffffff",
        )

    def _schedule_frame_preview(self, seconds: float) -> None:
        path = self.input_path.get().strip()
        if not path or self.video_duration <= 0:
            return

        if self._frame_preview_after_id is not None:
            self.after_cancel(self._frame_preview_after_id)
        self._frame_preview_after_id = self.after(120, lambda: self._load_frame_preview(seconds))

    def _load_frame_preview(self, seconds: float) -> None:
        self._frame_preview_after_id = None
        path = self.input_path.get().strip()
        if not path:
            return

        self._frame_preview_token += 1
        token = self._frame_preview_token
        safe_seconds = min(max(seconds, 0.0), max(self.video_duration - 0.001, 0.0))
        worker = threading.Thread(
            target=self._read_frame_preview,
            args=(path, safe_seconds, token),
            daemon=True,
        )
        worker.start()

    def _read_frame_preview(self, path: str, seconds: float, token: int) -> None:
        try:
            with VideoFileClip(path) as clip:
                frame = clip.get_frame(seconds)
            self.after(0, self._frame_preview_loaded, frame, seconds, token, None)
        except Exception as exc:
            self.after(0, self._frame_preview_loaded, None, seconds, token, str(exc))

    def _frame_preview_loaded(self, frame: object | None, seconds: float, token: int, error: str | None) -> None:
        if token != self._frame_preview_token:
            return
        if error or frame is None:
            self.status.set(f"Preview frame failed: {error}")
            return

        self._show_preview_frame(frame, seconds)
        self.status.set("Ready")

    def start_conversion(self) -> None:
        try:
            settings = self._read_settings()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.convert_button.configure(state="disabled")
        self.progress.configure(value=0)
        self.status.set("Converting... ETA calculating")

        worker = threading.Thread(target=self._convert_video, args=(settings,), daemon=True)
        worker.start()

    def _read_settings(self) -> dict[str, str | int | float | None]:
        input_text = self.input_path.get().strip()
        output_text = self.output_path.get().strip()
        input_path = Path(input_text)
        output_path = Path(output_text)

        if not input_text:
            raise ValueError("Input MP4 file is required.")
        if not input_path.exists():
            raise ValueError("Input MP4 file does not exist.")
        if input_path.suffix.lower() != ".mp4":
            raise ValueError("Input file must be an MP4 file.")
        if not output_text:
            raise ValueError("Output MP4 path is required.")
        if output_path.suffix.lower() != ".mp4":
            raise ValueError("Output file must use the .mp4 extension.")
        if output_path.resolve() == input_path.resolve():
            raise ValueError("Output file must be different from the input file.")
        if not output_path.parent.exists():
            raise ValueError("Output folder does not exist.")

        self._ensure_source_metadata(input_path)

        fps = self._parse_positive_float(self.fps.get(), "FPS")
        width, height = self._selected_output_size()
        trim_start = self._parse_non_negative_float(self.trim_start.get(), "Trim start")
        trim_end = self._parse_optional_positive_float(self.trim_end.get(), "Trim end")

        self._validate_downconvert_settings(fps, width, height)

        if trim_end is not None and trim_end <= trim_start:
            raise ValueError("Trim end must be greater than trim start.")
        if self.video_duration > 0 and trim_start >= self.video_duration:
            raise ValueError("Trim start must be less than the video duration.")
        if self.video_duration > 0 and trim_end is not None and trim_end > self.video_duration:
            raise ValueError("Trim end must not exceed the video duration.")

        return {
            "input_path": str(input_path),
            "output_path": str(output_path),
            "bitrate": QUALITY_BITRATES[self.quality.get()],
            "fps": fps,
            "width": width,
            "height": height,
            "trim_start": trim_start,
            "trim_end": trim_end,
        }

    def _selected_output_size(self) -> tuple[int, int]:
        selected = self.output_size.get()
        if selected not in self.size_presets:
            raise ValueError("Output size must be selected from the preset list.")

        width, height = self.size_presets[selected]
        if width <= 0 or height <= 0:
            raise ValueError("Load an input MP4 before selecting the output size.")
        return width, height

    def _ensure_source_metadata(self, input_path: Path) -> None:
        if self.source_fps > 0 and self.source_width > 0 and self.source_height > 0 and self.video_duration > 0:
            return

        with VideoFileClip(str(input_path)) as clip:
            self.source_fps = float(clip.fps or 0)
            self.source_width = int(clip.w)
            self.source_height = int(clip.h)
            self.video_duration = float(clip.duration or 0)
            self.source_bitrate_kbps = self._estimate_bitrate_kbps(str(input_path), self.video_duration)
        if not self.size_presets or self.output_size.get() not in self.size_presets:
            self._set_size_presets(self.source_width, self.source_height)

    def _validate_downconvert_settings(self, fps: float, width: int, height: int) -> None:
        if self.source_fps > 0 and fps > self.source_fps + 0.01:
            raise ValueError(
                f"FPS cannot exceed the input FPS. Input: {self._format_number(self.source_fps)}, "
                f"requested: {self._format_number(fps)}."
            )

        if self.source_width > 0 and width > self.source_width:
            raise ValueError(
                f"Output width cannot exceed the input width. Input: {self.source_width}, requested: {width}."
            )
        if self.source_height > 0 and height > self.source_height:
            raise ValueError(
                f"Output height cannot exceed the input height. Input: {self.source_height}, requested: {height}."
            )

        selected_bitrate = self._selected_bitrate_kbps()
        if (
            selected_bitrate is not None
            and self.source_bitrate_kbps > 0
            and selected_bitrate > self.source_bitrate_kbps * 1.05
        ):
            raise ValueError(
                "Quality bitrate cannot exceed the input video's approximate bitrate. "
                f"Input: {self._format_number(self.source_bitrate_kbps)} kbps, "
                f"requested: {self._format_number(selected_bitrate)} kbps."
            )

    def _selected_bitrate_kbps(self) -> float | None:
        bitrate = QUALITY_BITRATES[self.quality.get()]
        if bitrate is None:
            return None
        return float(bitrate.rstrip("k"))

    @staticmethod
    def _estimate_bitrate_kbps(path: str, duration: float) -> float:
        if duration <= 0:
            return 0.0
        return Path(path).stat().st_size * 8 / duration / 1000

    @staticmethod
    def _parse_positive_int(value: str, label: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be an integer.") from exc
        if number <= 0:
            raise ValueError(f"{label} must be greater than 0.")
        return number

    @staticmethod
    def _parse_positive_float(value: str, label: str) -> float:
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc
        if number <= 0:
            raise ValueError(f"{label} must be greater than 0.")
        return number

    @staticmethod
    def _parse_non_negative_float(value: str, label: str) -> float:
        try:
            number = float(value or "0")
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc
        if number < 0:
            raise ValueError(f"{label} must be 0 or greater.")
        return number

    @staticmethod
    def _parse_optional_positive_float(value: str, label: str) -> float | None:
        if not value.strip():
            return None
        return VideoConverterApp._parse_positive_float(value, label)

    def _convert_video(self, settings: dict[str, str | int | float | None]) -> None:
        edited = None
        try:
            logger = ConversionProgressLogger(
                lambda progress, eta: self.after(0, self._conversion_progress, progress, eta)
            )
            with VideoFileClip(str(settings["input_path"])) as clip:
                edited = clip.subclipped(settings["trim_start"], settings["trim_end"])
                edited = edited.resized(new_size=(settings["width"], settings["height"]))
                edited.write_videofile(
                    str(settings["output_path"]),
                    fps=settings["fps"],
                    codec="libx264",
                    audio_codec="aac",
                    bitrate=settings["bitrate"],
                    preset="medium",
                    threads=4,
                    logger=logger,
                )
                edited.close()

            self.after(0, self._conversion_finished, None)
        except Exception as exc:
            if edited is not None:
                edited.close()
            error = f"{exc}\n\n{traceback.format_exc()}"
            self.after(0, self._conversion_finished, error)

    def _conversion_finished(self, error: str | None) -> None:
        self.convert_button.configure(state="normal")

        if error:
            self.progress.configure(value=0)
            self.status.set("Failed")
            messagebox.showerror("Conversion failed", error)
            return

        self.progress.configure(value=100)
        self.status.set("Done")
        messagebox.showinfo("Conversion complete", "MP4 conversion finished.")

    def _conversion_progress(self, progress: float, eta: float | None) -> None:
        percent = round(progress * 100, 1)
        self.progress.configure(value=percent)
        if eta is None:
            self.status.set(f"Converting... {percent}% / ETA calculating")
            return
        self.status.set(f"Converting... {percent}% / ETA {self._format_duration(eta)}")

    def _on_trim_entry_changed(self, *_args: object) -> None:
        if self._syncing_trim:
            return
        self._update_trim_summary()
        self._draw_timeline()
        self._schedule_frame_preview(self._clamped_trim_start())

    def _set_trim_values(self, start: float, end: float) -> None:
        self._syncing_trim = True
        self.trim_start.set(self._format_number(start))
        self.trim_end.set(self._format_number(end))
        self._syncing_trim = False
        self._update_trim_summary()

    def _update_trim_summary(self) -> None:
        end = self.trim_end.get().strip() or "end"
        self.trim_summary.set(f"Trim: {self.trim_start.get().strip() or '0'}s - {end}s")

    def _draw_timeline(self) -> None:
        if not hasattr(self, "timeline"):
            return

        self.timeline.delete("all")
        width = max(self.timeline.winfo_width(), 300)
        height = max(self.timeline.winfo_height(), 100)
        left = 28
        right = width - 28
        center_y = 48

        self.timeline.create_line(left, center_y, right, center_y, fill="#d4d8df", width=8, capstyle=tk.ROUND)

        if self.video_duration <= 0:
            self.timeline.create_text(width // 2, center_y, text="Load a video to enable timeline", fill="#555555")
            return

        start = self._clamped_trim_start()
        end = self._clamped_trim_end()
        start_x = self._seconds_to_x(start, left, right)
        end_x = self._seconds_to_x(end, left, right)

        self.timeline.create_line(start_x, center_y, end_x, center_y, fill="#2f7de1", width=8, capstyle=tk.ROUND)
        self._draw_handle(start_x, center_y, "start", "#1f5fbf")
        self._draw_handle(end_x, center_y, "end", "#c53f3f")
        self.timeline.create_text(left, height - 18, text="0.00s", anchor="w", fill="#555555")
        self.timeline.create_text(
            right,
            height - 18,
            text=f"{self._format_number(self.video_duration)}s",
            anchor="e",
            fill="#555555",
        )

    def _draw_handle(self, x: float, y: float, label: str, fill: str) -> None:
        radius = 12
        self.timeline.create_oval(x - radius + 2, y - radius + 3, x + radius + 2, y + radius + 3, fill="#b9c1cc", outline="")
        self.timeline.create_oval(x - radius, y - radius, x + radius, y + radius, fill="#ffffff", outline=fill, width=2)
        self.timeline.create_oval(x - 6, y - 6, x + 6, y + 6, fill=fill, outline="")
        self.timeline.create_line(x, y - 5, x, y + 5, fill="#ffffff", width=2)
        self.timeline.create_text(x, y - 25, text=label, fill=fill)

    def _on_timeline_press(self, event: tk.Event) -> None:
        if self.video_duration <= 0:
            return

        width = max(self.timeline.winfo_width(), 300)
        left = 28
        right = width - 28
        start_x = self._seconds_to_x(self._clamped_trim_start(), left, right)
        end_x = self._seconds_to_x(self._clamped_trim_end(), left, right)
        self._active_handle = "start" if abs(event.x - start_x) <= abs(event.x - end_x) else "end"
        self._move_active_handle(event.x)

    def _on_timeline_drag(self, event: tk.Event) -> None:
        if self._active_handle:
            self._move_active_handle(event.x)

    def _on_timeline_release(self, _event: tk.Event) -> None:
        self._active_handle = None

    def _move_active_handle(self, x: int) -> None:
        width = max(self.timeline.winfo_width(), 300)
        left = 28
        right = width - 28
        seconds = self._x_to_seconds(x, left, right)
        start = self._clamped_trim_start()
        end = self._clamped_trim_end()

        if self._active_handle == "start":
            start = min(seconds, max(end - 0.01, 0))
        elif self._active_handle == "end":
            end = max(seconds, min(start + 0.01, self.video_duration))
        else:
            return

        self._set_trim_values(start, end)
        self._draw_timeline()
        preview_seconds = start if self._active_handle == "start" else end
        self._schedule_frame_preview(preview_seconds)

    def _seconds_to_x(self, seconds: float, left: int, right: int) -> float:
        ratio = seconds / self.video_duration if self.video_duration else 0
        return left + (right - left) * ratio

    def _x_to_seconds(self, x: int, left: int, right: int) -> float:
        clamped_x = min(max(x, left), right)
        ratio = (clamped_x - left) / (right - left)
        return self.video_duration * ratio

    def _clamped_trim_start(self) -> float:
        try:
            start = float(self.trim_start.get() or 0)
        except ValueError:
            start = 0.0
        return min(max(start, 0.0), self.video_duration)

    def _clamped_trim_end(self) -> float:
        try:
            end = float(self.trim_end.get() or self.video_duration)
        except ValueError:
            end = self.video_duration
        return min(max(end, 0.0), self.video_duration)

    @staticmethod
    def _format_number(value: float) -> str:
        return f"{value:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _format_duration(seconds: float) -> str:
        total_seconds = max(0, int(round(seconds)))
        minutes, remaining_seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{remaining_seconds:02d}"
        return f"{minutes:d}:{remaining_seconds:02d}"


def main() -> None:
    app = VideoConverterApp()
    app.mainloop()


if __name__ == "__main__":
    main()

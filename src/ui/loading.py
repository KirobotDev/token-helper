import threading
import customtkinter as ctk
from tkinter import Canvas
import math
import time


class LoadingScreen(ctk.CTkToplevel):
    def __init__(self, on_done_callback):
        super().__init__()
        self.on_done_callback = on_done_callback

        self.title("Token Helper")
        self.geometry("620x380")
        self.resizable(False, False)
        self.overrideredirect(True)

        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 620) // 2
        y = (sh - 380) // 2
        self.geometry(f"620x380+{x}+{y}")

        self.configure(fg_color="#f7fbff")
        self._build_ui()
        self._start_animations()

    def _build_ui(self):
        self.canvas = Canvas(self, width=620, height=380, bg="#f7fbff",
                             highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self._draw_bg()

        self.logo_frame = ctk.CTkFrame(self, width=90, height=90, corner_radius=45,
                                       fg_color="#ffffff", border_color="#3b82f6",
                                       border_width=2)
        self.logo_frame.place(x=265, y=60)

        self.logo_label = ctk.CTkLabel(
            self.logo_frame, text="⚿",
            font=ctk.CTkFont(size=38), text_color="#2563eb"
        )
        self.logo_label.place(relx=0.5, rely=0.5, anchor="center")

        self.title_label = ctk.CTkLabel(
            self, text="Token Helper",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color="#0f172a"
        )
        self.title_label.place(x=310, y=168, anchor="center")

        self.tag_label = ctk.CTkLabel(
            self, text="Scanning your system for Discord tokens…",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#6b7280"
        )
        self.tag_label.place(x=310, y=198, anchor="center")

        self.bar_bg = ctk.CTkFrame(self, width=440, height=6, corner_radius=3,
                                   fg_color="#e2e8f0")
        self.bar_bg.place(x=90, y=250)

        self.bar_fill = ctk.CTkFrame(self, width=0, height=6, corner_radius=3,
                                     fg_color="#3b82f6")
        self.bar_fill.place(x=90, y=250)

        self.status_label = ctk.CTkLabel(
            self, text="Initialisation…",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#6b7280"
        )
        self.status_label.place(x=310, y=270, anchor="center")

        self.pct_label = ctk.CTkLabel(
            self, text="0%",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#2563eb"
        )
        self.pct_label.place(x=310, y=290, anchor="center")

        ctk.CTkLabel(
            self, text="v1.0.0",
            font=ctk.CTkFont(size=10),
            text_color="#374151"
        ).place(x=310, y=355, anchor="center")

        self._dot_angle = 0
        self._dot_canvas = Canvas(self, width=30, height=30, bg="#f7fbff",
                                  highlightthickness=0)
        self._dot_canvas.place(x=295, y=310)

    def _draw_bg(self):
        """Draw subtle radial gradient blobs."""
        c = self.canvas
        for r in range(120, 0, -10):
            alpha_hex = format(int(r / 120 * 30), '02x')
            c.create_oval(-r + 80, -r + 80, r + 80, r + 80,
                          fill="", outline=f"#dbeafe")
        for r in range(100, 0, -10):
            c.create_oval(620 - r - 60, 380 - r - 60, 620 - 60 + r, 380 - 60 + r,
                          fill="", outline=f"#bfdbfe")

    def _start_animations(self):
        self._progress = 0.0
        self._target_progress = 0.0
        self._animate_loop()

    def _animate_loop(self):
        """Smooth progress bar animation."""
        if self._progress < self._target_progress:
            diff = self._target_progress - self._progress
            self._progress += max(0.002, diff * 0.08)
            self._progress = min(self._progress, self._target_progress)

        w = int(self._progress * 440)
        self.bar_fill.configure(width=max(w, 1))

        t = time.time()
        r_val = int(82 + 20 * math.sin(t * 2))
        self.bar_fill.configure(fg_color=f"#3b{r_val:02x}f6")

        self._dot_canvas.delete("all")
        for i in range(8):
            angle = self._dot_angle + i * 45
            rad = math.radians(angle)
            cx = 15 + 9 * math.cos(rad)
            cy = 15 + 9 * math.sin(rad)
            alpha = int(255 * (i / 8))
            color = f"#{alpha // 2:02x}{alpha:02x}ff"
            size = 2 + (i == 7) * 1
            self._dot_canvas.create_oval(cx - size, cy - size, cx + size, cy + size,
                                         fill=color, outline="")
        self._dot_angle = (self._dot_angle + 4) % 360

        pct = int(self._progress * 100)
        self.pct_label.configure(text=f"{pct}%")

        if self._progress < 0.999:
            self.after(16, self._animate_loop)  
        else:
            self.after(400, self._finish)

    def _finish(self):
        """Fade out and call callback."""
        self._fade_out(1.0)

    def _fade_out(self, alpha):
        if alpha > 0:
            try:
                self.attributes("-alpha", alpha)
                self.after(20, lambda: self._fade_out(round(alpha - 0.07, 2)))
            except Exception:
                pass
        else:
            self.destroy()
            self.on_done_callback()

    def update_progress(self, status_text: str, progress: float):
        """Called from scanner thread to update progress."""
        self._target_progress = min(progress, 0.94)
        try:
            self.status_label.configure(text=status_text)
        except Exception:
            pass

    def finish_scan(self):
        """Call when scan is complete to animate to 100%."""
        self._target_progress = 1.0

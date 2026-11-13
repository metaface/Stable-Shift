"""Stable Shift V2 desktop experiment: color reference + edited image."""
from dataclasses import asdict
from datetime import datetime
import importlib.util
import json
from pathlib import Path
from queue import Queue, Empty
import subprocess
import sys
from threading import Thread
from time import perf_counter
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk, ImageOps

from engine import Options, restore_quality, preserve_edits
from image_inputs import drop_path, load_image

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES, COPY, REFUSE_DROP
except ImportError:
    TkinterDnD = None
    DND_FILES, COPY, REFUSE_DROP = 'DND_Files', 'copy', 'refuse_drop'

ROOT = Path(__file__).resolve().parent


def default_method():
    if importlib.util.find_spec('bm3d_cupy') is not None:
        return 'GPU BM3D'
    if importlib.util.find_spec('bm3d') is not None:
        return 'CPU BM3D'
    return 'Region cleanup only'


class App:
    def __init__(self, root, dnd_available=False, dnd_error=''):
        self.root = root
        root.title('Stable Shift V2.1 — Surface Cleanup Lab')
        root.geometry('1400x940')
        root.minsize(1040, 760)
        self.images = {'clean': None, 'edited': None}
        self.paths = {}
        self.result = None
        self.maps = {}
        self.queue = Queue()
        self.busy = False
        self.started = None
        self.phase = ''
        self._redraw_job = None
        self.dnd_available = dnd_available
        self.dnd_error = dnd_error
        self.mode = tk.StringVar(value='Restore Quality')
        self.method = tk.StringVar(value=default_method())
        self.theme = tk.StringVar(value='System')
        self.palette = tk.BooleanVar(value=True)
        self.source_guard = tk.BooleanVar(value=True)
        self.noise = tk.DoubleVar(value=50)
        self.chroma = tk.DoubleVar(value=55)
        self.cleanup = tk.DoubleVar(value=60)
        self.cleanup_luma = tk.DoubleVar(value=60)
        self.cleanup_range = tk.DoubleVar(value=12)
        self.cleanup_radius = tk.IntVar(value=16)
        self.hard = tk.DoubleVar(value=100)
        self.soft = tk.DoubleVar(value=60)
        self.shade = tk.DoubleVar(value=35)
        self.edit = tk.DoubleVar(value=23)
        self.advanced_visible = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='Load or drop a color reference and an edited image. Cleanup is experimental.')
        self.result_info = tk.StringVar(value='No result yet. Preview is scaled; comparison crops retain native pixels.')
        self.file_info = tk.StringVar(value='Reference supplies colors only. All structural analysis uses the edited/denoised image.')

        main = ttk.Frame(root, padding=10)
        main.pack(fill='both', expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(5, weight=1)
        toolbar = ttk.Frame(main)
        toolbar.grid(row=0, column=0, sticky='ew', pady=(0, 7))
        self.open_buttons = {}
        for key, label in [('clean', 'Open color reference'), ('edited', 'Open edited image')]:
            button = ttk.Button(toolbar, text=label, command=lambda k=key: self.open_file(k))
            button.pack(side='left', padx=(0, 7))
            self.open_buttons[key] = button
        ttk.Button(toolbar, text='Run / Preview', command=self.run).pack(side='right')
        ttk.Button(toolbar, text='Compare V2', command=self.compare).pack(side='right', padx=7)
        ttk.Button(toolbar, text='Save PNG + timings', command=self.save).pack(side='right', padx=7)
        ttk.Button(toolbar, text='Save maps', command=self.save_maps).pack(side='right', padx=7)
        ttk.Label(main, textvariable=self.file_info).grid(row=1, column=0, sticky='ew', pady=(0, 6))

        controls = ttk.LabelFrame(main, text='Restore Quality', padding=8)
        controls.grid(row=2, column=0, sticky='ew')
        row = ttk.Frame(controls)
        row.pack(fill='x')
        ttk.Label(row, text='Denoiser:').pack(side='left')
        ttk.Combobox(row, textvariable=self.method, state='readonly', width=22, values=[
            'GPU BM3D', 'CPU BM3D', 'Region cleanup only', 'NLM', 'Boundary constrained', 'Color only'
        ]).pack(side='left', padx=7)
        ttk.Checkbutton(row, text='Reference color correction (last)', variable=self.palette).pack(side='left', padx=10)
        ttk.Label(row, text='Theme:').pack(side='left', padx=(12, 0))
        theme = ttk.Combobox(row, textvariable=self.theme, state='readonly', width=8, values=['System', 'Dark', 'Light'])
        theme.pack(side='left', padx=6)
        theme.bind('<<ComboboxSelected>>', lambda e: self.apply_theme())
        ttk.Checkbutton(row, text='Advanced / legacy', variable=self.advanced_visible, command=self.show_advanced).pack(side='right')
        grid = ttk.Frame(controls)
        grid.pack(fill='x', pady=(7, 0))
        self._scale(grid, 'Luminance denoise', self.noise, 0, 100, 0, 0)
        self._scale(grid, 'Color denoise', self.chroma, 0, 100, 0, 1)
        self._scale(grid, 'V2 surface cleanup (0 = off)', self.cleanup, 0, 100, 0, 2)
        self._scale(grid, 'Brightness cleanup (0 = chroma only)', self.cleanup_luma, 0, 100, 1, 0)
        self._scale(grid, 'Color similarity range (LAB)', self.cleanup_range, 2, 40, 1, 1)
        radius_frame = ttk.Frame(grid)
        radius_frame.grid(row=1, column=2, sticky='ew', padx=6, pady=3)
        ttk.Label(radius_frame, text='Broad neighborhood radius (pixels)').pack(anchor='w')
        ttk.Spinbox(radius_frame, from_=2, to=32, width=7, textvariable=self.cleanup_radius).pack(side='left')
        ttk.Label(radius_frame, text='  Full-resolution sampling').pack(side='left')
        ttk.Checkbutton(controls, text='Trace source lines before denoising and protect them through cleanup', variable=self.source_guard).pack(anchor='w', pady=(5, 0))
        ttk.Label(controls, text='Compare V2: baseline / + source lines / + surface cleanup / surface cleanup alone.').pack(anchor='w', pady=(3, 0))
        self.advanced = ttk.LabelFrame(main, text='Legacy denoiser guards / Preserve Edits (unchanged)', padding=7)
        ag = ttk.Frame(self.advanced)
        ag.pack(fill='x')
        self._scale(ag, 'Hard edge guard (legacy denoisers)', self.hard, 0, 100, 0, 0)
        self._scale(ag, 'Soft edge guard (legacy denoisers)', self.soft, 0, 100, 0, 1)
        self._scale(ag, 'Original shading-boundary sensitivity', self.shade, 0, 100, 0, 2)
        taskrow = ttk.Frame(self.advanced)
        taskrow.pack(fill='x', pady=4)
        ttk.Label(taskrow, text='Task:').pack(side='left')
        ttk.Combobox(taskrow, textvariable=self.mode, state='readonly', width=18, values=['Restore Quality', 'Preserve Edits']).pack(side='left', padx=6)
        ttk.Label(taskrow, text='Legacy edit sensitivity:').pack(side='left', padx=8)
        ttk.Spinbox(taskrow, from_=3, to=90, textvariable=self.edit, width=5).pack(side='left')
        ttk.Label(self.advanced, text='BM3D/NLM retain V1 edge blending. V2 surface sampling has its own internal boundary constraints.').pack(anchor='w')

        installbar = ttk.Frame(main)
        installbar.grid(row=4, column=0, sticky='ew', pady=7)
        ttk.Button(installbar, text='Install CPU BM3D', command=lambda: self.install('bm3d==4.0.3')).pack(side='right', padx=4)
        ttk.Button(installbar, text='Install GPU BM3D (CUDA 12)', command=lambda: self.install('bm3d-cupy[cuda12]==0.1.3')).pack(side='right', padx=4)
        dnd_message = 'Drop one image onto each input panel (file paths with spaces are supported).'
        if not dnd_available:
            dnd_message = 'Drag/drop unavailable. Open buttons still work; see startup.log for the load error.'
        self.dnd_label = ttk.Label(installbar, text=dnd_message)
        self.dnd_label.pack(side='left')

        previews = ttk.Frame(main)
        previews.grid(row=5, column=0, sticky='nsew')
        previews.rowconfigure(0, weight=1)
        self.canvases = {}
        self.preview_frames = {}
        self.photos = {}
        for column, (key, title) in enumerate([
            ('clean', 'COLOR REFERENCE — palette only'), ('edited', 'EDITED — image to clean'), ('result', 'RESULT')
        ]):
            previews.columnconfigure(column, weight=1, uniform='preview')
            frame = ttk.LabelFrame(previews, text=title, padding=3)
            frame.grid(row=0, column=column, sticky='nsew', padx=3)
            canvas = tk.Canvas(frame, highlightthickness=0, width=200, height=220)
            canvas.pack(fill='both', expand=True)
            canvas.bind('<Configure>', self.schedule_redraw)
            canvas.bind('<Double-Button-1>', lambda e, k=key: self.open_file(k) if k != 'result' else None)
            self.canvases[key] = canvas
            self.preview_frames[key] = frame
            if dnd_available and key != 'result':
                for widget in (canvas, frame, self.open_buttons[key]):
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind('<<Drop>>', lambda e, k=key: self.drop(e, k))
        ttk.Label(main, textvariable=self.result_info, anchor='w').grid(row=6, column=0, sticky='ew', pady=(6, 2))
        ttk.Label(main, textvariable=self.status, anchor='w', wraplength=1300).grid(row=7, column=0, sticky='ew')
        self.apply_theme()
        self.root.after(100, self.poll)
        self.root.after(250, self.tick)

    def _scale(self, parent, label, var, low, high, row, col):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=col, sticky='ew', padx=6, pady=3)
        parent.columnconfigure(col, weight=1, uniform='controls')
        line = ttk.Frame(frame)
        line.pack(fill='x')
        ttk.Label(line, text=label).pack(side='left')
        text = tk.StringVar(value=f'{var.get():.0f}')
        var.trace_add('write', lambda *args: text.set(f'{var.get():.0f}'))
        ttk.Label(line, textvariable=text, width=4, anchor='e').pack(side='right')
        ttk.Scale(frame, from_=low, to=high, variable=var).pack(fill='x', pady=2)

    def show_advanced(self):
        if self.advanced_visible.get():
            self.advanced.grid(row=3, column=0, sticky='ew', pady=6)
        else:
            self.advanced.grid_remove()
        self.schedule_redraw()

    def apply_theme(self):
        dark = self.theme.get() != 'Light'
        if self.theme.get() == 'System':
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                    dark = winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
            except (ImportError, OSError):
                dark = True
        colors = ('#202124', '#eceff4', '#363a40', '#151719') if dark else ('#eeeeee', '#17191c', '#d5d9df', '#dfe3e8')
        if getattr(self, '_colors', None) == colors:
            return
        self._colors = colors
        bg, fg, field, canvas_bg = colors
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', background=bg, foreground=fg, fieldbackground=field)
        style.configure('TCombobox', fieldbackground=field, background=field, foreground=fg)
        style.map('TCombobox', fieldbackground=[('readonly', field)], foreground=[('readonly', fg)], selectbackground=[('readonly', field)], selectforeground=[('readonly', fg)])
        style.configure('TSpinbox', fieldbackground=field, foreground=fg, arrowcolor=fg)
        style.map('TButton', background=[('active', field)], foreground=[('active', fg)])
        style.configure('Horizontal.TScale', background=bg, troughcolor=field)
        self.root.configure(background=bg)
        self.root.option_add('*TCombobox*Listbox.background', field)
        self.root.option_add('*TCombobox*Listbox.foreground', fg)
        for canvas in self.canvases.values():
            canvas.configure(background=canvas_bg)
        self.schedule_redraw()

    def schedule_redraw(self, event=None):
        if self._redraw_job is not None:
            self.root.after_cancel(self._redraw_job)
        self._redraw_job = self.root.after(80, self.redraw)

    def redraw(self):
        self._redraw_job = None
        for key, canvas in self.canvases.items():
            canvas.delete('all')
            width, height = max(80, canvas.winfo_width()), max(80, canvas.winfo_height())
            image = self.result if key == 'result' else self.images[key]
            if image is None:
                label = 'Run a preview to see the result' if key == 'result' else 'Drop an image here\nor use Open above'
                canvas.create_text(width / 2, height / 2, text=label, fill=self._colors[1], justify='center')
                self.photos.pop(key, None)
                continue
            thumb = ImageOps.contain(image, (max(1, width - 8), max(1, height - 8)), Image.Resampling.LANCZOS)
            self.photos[key] = ImageTk.PhotoImage(thumb)
            canvas.create_image(width / 2, height / 2, image=self.photos[key])

    def open_file(self, key):
        if self.busy:
            self.status.set('Finish the current operation before replacing an input image.')
            return
        parent = Path(self.paths[key]).parent if key in self.paths else None
        path = filedialog.askopenfilename(initialdir=str(parent) if parent else None, filetypes=[
            ('Images', '*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff'), ('All files', '*.*')])
        if path:
            self.set_image(key, path)

    def set_image(self, key, path):
        if self.busy:
            self.status.set('Finish the current operation before replacing an input image.')
            return False
        try:
            image = load_image(path)
        except Exception as exc:
            messagebox.showerror('Open image', str(exc))
            return False
        self.images[key] = image
        self.paths[key] = str(path)
        self.result = None
        self.maps = {}
        self.file_info.set(' | '.join(f'{name}: {Path(value).name} ({self.images[name].width} x {self.images[name].height})' for name, value in self.paths.items()))
        self.result_info.set('Input changed. Run again to create a result for this pair.')
        self.status.set(f'Loaded {key}: {image.width} x {image.height}')
        self.schedule_redraw()
        return True

    def drop(self, event, key):
        if self.busy:
            self.status.set('Finish the current operation before replacing an input image.')
            return REFUSE_DROP
        try:
            path = drop_path(self.root.tk, event.data)
        except (ValueError, tk.TclError) as exc:
            self.status.set(str(exc))
            return REFUSE_DROP
        return COPY if self.set_image(key, path) else REFUSE_DROP

    def opts(self):
        return Options(method=self.method.get(), noise=self.noise.get(), color_noise=self.chroma.get(),
                       hard_guard=self.hard.get(), soft_guard=self.soft.get(), shade_threshold=self.shade.get(),
                       color_match=self.palette.get(), edit_sensitivity=self.edit.get(), cleanup=self.cleanup.get(),
                       cleanup_range=self.cleanup_range.get(), cleanup_luma=self.cleanup_luma.get(),
                       cleanup_radius=self.cleanup_radius.get(), source_guard=self.source_guard.get())

    def snapshot(self):
        if self.images['edited'] is None:
            raise ValueError('Load an edited image first.')
        if self.images['clean'] is None and (self.palette.get() or self.mode.get() == 'Preserve Edits'):
            raise ValueError('Load a color reference, or turn reference color correction off.')
        opts = self.opts()
        from region_cleanup import RegionOptions
        RegionOptions(opts.cleanup, opts.cleanup_range, opts.cleanup_luma, opts.cleanup_radius).validated()
        edited = self.images['edited'].copy()
        clean = self.images['clean'].copy() if self.images['clean'] is not None else edited.copy()
        return clean, edited, opts

    def begin(self, phase):
        self.busy = True
        self.started = perf_counter()
        self.phase = phase
        self.status.set(phase)

    def progress(self, text):
        self.queue.put(('progress', text))

    def run(self):
        if self.busy:
            return
        try:
            clean, edited, opts = self.snapshot()
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning('Inputs/settings', str(exc))
            return
        mode = self.mode.get()
        self.begin('Preparing restoration')
        def worker():
            try:
                if mode == 'Preserve Edits':
                    start = perf_counter()
                    out, maps = preserve_edits(clean, edited, opts)
                    maps['report'] = {'backend': 'Legacy Preserve Edits', 'total_seconds': perf_counter() - start, 'options': asdict(opts)}
                else:
                    out, maps = restore_quality(clean, edited, opts, progress=self.progress)
                self.queue.put(('result', (out, maps)))
            except Exception as exc:
                self.queue.put(('error', (str(exc), traceback.format_exc())))
        Thread(target=worker, daemon=True).start()

    def compare(self):
        if self.busy:
            return
        if self.mode.get() != 'Restore Quality':
            messagebox.showinfo('Compare V2', 'Comparison is for Restore Quality; Preserve Edits is unchanged.')
            return
        try:
            clean, edited, opts = self.snapshot()
            from comparison import comparison_plan, export_comparison
            comparison_plan(opts)
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning('Inputs/settings', str(exc))
            return
        parent = filedialog.askdirectory(title='Choose parent folder for a new V2 comparison folder')
        if not parent:
            return
        directory = Path(parent) / datetime.now().strftime('stable_shift_v2_%Y%m%d_%H%M%S_%f')
        self.begin('Comparing V2 variants')
        def worker():
            try:
                reports = export_comparison(clean, edited, opts, directory, self.progress)
                self.queue.put(('compared', (directory, reports)))
            except Exception as exc:
                self.queue.put(('error', (str(exc), traceback.format_exc())))
        Thread(target=worker, daemon=True).start()

    def install(self, package):
        if self.busy:
            return
        note = 'CPU BM3D publishes noncommercial license terms. ' if package.startswith('bm3d==') else 'Requires a compatible NVIDIA driver; CUDA downloads can be large. '
        if not messagebox.askyesno('Install optional backend', note + '\nInstall ' + package + ' into this app\'s Python environment?'):
            return
        self.begin('Installing ' + package)
        def worker():
            try:
                proc = subprocess.run([sys.executable, '-m', 'pip', 'install', package], capture_output=True, text=True, timeout=1200)
                if proc.returncode:
                    raise RuntimeError((proc.stderr or proc.stdout)[-2200:])
                self.queue.put(('installed', package + ' installed. Select its backend from the dropdown.'))
            except Exception as exc:
                self.queue.put(('error', (str(exc), traceback.format_exc())))
        Thread(target=worker, daemon=True).start()

    def tick(self):
        if self.busy and self.started is not None:
            self.status.set(f'{self.phase} | {perf_counter() - self.started:.1f}s elapsed')
        if self.theme.get() == 'System':
            self.apply_theme()
        self.root.after(250, self.tick)

    def poll(self):
        try:
            while True:
                kind, data = self.queue.get_nowait()
                if kind == 'progress':
                    self.phase = data
                    continue
                self.busy = False
                self.started = None
                if kind == 'result':
                    self.result, self.maps = data
                    report = self.maps['report']
                    parts = [report['backend']]
                    parts += [f'{key.removesuffix("_seconds")}: {value:.2f}s' for key, value in report.items() if key.endswith('_seconds')]
                    self.result_info.set(' | '.join(parts))
                    region = report.get('region_cleanup', {})
                    self.status.set(f'Finished. Source lines protected {report.get("source_protected_pixels_percent", 0):.1f}% | Cleanup changed {region.get("changed_pixels_percent", 0):.1f}%; mean RGB change {region.get("mean_rgb_change", 0):.2f}/255. Compare native-resolution crops.')
                    self.schedule_redraw()
                elif kind == 'compared':
                    directory, reports = data
                    self.status.set('Comparison saved: ' + str(directory))
                    self.result_info.set(' | '.join(f'{run["name"]}: {run["total_seconds"]:.2f}s' for run in reports))
                elif kind == 'installed':
                    self.status.set(data)
                elif kind == 'error':
                    self.status.set('Operation failed; no backend fallback was performed.')
                    messagebox.showerror('Stable Shift', data[0] + '\n\n' + data[1][-1800:])
        except Empty:
            pass
        self.root.after(100, self.poll)

    def save(self):
        if self.result is None:
            messagebox.showinfo('Save', 'Run a preview first.')
            return
        path = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('PNG', '*.png')])
        if not path:
            return
        try:
            self.result.save(path)
            Path(path).with_suffix('.settings.json').write_text(json.dumps(self.maps.get('report', {}), indent=2), encoding='utf-8')
            self.status.set('Saved PNG and its actual settings/timings report.')
        except Exception as exc:
            messagebox.showerror('Save', str(exc))

    def save_maps(self):
        if not self.maps:
            messagebox.showinfo('Maps', 'Run a preview first.')
            return
        directory = filedialog.askdirectory(title='Save diagnostic maps')
        if not directory:
            return
        try:
            from stage_maps import save_diagnostics
            count = save_diagnostics(self.maps, directory)
            self.status.set(f'Saved {count} map previews, signed raw arrays and MAP_LEGEND.')
        except Exception as exc:
            messagebox.showerror('Save maps', str(exc))



def main():
    error = ''
    available = False
    root = tk.Tk()
    try:
        if TkinterDnD is None:
            raise ImportError('tkinterdnd2 is not installed. Relaunch through START_Difference_Guard.bat to install V2 dependencies.')
        TkinterDnD.require(root)
        available = True
    except (ImportError, tk.TclError, RuntimeError) as exc:
        error = str(exc)
        try:
            (ROOT / 'startup.log').write_text(error, encoding='utf-8')
        except OSError:
            pass
    App(root, available, error)
    root.mainloop()


if __name__ == '__main__':
    main()

"""One restoration workflow with automatic strengths and optional overrides."""
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
from time import perf_counter
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageOps

from .pipeline import Options, prepare
from .global_color import METHODS, color_method_label
from .image_inputs import load_image, drop_path
from .preview import result_view
from .export import save_result, save_test

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES, COPY, REFUSE_DROP
except ImportError:
    TkinterDnD = None
    DND_FILES, COPY, REFUSE_DROP = 'DND_Files', 'copy', 'refuse_drop'

ROOT = Path(__file__).resolve().parent.parent


class App:
    def __init__(self, root, dnd_available=False, dnd_error=''):
        self.root = root
        root.title('Stable Shift V2.24 — Automatic Restoration')
        root.geometry('1400x880')
        root.minsize(1000, 640)
        self.images = {'reference': None, 'edited': None}
        self.paths, self.photos, self.canvases = {}, {}, {}
        self.preview = self.displayed_preview = self.cache = None
        self.result, self.report = None, {}
        self.queue = Queue()
        self.busy = False
        self.generation = 0
        self.started = None
        self.phase = ''
        self._redraw_job = self._render_job = None
        self._view_box = self._drag_start = None
        self.center = (.5, .5)
        self.automatic = tk.BooleanVar(value=True)
        self.reference_enabled = tk.BooleanVar(value=True)
        self.color_method = tk.StringVar(value='Robust global')
        self.denoise = tk.DoubleVar(value=100)
        self.deblotch = tk.DoubleVar(value=100)
        self.color = tk.DoubleVar(value=100)
        self.zoom = tk.StringVar(value='Fit')
        self.theme = tk.StringVar(value='System')
        self.status = tk.StringVar(value='Open an image and optionally a color reference. Automatic strengths are enabled.')
        self.info = tk.StringVar(value='SCUNet denoising, deblotching and color correction')
        self.files = tk.StringVar(value='A color reference is optional; the edited image supplies all geometry.')
        self.dnd_available = dnd_available
        main = ttk.Frame(root, padding=10)
        main.pack(fill='both', expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)
        bar = ttk.Frame(main)
        bar.grid(row=0, column=0, sticky='ew')
        self.open_buttons = {}
        for key, label in (('edited', 'Open image'), ('reference', 'Open color reference')):
            button = ttk.Button(bar, text=label, command=lambda k=key: self.open_file(k))
            button.pack(side='left', padx=(0, 7))
            self.open_buttons[key] = button
        ttk.Button(bar, text='Clear reference', command=self.clear_reference).pack(side='left')
        ttk.Button(bar, text='Run', command=self.run).pack(side='right')
        ttk.Button(bar, text='Save PNG + settings', command=self.save).pack(side='right', padx=7)
        ttk.Button(bar, text='Save test', command=self.save_bundle).pack(side='right', padx=7)
        setup = ttk.Menubutton(bar, text='SCUNet setup')
        menu = tk.Menu(setup, tearoff=False)
        menu.add_command(label='NVIDIA GPU', command=lambda: self.install_scunet('nvidia'))
        menu.add_command(label='CPU', command=lambda: self.install_scunet('cpu'))
        setup.configure(menu=menu)
        setup.pack(side='right', padx=7)
        ttk.Label(main, textvariable=self.files).grid(row=1, column=0, sticky='ew', pady=7)
        controls = ttk.LabelFrame(main, text='Restoration', padding=8)
        controls.grid(row=2, column=0, sticky='ew')
        row = ttk.Frame(controls)
        row.pack(fill='x')
        ttk.Checkbutton(row, text='Automatic strengths', variable=self.automatic,
                        command=self.toggle_automatic).pack(side='left')
        ttk.Checkbutton(row, text='Use color reference', variable=self.reference_enabled).pack(side='left', padx=10)
        ttk.Label(row, text='Color method:').pack(side='left')
        ttk.Combobox(row, state='readonly', values=METHODS, textvariable=self.color_method, width=15).pack(side='left', padx=6)
        ttk.Label(row, text='Result zoom:').pack(side='left', padx=(12, 0))
        zoom = ttk.Combobox(row, state='readonly', values=('Fit', '100%', '200%', '400%'), textvariable=self.zoom, width=6)
        zoom.pack(side='left', padx=6)
        zoom.bind('<<ComboboxSelected>>', self.schedule_redraw)
        theme = ttk.Combobox(row, state='readonly', values=('System', 'Dark', 'Light'), textvariable=self.theme, width=8)
        theme.pack(side='right')
        theme.bind('<<ComboboxSelected>>', self.apply_theme)
        ttk.Label(controls, text='Run analyzes noise and surfaces. Color-method changes require Run; matching inference is reused.').pack(anchor='w', pady=(5, 0))
        self.manual = ttk.Frame(main)
        for column, (label, variable, maximum) in enumerate((('Denoise %', self.denoise, 100),
                ('Deblotch %', self.deblotch, 200), ('Color correction %', self.color, 100))):
            self.manual.columnconfigure(column, weight=1, uniform='manual')
            frame = ttk.Frame(self.manual)
            frame.grid(row=0, column=column, sticky='ew', padx=6)
            ttk.Label(frame, text=label).pack(side='left')
            ttk.Spinbox(frame, from_=0, to=maximum, increment=5, textvariable=variable, width=5).pack(side='right')
            ttk.Scale(frame, variable=variable, from_=0, to=maximum).pack(fill='x', padx=6)
        ttk.Label(self.manual, text='Deblotch/color update from cache. Denoise, reference or color-method changes require Run; matching SCUNet inference is reused.').grid(row=1, column=0, columnspan=3, sticky='w', pady=4)
        self.deblotch.trace_add('write', self.schedule_render)
        self.color.trace_add('write', self.schedule_render)
        previews = ttk.Frame(main)
        previews.grid(row=4, column=0, sticky='nsew', pady=8)
        previews.rowconfigure(0, weight=1)
        for column, (key, title) in enumerate((('reference', 'COLOR REFERENCE (optional)'), ('edited', 'IMAGE'), ('result', 'RESULT'))):
            previews.columnconfigure(column, weight=1, uniform='preview')
            frame = ttk.LabelFrame(previews, text=title, padding=3)
            frame.grid(row=0, column=column, sticky='nsew', padx=3)
            canvas = tk.Canvas(frame, highlightthickness=0, width=200, height=220)
            canvas.pack(fill='both', expand=True)
            canvas.bind('<Configure>', self.schedule_redraw)
            self.canvases[key] = canvas
            if key == 'result':
                canvas.bind('<ButtonPress-1>', self.start_pan)
                canvas.bind('<B1-Motion>', self.pan)
            else:
                canvas.bind('<Double-Button-1>', lambda e, k=key: self.open_file(k))
                if dnd_available:
                    for widget in (canvas, frame, self.open_buttons[key]):
                        widget.drop_target_register(DND_FILES)
                        widget.dnd_bind('<<Drop>>', lambda e, k=key: self.drop(e, k))
        ttk.Label(main, textvariable=self.info).grid(row=5, column=0, sticky='ew')
        ttk.Label(main, textvariable=self.status, wraplength=1300).grid(row=6, column=0, sticky='ew', pady=(5, 0))
        self.apply_theme()
        self.root.after(80, self.poll)

    def options(self):
        # In automatic mode unfinished manual widget edits cannot block Run.
        values = {} if self.automatic.get() else dict(denoise=self.denoise.get(), deblotch=self.deblotch.get(), color=self.color.get())
        return Options(automatic=self.automatic.get(), reference=self.reference_enabled.get(),
                       color_method=self.color_method.get(), **values).validate()

    def toggle_automatic(self):
        if self.automatic.get():
            self.manual.grid_remove()
            if self.preview is not None:
                self.status.set('Automatic strengths selected. Press Run to analyze/apply them.')
        else:
            self.manual.grid(row=3, column=0, sticky='ew', pady=6)
            if self.report:
                for name in ('denoise', 'deblotch', 'color'):
                    getattr(self, name).set(self.report['applied'][name])

    def set_image(self, key, path):
        if self.busy:
            return False
        try:
            image = load_image(path)
        except Exception as exc:
            messagebox.showerror('Open image', str(exc))
            return False
        self.images[key], self.paths[key] = image, str(path)
        if key == 'edited':
            self.cache = None
        self.invalidate()
        self.files.set(' | '.join(f'{k}: {Path(v).name} ({self.images[k].width} x {self.images[k].height})' for k,v in self.paths.items()))
        return True

    def invalidate(self):
        self.generation += 1
        self.preview = self.displayed_preview = None
        self.result, self.report = None, {}
        self.center = (.5, .5)
        self.status.set('Input changed. Press Run.')
        self.schedule_redraw()

    def clear_reference(self):
        if not self.busy:
            self.images['reference'] = None
            self.paths.pop('reference', None)
            self.invalidate()
            self.files.set('Reference cleared; restoration can run without one.')

    def open_file(self, key):
        if self.busy:
            return
        path = filedialog.askopenfilename(filetypes=[('Images', '*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff'), ('All files', '*.*')])
        if path:
            self.set_image(key, path)

    def drop(self, event, key):
        if self.busy:
            return REFUSE_DROP
        try:
            path = drop_path(self.root.tk, event.data)
        except (ValueError, tk.TclError) as exc:
            self.status.set(str(exc))
            return REFUSE_DROP
        return COPY if self.set_image(key, path) else REFUSE_DROP

    def progress(self, text):
        self.queue.put(('progress', text))

    def run(self):
        if self.busy:
            return
        try:
            if self.images['edited'] is None:
                raise ValueError('Open an image first.')
            opts = self.options()
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning('Inputs/settings', str(exc))
            return
        source = self.images['edited'].copy()
        reference = self.images['reference'].copy() if self.images['reference'] is not None else None
        self.generation += 1
        generation = self.generation
        self.busy, self.started, self.phase = True, perf_counter(), 'Analyzing restoration'
        self.status.set(self.phase)
        cached = self.cache
        def worker():
            try:
                prepared = prepare(reference, source, opts, self.progress, cached=cached)
                self.queue.put(('ready', (generation, prepared)))
            except Exception as exc:
                self.queue.put(('failed', (generation, str(exc))))
        Thread(target=worker, daemon=True).start()

    def schedule_render(self, *args):
        if self._render_job is None:
            self._render_job = self.root.after(40, self.render_manual)

    def render_manual(self):
        self._render_job = None
        if self.busy or self.preview is None or self.automatic.get():
            return
        try:
            if self.denoise.get() != self.preview.report['prepared_strengths']['denoise'] or self.color_method.get() != self.preview.report['options']['color_method'] or self.reference_enabled.get() != self.preview.report['options']['reference']:
                self.status.set('Denoise/reference/method changed. Press Run; matching model inference is reused.')
                return
            image, report = self.preview.render(self.deblotch.get(), self.color.get(), automatic=False)
        except (ValueError, tk.TclError):
            self.status.set('Enter valid strengths. The previous result is retained.')
            return
        self.display(self.preview, image, report)

    def display(self, preview, image, report):
        self.displayed_preview = preview
        self.result, self.report = image, report
        a = report['applied']
        method = color_method_label(report['color_correction']) if a['color'] else 'Off'
        mode = 'Automatic' if a['automatic'] else 'Manual'
        self.info.set(f'{mode} | Denoise {a["denoise"]:g}% | Deblotch {a["deblotch"]:g}% | Color {a["color"]:g}% ({method})')
        self.status.set('Ready. Zoom and drag the result to inspect it. Manual deblotch/color previews do not repeat model inference.')
        self.schedule_redraw()

    def poll(self):
        try:
            while True:
                kind, data = self.queue.get_nowait()
                if kind == 'progress':
                    self.phase = data
                    continue
                if kind in ('ready', 'failed'):
                    if data[0] != self.generation:
                        continue
                    self.busy, self.started = False, None
                    if kind == 'failed':
                        self.status.set('Restoration failed; the previous result is retained.')
                        messagebox.showerror('Restore', data[1])
                        continue
                    prepared = data[1]
                    self.preview, self.cache = prepared, prepared.cache
                    image, report = prepared.render()
                    self.display(prepared, image, report)
                elif kind == 'installed':
                    self.busy, self.started = False, None
                    self.status.set('SCUNet installed and weights verified. Restart the app.')
                elif kind == 'install_error':
                    self.busy, self.started = False, None
                    self.status.set('SCUNet setup failed.')
                    messagebox.showerror('SCUNet setup', data)
        except Empty:
            pass
        if self.busy and self.started is not None:
            self.status.set(f'{self.phase} | {perf_counter()-self.started:.1f}s')
        self.root.after(80, self.poll)

    def save(self):
        if self.result is None:
            return
        path = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('PNG', '*.png')])
        if path:
            try:
                save_result(self.result, self.report, path)
                self.status.set('Saved native PNG and actual applied settings.')
            except Exception as exc:
                messagebox.showerror('Save', str(exc))

    def save_bundle(self):
        if self.busy or self.result is None:
            return
        parent = filedialog.askdirectory(title='Save restoration test')
        if parent:
            try:
                directory = Path(parent)/datetime.now().strftime('stable_shift_v224_%Y%m%d_%H%M%S_%f')
                path = save_test(self.displayed_preview, self.result, self.report,
                    self.images['edited'], self.images['reference'], directory)
                self.status.set('Saved test: '+str(path))
            except Exception as exc:
                messagebox.showerror('Save test', str(exc))

    def install_scunet(self, accelerator):
        if self.busy:
            return
        from .scunet import install_commands, ensure_weights
        self.busy, self.started, self.phase = True, perf_counter(), 'Setting up SCUNet'
        def worker():
            try:
                commands = install_commands(sys.executable, accelerator)
                probe = 'import torch, torchvision'+("; assert torch.cuda.is_available(), 'CUDA is unavailable'" if accelerator == 'nvidia' else '')
                checked = subprocess.run([sys.executable, '-c', probe], capture_output=True, text=True, timeout=90)
                for command in commands[1:] if checked.returncode == 0 else commands:
                    process = subprocess.run(command, capture_output=True, text=True, timeout=1800)
                    if process.returncode:
                        raise RuntimeError((process.stderr or process.stdout)[-2000:])
                verified = subprocess.run([sys.executable, '-c', probe+'; import spandrel'], capture_output=True, text=True, timeout=90)
                if verified.returncode:
                    raise RuntimeError((verified.stderr or verified.stdout)[-2000:])
                ensure_weights(progress=self.progress)
                self.queue.put(('installed', None))
            except Exception as exc:
                self.queue.put(('install_error', str(exc)))
        Thread(target=worker, daemon=True).start()

    def apply_theme(self, event=None):
        dark = self.theme.get() != 'Light'
        if self.theme.get() == 'System':
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                    dark = winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] == 0
            except (ImportError, OSError):
                pass
        self._colors = ('#202124', '#eceff4', '#363a40', '#151719') if dark else ('#eeeeee', '#17191c', '#d5d9df', '#dfe3e8')
        bg, fg, field, canvas_bg = self._colors
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', background=bg, foreground=fg, fieldbackground=field)
        style.map('TCombobox', fieldbackground=[('readonly', field)], foreground=[('readonly', fg)], selectbackground=[('readonly', field)], selectforeground=[('readonly', fg)])
        style.configure('TSpinbox', fieldbackground=field, foreground=fg, arrowcolor=fg)
        style.map('TButton', background=[('active', field)], foreground=[('active', fg)])
        self.root.configure(background=bg)
        for canvas in self.canvases.values():
            canvas.configure(background=canvas_bg)
        self.schedule_redraw()

    def schedule_redraw(self, event=None):
        if self._redraw_job is None:
            self._redraw_job = self.root.after(30, self.redraw)

    def redraw(self):
        self._redraw_job = None
        for key, canvas in self.canvases.items():
            canvas.delete('all')
            width, height = max(80, canvas.winfo_width()), max(80, canvas.winfo_height())
            image = self.result if key == 'result' else self.images[key]
            if image is None:
                canvas.create_text(width/2, height/2, text='Run to restore' if key == 'result' else 'Drop an image here\nor use Open', fill=self._colors[1], justify='center')
                self.photos.pop(key, None)
                continue
            if key == 'result':
                thumb, self._view_box = result_view(image, (width-8, height-8), self.zoom.get(), self.center)
            else:
                thumb = ImageOps.contain(image, (width-8, height-8), Image.Resampling.LANCZOS)
            self.photos[key] = ImageTk.PhotoImage(thumb)
            canvas.create_image(width/2, height/2, image=self.photos[key])

    def start_pan(self, event):
        if self.result is None or self.zoom.get() == 'Fit' or self._view_box is None:
            return
        left, top, right, bottom = self._view_box
        self._drag_start = event.x, event.y, ((left+right)/(2*self.result.width), (top+bottom)/(2*self.result.height))

    def pan(self, event):
        if self._drag_start is None or self.result is None or self.zoom.get() == 'Fit':
            return
        x, y, center = self._drag_start
        scale = float(self.zoom.get().removesuffix('%'))/100
        self.center = (max(0, min(1, center[0]-(event.x-x)/(scale*self.result.width))),
                       max(0, min(1, center[1]-(event.y-y)/(scale*self.result.height))))
        self.schedule_redraw()


def main():
    root = tk.Tk()
    available, error = False, ''
    try:
        if TkinterDnD is None:
            raise ImportError('tkinterdnd2 unavailable; restart using START_Stable_Shift.bat.')
        TkinterDnD.require(root)
        available = True
    except (ImportError, RuntimeError, tk.TclError) as exc:
        error = str(exc)
        try:
            (ROOT/'startup.log').write_text(error, encoding='utf-8')
        except OSError:
            pass
    App(root, available, error)
    root.mainloop()


if __name__ == '__main__':
    main()

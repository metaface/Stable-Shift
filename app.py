"""Lean Tk front end for Difference Guard Boundary Lab v1.0."""
from pathlib import Path
from threading import Thread
from queue import Queue,Empty
import traceback,json,sys,subprocess
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk,ImageOps,ImageDraw
from engine import Options,restore_quality,preserve_edits,heatmap

ROOT=Path(__file__).resolve().parent

class App:
    def __init__(self,root):
        self.root=root;root.title('Difference Guard v1.1 — Restoration Lab')
        root.geometry('1260x830');root.minsize(900,620)
        self.images={'clean':None,'edited':None}
        self.paths={};self.result=None;self.maps={};self.queue=Queue();self.busy=False
        self.mode=tk.StringVar(value='Restore Quality')
        self.method=tk.StringVar(value='CPU BM3D')
        self.cleanup=tk.IntVar(value=0)
        self.theme=tk.StringVar(value='System')
        self.started=None
        self.auto_palette=tk.BooleanVar(value=True)
        self.noise=tk.IntVar(value=50);self.chroma=tk.IntVar(value=55)
        self.hard=tk.IntVar(value=100);self.soft=tk.IntVar(value=60)
        self.shade=tk.IntVar(value=35);self.edit=tk.IntVar(value=23)
        self.status=tk.StringVar(value='Load a clean reference and edited image. Reference may be a different resolution.')
        main=ttk.Frame(root,padding=8);main.pack(fill='both',expand=True)
        bar=ttk.Frame(main);bar.pack(fill='x')
        for key,text in [('clean','1. Clean reference'),('edited','2. Edited image')]:
            ttk.Button(bar,text=text,command=lambda k=key:self.open_file(k)).pack(side='left',padx=(0,8))
        ttk.Button(bar,text='Run / Preview',command=self.run).pack(side='right')
        ttk.Button(bar,text='Compare denoisers',command=self.compare).pack(side='right',padx=8)
        ttk.Button(bar,text='Save PNG',command=self.save).pack(side='right',padx=8)
        ttk.Button(bar,text='Save diagnostic maps',command=self.save_maps).pack(side='right',padx=8)
        self.file_info=ttk.Label(main,text='No images loaded',anchor='w');self.file_info.pack(fill='x',pady=(4,7))
        options=ttk.LabelFrame(main,text='Focused controls',padding=8);options.pack(fill='x')
        row=ttk.Frame(options);row.pack(fill='x')
        ttk.Label(row,text='Task:').pack(side='left')
        ttk.Combobox(row,textvariable=self.mode,values=['Restore Quality','Preserve Edits'],state='readonly',width=20).pack(side='left',padx=6)
        ttk.Label(row,text='Denoiser:').pack(side='left',padx=(14,0))
        ttk.Combobox(row,textvariable=self.method,values=['CPU BM3D','GPU BM3D','NLM','Boundary constrained','Color only'],state='readonly',width=18).pack(side='left',padx=6)
        ttk.Checkbutton(row,text='Reference palette correction (after denoising)',variable=self.auto_palette).pack(side='left',padx=15)
        ttk.Button(row,text='Install CPU BM3D',command=self.install_bm3d).pack(side='right',padx=(10,0))
        extra=ttk.Frame(options);extra.pack(fill='x',pady=5)
        ttk.Button(extra,text='Install GPU BM3D (CUDA 12)',command=self.install_gpu).pack(side='right')
        ttk.Label(extra,text='Theme:').pack(side='left')
        theme_box=ttk.Combobox(extra,textvariable=self.theme,values=['System','Dark','Light'],state='readonly',width=9)
        theme_box.pack(side='left',padx=6);theme_box.bind('<<ComboboxSelected>>',lambda e:self.apply_theme())
        ttk.Label(options,text='Boundary constrained: edges restrict smoothing internally. BM3D/NLM: edge pixels restored afterward.',).pack(anchor='w',pady=(6,0))
        self.scales=ttk.Frame(options);self.scales.pack(fill='x',pady=(8,0))
        self._scale('Luminance noise',self.noise,0,100,0,0)
        self._scale('Color noise',self.chroma,0,100,0,1)
        self._scale('Hard edge protection',self.hard,0,100,0,2)
        self._scale('Soft shading edges',self.soft,0,100,1,0)
        self._scale('Shading detection sensitivity',self.shade,0,100,1,1)
        self._scale('Preserve-Edit sensitivity (legacy task only)',self.edit,3,90,1,2)
        self._scale('Optional chroma cleanup (0 = off)',self.cleanup,0,100,2,0)
        previews=ttk.Frame(main);previews.pack(fill='both',expand=True,pady=(8,4))
        self.preview_labels=[]
        for i,(name,key) in enumerate([('CLEAN','clean'),('EDITED','edited'),('RESULT','result')]):
            f=ttk.LabelFrame(previews,text=name,padding=3);f.pack(side='left',fill='both',expand=True,padx=3)
            l=ttk.Label(f,anchor='center');l.pack(fill='both',expand=True)
            self.preview_labels.append(l)
        ttk.Label(main,textvariable=self.status,anchor='w').pack(fill='x')
        self.root.bind('<Configure>',self.redraw)
        self.apply_theme()
        self.root.after(500,self.tick)
        self.root.after(120,self.poll)

    def install_gpu(self):
        self.install_bm3d('bm3d-cupy[cuda12]==0.1.3')

    def tick(self):
        import time
        if self.busy and self.started is not None:
            self.status.set(f'Processing: {time.perf_counter()-self.started:.1f}s elapsed (first GPU run includes initialization)')
        if self.theme.get()=='System':self.apply_theme()
        self.root.after(500,self.tick)

    def apply_theme(self):
        dark=True
        if self.theme.get()=='System':
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                    dark=winreg.QueryValueEx(key,'AppsUseLightTheme')[0]==0
            except (ImportError,OSError):pass
        else:dark=self.theme.get()=='Dark'
        colors=('#202124','#e8eaed','#35373b') if dark else ('#eeeeee','#171717','#d5d5d5')
        if getattr(self,'_colors',None)==colors:return
        self._colors=colors
        bg,fg,field=colors
        style=ttk.Style(self.root);style.theme_use('clam')
        style.configure('.',background=bg,foreground=fg,fieldbackground=field)
        style.configure('TCombobox',fieldbackground=field,background=field,foreground=fg)
        style.map('TCombobox',fieldbackground=[('readonly',field)],foreground=[('readonly',fg)],selectbackground=[('readonly',field)],selectforeground=[('readonly',fg)])
        style.map('TButton',background=[('active',field)],foreground=[('active',fg)])
        style.configure('Horizontal.TScale',background=bg,troughcolor=field)
        self.root.configure(background=bg)
        self.root.option_add('*TCombobox*Listbox.background',field)
        self.root.option_add('*TCombobox*Listbox.foreground',fg)

    def _scale(self,name,var,start,end,row,col):
        f=ttk.Frame(self.scales);f.grid(row=row,column=col,sticky='ew',padx=6,pady=2)
        ttk.Label(f,text=name).pack(anchor='w')
        z=ttk.Frame(f);z.pack(fill='x')
        ttk.Scale(z,from_=start,to=end,variable=var).pack(side='left',fill='x',expand=True)
        ttk.Label(z,textvariable=var,width=4).pack(side='left')
        self.scales.columnconfigure(col,weight=1)

    def open_file(self,key):
        p=filedialog.askopenfilename(filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff'),('All files','*.*')]);
        if not p:return
        try:
            im=Image.open(p).convert('RGB');im.load();self.images[key]=im;self.paths[key]=p
            self.file_info.configure(text='  |  '.join(f'{k}: {Path(v).name}' for k,v in self.paths.items()))
            self.status.set(f'Loaded {key}: {im.width} x {im.height}')
            self.redraw()
        except Exception as e:messagebox.showerror('Open image',str(e))

    def install_bm3d(self, package="bm3d==4.0.3"):
        # Install only into the interpreter running this app.
        if self.busy:return
        if not messagebox.askyesno('Install optional BM3D',
                "Install BM3D into THIS application\'s Python environment?\n\n"
                'Internet access required. GPU installation requires a compatible NVIDIA driver and may download large CUDA libraries. CPU BM3D uses a non-commercial license; '
                'check its terms before installation.'):
            return
        self.busy=True
        self.status.set('Installing BM3D into this application environment...')
        def job():
            try:
                proc=subprocess.run([sys.executable,'-m','pip','install',package],
                                    capture_output=True,text=True,timeout=1200)
                if proc.returncode:
                    raise RuntimeError((proc.stderr or proc.stdout)[-1800:])
                self.queue.put(('installed',package+' installed into: '+sys.executable))
            except Exception as exc:
                self.queue.put(('error',(str(exc),traceback.format_exc())))
        Thread(target=job,daemon=True).start()

    def compare(self):
        if self.busy:return
        if self.images['clean'] is None or self.images['edited'] is None:
            messagebox.showwarning('Missing images','Load reference and edited images.');return
        directory=filedialog.askdirectory(title='Save denoiser comparison')
        if not directory:return
        self.busy=True;self.status.set('Comparing NLM and boundary-constrained denoising; BM3D if installed...')
        clean=self.images['clean'].copy();edit=self.images['edited'].copy()
        options=self.opts()
        def job():
            try:
                from dataclasses import replace
                import json
                from PIL import ImageDraw,ImageOps
                outs=[]
                import importlib.util
                methods=['Color only','NLM']
                if options.method=='GPU BM3D':methods.append('GPU BM3D')
                if importlib.util.find_spec('bm3d') is not None:methods.append('CPU BM3D')
                for name in methods:
                    out,run_maps=restore_quality(clean,edit,replace(options,method=name),diagnostics=False)
                    Path(directory,f'{name.replace(" ","_")}_timing.json').write_text(json.dumps(run_maps['report'],indent=2))
                    slug=name.lower().replace(' (optional)','').replace(' ','_')
                    out.save(str(Path(directory)/(f'restored_{slug}.png')))
                    outs.append((name,out))
                inputs=[('Clean reference',clean),('Edited input',edit)]+outs
                thumbs=[]
                for name,im in inputs:
                    thumb=ImageOps.contain(im.convert('RGB'),(680,680),Image.Resampling.LANCZOS)
                    tile=Image.new('RGB',(690,730),'#fafafa');d=ImageDraw.Draw(tile)
                    tile.paste(thumb,((690-thumb.width)//2,46));d.text((15,15),name,fill=(20,20,20))
                    thumbs.append(tile)
                sheet=Image.new('RGB',(690*len(thumbs),730),'white')
                for i,im in enumerate(thumbs):sheet.paste(im,(i*690,0))
                sheet.save(str(Path(directory)/'comparison.jpg'),quality=95)
                # Identical native-resolution crops of edited input and each output.
                crop_inputs=[('Edited',edit)]+outs
                for index,(fx,fy) in enumerate(((.40,.24),(.60,.58),(.80,.24))):
                    size=min(256,edit.width,edit.height)
                    left=max(0,min(edit.width-size,round(edit.width*fx-size/2)))
                    top=max(0,min(edit.height-size,round(edit.height*fy-size/2)))
                    crops=Image.new('RGB',((size+10)*len(crop_inputs),size+35),'#202124')
                    draw=ImageDraw.Draw(crops)
                    for col,(label,image) in enumerate(crop_inputs):
                        crops.paste(image.crop((left,top,left+size,top+size)),(col*(size+10),30))
                        draw.text((col*(size+10)+3,8),label,fill='white')
                    crops.save(Path(directory)/f'crop_{index+1}_x{left}_y{top}_100percent.png')

                Path(directory,'settings.json').write_text(json.dumps({'noise':options.noise,'color_noise':options.color_noise,
                    'hard_guard':options.hard_guard,'soft_guard':options.soft_guard,
                    'shade_threshold':options.shade_threshold,'color_match':options.color_match,'cleanup':options.cleanup,
                    'reference_size':clean.size,'edited_size':edit.size,'methods':methods},indent=2))
                self.queue.put(('compared',directory))
            except Exception as exc:self.queue.put(('error',(str(exc),traceback.format_exc())))
        Thread(target=job,daemon=True).start()

    def opts(self):
        return Options(method=self.method.get(),noise=self.noise.get(),color_noise=self.chroma.get(),
          hard_guard=self.hard.get(),soft_guard=self.soft.get(),shade_threshold=self.shade.get(),
          color_match=self.auto_palette.get(),edit_sensitivity=self.edit.get(),cleanup=self.cleanup.get())

    def run(self):
        if self.busy:return
        if self.images['clean'] is None or self.images['edited'] is None:
            messagebox.showwarning('Missing images','Load both reference and edited images.');return
        self.busy=True
        import time
        self.started=time.perf_counter();self.status.set('Processing...')
        clean=self.images['clean'].copy();edited=self.images['edited'].copy()
        opts=self.opts();mode=self.mode.get()
        def job():
            try:
                if mode=='Restore Quality':out,maps=restore_quality(clean,edited,opts,diagnostics=True)
                else:out,maps=preserve_edits(clean,edited,opts)
                self.queue.put(('ok',(out,maps)))
            except Exception as exc:self.queue.put(('error',(str(exc),traceback.format_exc())))
        Thread(target=job,daemon=True).start()

    def poll(self):
        try:
            while True:
                k,data=self.queue.get_nowait()
                self.busy=False
                if k=='installed':
                    self.status.set(data)
                    messagebox.showinfo('BM3D installation',data+'\nSelect the corresponding CPU or GPU backend.')
                    continue
                if k=='compared':
                    self.status.set(f'Comparison saved to {data}: full-resolution PNGs, sheet, settings.')
                    continue
                if k=='ok':
                    self.result,self.maps=data
                    report=self.maps.get('report',{})
                    self.started=None
                    self.status.set('Finished: '+str(report.get('backend','Preserve Edits'))+' | '+ ' | '.join(f'{k.replace("_seconds","")}: {v:.2f}s' for k,v in report.items() if k.endswith('_seconds'))) 
                    self.redraw()
                else:
                    self.status.set('Processing failed.');messagebox.showerror('Restoration error',data[0]+'\n\n'+data[1][-1500:])
        except Empty:pass
        self.root.after(120,self.poll)

    def redraw(self,event=None):
        try:
            w=max(150,(self.root.winfo_width()-50)//3)
            h=max(140,self.root.winfo_height()-290)
            for lab,key in zip(self.preview_labels,['clean','edited','result']):
                im=self.result if key=='result' else self.images[key]
                if im is None:lab.configure(image='',text='No image');continue
                im=ImageOps.contain(im,(w,h),Image.Resampling.LANCZOS)
                photo=ImageTk.PhotoImage(im);lab.configure(image=photo,text='');lab.image=photo
        except Exception:pass

    def save(self):
        if self.result is None:return messagebox.showwarning('No result','Run a restoration first.')
        p=filedialog.asksaveasfilename(defaultextension='.png',filetypes=[('PNG','*.png')]);
        if p:
            self.result.save(p)
            Path(p).with_suffix('.settings.json').write_text(json.dumps({'options':self.maps.get('report',{}).get('options',vars(self.opts())),'report':self.maps.get('report',{})},indent=2))
            self.status.set(f'Saved {p} and settings/timings JSON')

    def save_maps(self):
        if not self.maps:return messagebox.showwarning('No maps','Run a restoration first.')
        d=filedialog.askdirectory(title='Save map images');
        if not d:return
        count=0
        for name,arr in self.maps.items():
            import numpy as np
            if not isinstance(arr,np.ndarray) or arr.ndim!=2:continue
            if name=='distance':save=heatmap(np.clip(arr/18,0,1))
            elif name in ('hard','soft','guard','difference','cleanup'):save=heatmap(arr)
            else:continue
            save.save(str(Path(d)/(name+'.png')));count+=1
        self.status.set(f'Saved {count} diagnostic maps to {d}')

if __name__=='__main__':
    root=tk.Tk()
    try:
        style=ttk.Style(root)
        if 'clam' in style.theme_names():style.theme_use('clam')
    except Exception:pass
    App(root);root.mainloop()

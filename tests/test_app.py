import json
import os
import time
import numpy as np
from PIL import Image
import pytest
from stable_shift import pipeline
from tests.test_core import scene

pytestmark=pytest.mark.skipif(os.name!='nt' and not os.environ.get('DISPLAY'),reason='Tk needs a display')


def app():
    from tkinterdnd2 import TkinterDnD
    from stable_shift.app import App
    root=TkinterDnD.Tk(); ui=App(root,True);root.update()
    return root,ui


def finish(root,ui):
    end=time.monotonic()+10
    while ui.busy and time.monotonic()<end:
        root.update();time.sleep(.01)
    assert not ui.busy


def close(root):
    for job in root.tk.call('after','info'):root.after_cancel(job)
    root.destroy()


def test_auto_run_manual_cache_and_exact_applied_save(tmp_path,monkeypatch):
    from stable_shift.app import filedialog,messagebox
    root,ui=app()
    try:
        for key in ('showerror','showwarning'):monkeypatch.setattr(messagebox,key,lambda *a:pytest.fail(str(a)))
        image=scene();image=np.uint8(np.clip(image.astype(float)+np.random.default_rng(1).normal(0,2,image.shape)+.5,0,255))
        path=tmp_path/'source café.png';Image.fromarray(image).save(path)
        assert ui.set_image('edited',path) and ui.automatic.get()
        calls=[]
        def model(rgb,progress):calls.append(True);return rgb.copy(),{'device_name':'Test stub'}
        monkeypatch.setattr(pipeline,'denoise',model)
        ui.run();finish(root,ui)
        assert ui.report['applied']['automatic'] and 'Automatic' in ui.info.get()
        ui.automatic.set(False);ui.toggle_automatic();ui.deblotch.set(145);ui.render_manual()
        assert ui.report['applied']['deblotch']==145
        old=np.array(ui.result);ui.deblotch.set(200)  # pending widget edit must not mislabel a save
        target=tmp_path/'saved.png';monkeypatch.setattr(filedialog,'asksaveasfilename',lambda **k:str(target));ui.save()
        np.testing.assert_array_equal(Image.open(target),old)
        assert json.loads(target.with_suffix('.settings.json').read_text())['applied']['deblotch']==145
        ui.denoise.set(50);ui.run();finish(root,ui)
        assert len(calls)==1 and ui.report['applied']['denoise']==50
        ui.zoom.set('200%');ui.redraw();assert ui._view_box is not None
    finally:close(root)


def test_failed_and_stale_workers_cannot_replace_the_last_result(tmp_path,monkeypatch):
    from stable_shift.app import messagebox
    root,ui=app()
    try:
        p=tmp_path/'source.png';Image.fromarray(scene()).save(p);ui.set_image('edited',p)
        ui.automatic.set(False);ui.toggle_automatic()
        retained=Image.new('RGB',(17,19),'red');ui.result=retained
        def failure(*a,**k):raise RuntimeError('model unavailable')
        monkeypatch.setattr(pipeline,'denoise',failure)
        errors=[];monkeypatch.setattr(messagebox,'showerror',lambda *a:errors.append(a))
        ui.run();finish(root,ui)
        assert ui.result is retained and errors
        ui.busy=True;ui.queue.put(('ready',(ui.generation-1,object())));ui.poll()
        assert ui.busy and ui.result is retained
    finally:close(root)

"""Always-visible restoration panel; independent of the Script dropdown."""
import gradio as gr
from modules import scripts

from stable_shift import forge
from stable_shift.global_color import METHODS
from stable_shift.pipeline import Options


def settings(enabled=False, automatic=True, reference_mode='Starting image',
             reference_image=None, method='Robust global', denoise=100,
             deblotch=100, color=100, save_test=True):
    return forge.Settings(enabled, Options(automatic=automatic, denoise=denoise,
        deblotch=deblotch, color=color, reference=reference_mode != 'Off', color_method=method),
        reference_mode, reference_image, save_test)


class StableShift(scripts.Script):
    def title(self):
        return 'Stable Shift'

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        with gr.Accordion('Stable Shift', open=False):
            enabled = gr.Checkbox(value=False, label='Enable Stable Shift')
            gr.Markdown('Restores each image before saving or passing it to the next step. '
                        'Choose Loopback or another script in the normal Script dropdown.')
            automatic = gr.Checkbox(value=True, label='Automatic restoration strengths')
            with gr.Accordion('Color reference (optional)', open=False):
                reference_mode = gr.Dropdown(choices=forge.REFERENCE_MODES,
                    value='Starting image' if is_img2img else 'Off', label='Color reference',
                    info='Fixed throughout the run. For txt2img, upload a reference to enable color correction.')
                reference_image = gr.Image(type='pil', sources=['upload'],
                                           label='Uploaded color reference', visible=False)
                method = gr.Dropdown(choices=METHODS, value='Robust global', label='Color method')
            with gr.Accordion('Manual restoration strengths', open=False, visible=False) as manual:
                denoise = gr.Slider(0, 100, value=100, step=5, label='SCUNet denoise (%)')
                deblotch = gr.Slider(0, 200, value=100, step=5, label='Deblotch (%)')
                color = gr.Slider(0, 100, value=100, step=5, label='Reference color correction (%)')
            save_test = gr.Checkbox(value=True, label='Save generated/restored comparison files and report',
                info='Saved under the normal image output folder / stable-shift.')
        automatic.change(lambda value: gr.update(visible=not value), automatic, manual)
        reference_mode.change(lambda mode: gr.update(visible=mode == 'Uploaded reference'),
                              reference_mode, reference_image)
        self.infotext_fields = [(enabled, 'Stable Shift enabled'), (automatic, 'Stable Shift automatic'),
            (reference_mode, 'Stable Shift reference'), (method, 'Stable Shift requested color method'),
            (denoise, 'Stable Shift requested denoise'), (deblotch, 'Stable Shift requested deblotch'),
            (color, 'Stable Shift requested color')]
        return [enabled, automatic, reference_mode, reference_image, method,
                denoise, deblotch, color, save_test]

    def setup(self, p, *args):
        forge.setup(p, settings(*args))

    def process(self, p, *args):
        forge.begin(p, settings(*args))

    def postprocess_image_after_composite(self, p, pp, *args):
        forge.process_image(p, pp, settings(*args))

    def postprocess(self, p, processed, *args):
        forge.finish(p, processed, settings(*args))

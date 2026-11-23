"""Always-visible restoration panel; independent of the Script dropdown."""
import gradio as gr
from modules import scripts

from stable_shift import forge
from stable_shift.color_shift import ColorShift, preview
from stable_shift.global_color import METHODS
from stable_shift.pipeline import Options


def settings(enabled=False, automatic=True, reference_mode='Starting image',
             reference_image=None, method='Robust global', denoise=100,
             deblotch=100, color=100, save_test=True, shift_enabled=False,
             exposure=0., red=0., blue=0., saturation=0.):
    return forge.Settings(enabled, Options(automatic=automatic, denoise=denoise,
        deblotch=deblotch, color=color, reference=reference_mode != 'Off', color_method=method),
        reference_mode, reference_image, save_test,
        ColorShift(shift_enabled, exposure, red, blue, saturation))


def preview_colors(image, source, reference, count, exposure, red, blue, saturation):
    image = next((item for item in (image, source, reference) if item is not None), None)
    try:
        return preview(image, count, exposure=exposure, red=red, blue=blue, saturation=saturation)
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc


class StableShift(scripts.Script):
    _preview_source = None
    _capture_background = False

    def title(self):
        return 'Stable Shift'

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def after_component(self, component, **kwargs):
        if not self.is_img2img:
            return
        # Neo's ForgeCanvas uses a hidden LogicalImage as its actual PIL input.
        if kwargs.get('elem_id') == 'img2img_image':
            self._capture_background = True
        elif self._capture_background and 'logical_image_background' in (kwargs.get('elem_classes') or []):
            self._preview_source = component
            self._capture_background = False

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
            with gr.Accordion('Color changes per loop', open=False):
                shift_enabled = gr.Checkbox(value=False, label='Apply color changes per loop')
                gr.Markdown('Each loop applies one step after restoration. With a color reference, '
                            'correction follows the changing lighting. Zero values leave colors unchanged.')
                exposure = gr.Slider(-.5, .5, value=0, step=.01, label='Exposure per loop (EV)',
                    info='Negative darkens; positive brightens. One EV doubles linear-light brightness.')
                red = gr.Slider(-.25, .25, value=0, step=.01, label='Red / cyan per loop (EV)',
                    info='Positive adds red; negative adds cyan.')
                blue = gr.Slider(-.25, .25, value=0, step=.01, label='Blue / yellow per loop (EV)',
                    info='Positive adds blue; negative adds yellow. Combine both balances for other color directions.')
                saturation = gr.Slider(-25, 25, value=0, step=1, label='Saturation change per loop (%)')
                with gr.Accordion('Preview cumulative colors', open=False):
                    preview_image = gr.Image(type='pil', sources=['upload'], label='Preview image (optional)')
                    gr.Markdown('Uses the img2img input or uploaded color reference when no preview image is supplied. '
                                'Shows color changes on a still image, without generation or denoising. '
                                'The preview works before enabling Apply color changes per loop.')
                    loops = gr.Slider(1, 100, value=10, step=1, label='Loops to preview')
                    preview_button = gr.Button('Preview color progression')
                    previews = gr.Gallery(label='Color progression', columns=4, format='png', height='auto')
            save_test = gr.Checkbox(value=True, label='Save generated/restored comparison files and report',
                info='Saved under the normal image output folder / stable-shift.')
        automatic.change(lambda value: gr.update(visible=not value), automatic, manual)
        reference_mode.change(lambda mode: gr.update(visible=mode == 'Uploaded reference'),
                              reference_mode, reference_image)
        source = self._preview_source if self._preview_source is not None else gr.State(None)
        preview_button.click(preview_colors,
            [preview_image, source, reference_image, loops, exposure, red, blue, saturation], previews)
        self.infotext_fields = [(enabled, 'Stable Shift enabled'), (automatic, 'Stable Shift automatic'),
            (reference_mode, 'Stable Shift reference'), (method, 'Stable Shift requested color method'),
            (denoise, 'Stable Shift requested denoise'), (deblotch, 'Stable Shift requested deblotch'),
            (color, 'Stable Shift requested color'), (shift_enabled, 'Stable Shift shift enabled'),
            (exposure, 'Stable Shift shift exposure'), (red, 'Stable Shift shift red'),
            (blue, 'Stable Shift shift blue'), (saturation, 'Stable Shift shift saturation')]
        return [enabled, automatic, reference_mode, reference_image, method,
                denoise, deblotch, color, save_test, shift_enabled, exposure, red, blue, saturation]

    def setup(self, p, *args):
        forge.setup(p, settings(*args))

    def process(self, p, *args):
        forge.begin(p, settings(*args))

    def postprocess_image_after_composite(self, p, pp, *args):
        forge.process_image(p, pp, settings(*args))

    def postprocess(self, p, processed, *args):
        forge.finish(p, processed, settings(*args))

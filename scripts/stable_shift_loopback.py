"""Selectable img2img script for Forge Neo 2.33."""
import gradio as gr
from modules import scripts

from stable_shift.forge_loopback import run, REFERENCE_MODES, SEED_MODES
from stable_shift.global_color import METHODS
from stable_shift.pipeline import Options


class StableShiftLoopback(scripts.Script):
    def title(self):
        return 'Stable Shift Loopback'

    def show(self, is_img2img):
        return is_img2img

    def ui(self, is_img2img):
        gr.Markdown('Each generated image is restored before the next loop. '
                    'Use ordinary img2img with Batch size and Batch count set to 1. '
                    'Forge\'s img2img denoising strength stays constant across loops.')
        with gr.Row():
            loops = gr.Slider(1, 32, value=3, step=1, label='Loops')
            seed_mode = gr.Dropdown(choices=SEED_MODES, value='Increment', label='Seed per loop')
        automatic = gr.Checkbox(value=True, label='Automatic restoration strengths')
        with gr.Accordion('Color reference', open=False):
            reference_mode = gr.Dropdown(choices=REFERENCE_MODES, value='Starting image',
                label='Keep colors anchored to',
                info='The same reference is used for every loop.')
            reference_image = gr.Image(type='pil', sources=['upload'], label='Uploaded color reference', visible=False)
            method = gr.Dropdown(choices=METHODS, value='Robust global', label='Color method')
        with gr.Accordion('Manual restoration strengths', open=False, visible=False) as manual:
            denoise = gr.Slider(0, 100, value=100, step=5, label='SCUNet denoise (%)')
            deblotch = gr.Slider(0, 200, value=100, step=5, label='Deblotch (%)')
            color = gr.Slider(0, 100, value=100, step=5, label='Reference color correction (%)')
        save_test = gr.Checkbox(value=True, label='Save generated/restored comparison files and report',
            info='Saved under your img2img output folder / stable-shift. Useful for this first Forge test.')
        automatic.change(lambda enabled: gr.update(visible=not enabled), automatic, manual)
        reference_mode.change(lambda mode: gr.update(visible=mode == 'Uploaded reference'),
                              reference_mode, reference_image)
        return [loops, seed_mode, automatic, reference_mode, reference_image, method,
                denoise, deblotch, color, save_test]

    def run(self, p, loops, seed_mode, automatic, reference_mode, reference_image, method,
            denoise, deblotch, color, save_test):
        options = Options(automatic=automatic, denoise=denoise, deblotch=deblotch, color=color,
                          reference=reference_mode != 'Off', color_method=method)
        return run(p, loops, seed_mode, reference_mode, reference_image, options, save_test)

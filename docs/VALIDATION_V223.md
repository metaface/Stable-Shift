# V2.23 — consistent color-method selection

The SCUNet preparation previously ignored `Options.color_method`, always trying
the paired RGB fit and then V2.22's RGB palette fallback. Normal Run did honor
the selector but reported only the applied Classic fallback, which made a
failed Robust global fit look like another ignored selection.

Both active paths now use the same method picker. Classic returns the existing
frozen LAB correction. Robust global retains the existing RGB estimator and
Classic fallback. Global palette is a third explicit selector value and does
not substitute itself for the other choices. Normal Run preserves its Classic
baseline convention around broad correction. Disabled reference correction
applies none of the methods.

The result bar shows requested/applied methods near the start of its text.
Fallback reports retain the reason, and saved settings describe the displayed
result. SCUNet fits the selected correction once for all cached strength
endpoints. Changing methods can reuse matching raw inference. The model,
accepted blotch filter, and cached strength blending are unchanged. No text
mask, halo repair or new denoising operation is introduced.

Seven focused tests cover all three selector values across both color paths,
explicit fallback reporting, exact original Classic pixels with broad cleanup
off/on, reference Off, and a real Tk method-switch/save flow using one cached
model result. No historical denoising, reconstruction, stroke or AA suite was
rerun.

Cached actual SCUNet cabin/beach inputs keep their accepted RGB color output
when Robust global is selected. A cached alley output is checked against the
original Classic color stage using a controlled synthetic dark reference;
the original warm reference is only available inline, so this is not an exact
replay of the user's pair. Classic matches normal Run's color stage on the same
pixels, while Global palette remains a distinct, explicit result. Windows/CUDA
execution was unavailable, and unchanged SCUNet inference was not repeated.

Classic's inherited coarse LAB field can affect local color variation; making
it selectable does not turn it into the uniform RGB method. Global palette
can tint neutral colors. These are different user-selected correction models.

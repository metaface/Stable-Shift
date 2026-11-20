# Stable Shift V2.22 — standalone guide

## Reference lighting with different compositions

Keep **Reference color correction** enabled, then choose **Prepare SCUNet
cleanup**. V2.21 could silently disable correction if a reference with different
object positions failed the paired global fit. V2.22 instead uses **Global
palette**, a uniform RGB transfer fitted to the images' independent color
distributions. It can darken, brighten, warm or cool the target without copying
the reference's edges, texture or grid. Reliable paired fits retain their
existing coefficients. The result bar now identifies the effective reference
method; **Off** means the reference checkbox is disabled.

Every live cleanup strength shares the same frozen color coefficients,
including 0%. The SCUNet model and accepted blotch filter are unchanged. Global
palette approximates an overall look: differently colored or differently sized
objects can influence its statistics. The halo experiment is not included in
this release. See [focused checks](VALIDATION_V222.md).

## SCUNet color cleanup

Use **Prepare SCUNet cleanup** after optional SCUNet setup. The edited image
goes through the full real-PSNR model once, followed by independent regular and
strong color-averaging candidates. The result is displayed in the app. The live
slider becomes **SCUNet cleanup %**: 0 shows the model-only control, 100 applies
regular cleanup, and 200 applies stronger cleanup. Intermediate values blend
fixed endpoints; they never repeat inference, refit colors or accumulate passes.

The focused cleanup includes brightness variation as well as color because
many remaining broad patches are changes in lightness. Similar nearby model
colors are averaged with a recursive edge-aware filter at native resolution.
Large color differences limit averaging, including at clean SCUNet lines and
shade boundaries. It uses no hard protection map, region fill, raw source
copy-back, classical denoiser, pyramid, stroke reconstruction or AA. The old
denoiser, automatic-strength, local/broad and line/finishing controls do not
affect this separate path. They retain their meaning for the older tests.

Reference correction fits one uniform global RGB transform to SCUNet alone,
then applies it to the control and both candidates. It uses the reference
checkbox, with a reliable paired global fit or the independent Global palette
fallback; Classic spatial correction is not used here. Its coefficients can differ
from **Compare SCUNet**, which fits colors to the classical comparator. No
reference detail, grid or shading field is transferred. Repeating preparation
can reuse the raw model output if the edited pixels still match, while
recomputing cleanup and colors. Changing inputs clears the active live cache.

Use result zoom and pan to compare 0, 100 and 200. **Save PNG + timings** saves
the displayed image and its actual applied strength. **Save live test** writes
`scunet_cleanup_v222_<timestamp>` containing:

- `00_scunet_only.png`, with the common color correction and cleanup off.
- `01_cleanup_100.png`, `02_cleanup_200.png` and `03_selected.png`.
- `scunet_before_color.png`, the exact raw model output.
- Full inputs, native comparison crops, a sheet and actual settings/timings.
- `share_scunet_cleanup.zip` when the control, selected result and inputs fit
  within 30 MiB; additional endpoints/crops are included as space allows.

**Save maps** exports `scunet_cleanup_signed_rgb` (selected minus model-only,
native int16 RGB) and `scunet_cleanup_change` (mean absolute change / 16). These
show the applied correction, not a detected-noise probability. The raw arrays
and applied report are saved alongside display previews.

Cleanup uses contrast rather than semantic recognition. Strong settings can
soften faint lines, small stars, smoke gradients and intentional texture. This
is why the model-only endpoint stays available. Existing ordinary Run, Preserve
Edits and earlier comparisons are retained. See [V2.21 checks](VALIDATION_V221.md).

## SCUNet comparison

SCUNet is optional. The ordinary launcher and existing denoisers do not import
PyTorch or download a model. Use **SCUNet NVIDIA setup** or **SCUNet CPU setup**
once, then restart. A working matching PyTorch/torchvision runtime is reused;
otherwise setup installs matched official CPU or CUDA 12.8 wheels. Spandrel
0.4.2 loads the official `scunet_color_real_psnr.pth` model. The 72 MB weights
are downloaded from the authors' release and checked by size and SHA-256 before
an atomic cache replacement. They live in `models/`, outside Git and the small
standalone ZIP. Partial or mismatched downloads are rejected.

For the first test, keep the usual current denoiser selected and press **Compare
SCUNet**. The model runs on the edited input at full strength, without source
guards, automatic attenuation, surface cleanup, pyramid rebuilding, stroke
fitting or AA. It does not receive the color reference. The current pipeline
uses the selected denoiser/settings and live line-reconstruction strength; a
matching cached preparation is reused. Source/reference pixel signatures and
preparation settings must match before reuse.

The new `scunet_test_v220_<timestamp>` folder contains:

- `01_current_pipeline.png`: the current live pyramid at the selected strength.
- `02_scunet_only.png`: the model output with the same frozen global colors.
- `03_input_same_colors.png`: the edited input with those same colors.
- `scunet_before_color.png`: the model output before any color correction.
- Full inputs, a comparison sheet, native crops and settings/timings, plus a
  share ZIP when the two compared results and original inputs fit within 30 MiB.

Those two results and inputs take priority in the ZIP. The raw model output,
additional input control and crops are included as space allows; the JSON lists
omitted extras, which remain in the full folder.

The comparison does not replace the image currently displayed in the app.
Open the exported images/crops. If global color fitting is unreliable, all
three primary views retain their own source-space colors. Color coefficients
are reused from the current result, never refitted separately to favor SCUNet.

Inference uses float32 RGB at native resolution. Auto device selection uses
CUDA when PyTorch can initialize it, otherwise CPU. The actual device, model
checksum, PyTorch version, padded size and tiles are recorded. Inputs are
reflected to a 64-pixel grid; padding is removed afterward. Default 512-pixel
tiles overlap by 128 pixels with raised-cosine blending and aligned origins.
This controls memory but is not identical to whole-image inference. GPU memory
exhaustion retries smaller tiles, with the attempts recorded. Other errors
propagate; no replacement denoiser is silently used. CPU processing can take
minutes on large inputs.

Selecting **SCUNet** in the ordinary denoiser dropdown instead puts the model
inside the existing processing pipeline. Luminance and color sliders blend
its fixed output; they are not noise inputs to the learned network. Auto uses
the requested blend ceilings and source-derived spatial permissions, skipping
the model when no location is eligible. It does not apply BM3D's sigma-to-slider
mapping to SCUNet. The separate comparison deliberately bypasses those limits
and all subsequent cleanup for the model-only candidate. Existing
BM3D/cleanup defaults and V2.19 processing are retained. See
[validation and official sources](VALIDATION_V220.md).

## Border sampling correction

V2.19 changes **Prepare live pyramid** and **Compare line borders**. Earlier
border cleanup could follow a sampling ray into a broad filled object whose
edge had no two-sided ink profile. Selecting the farthest coarse sample could
also select its blurred dark edge. This created dark spots on previously
lighter paint before the connected-stroke fitter ran.

Rays now stop when source luminance falls more than 12 levels below the highest
value encountered while moving away from ink. Of the valid coarse samples,
the brightest paint plateau supplies the replacement; supported gentle trends
still use the existing extrapolation. Native source pixels constrain sampling
but do not become replacement texture. There is no new median cleanup or tuning
control. Restart and **Prepare live pyramid** again, then compare with the
previous saved crop at 0% as well as fitted strengths. Existing source noise
and ambiguous boundaries can remain. See [V2.19 validation](VALIDATION_V219.md).

## Live connected stroke paths

Choose **Prepare live pyramid** with the usual images/settings. Native, quarter and half processing run once. The **Line reconstruction %** slider then blends the cached traced-source base, regular fitted view and stronger fitted view. It does not rerun upstream work.

The source map is now a search region rather than permission to fit every dark component. Observed two-sided dark profiles produce a thin centerline graph. A candidate must contain at least 12 native pixels of connected arc length and eight pixels of spatial extent. Chains split at junctions; short terminal spurs are pruned. A large connected dirty texture does not qualify merely because it has many pixels. Short simple independent marks are kept as observed details and remain unfitted.

Fitting uses the same source path ID and nearby position along that path for its color, width and geometry samples. Native samples avoid interpolating colors across separate IDs. The output's edge coverage is rebuilt at 4x4 subpixel resolution. Integrated opacity is retained per path so smoothing does not silently turn into widening. Junctions, endpoints and compact dark-filled details have exclusions. Filled object rims are included in that guard so a nose is not reshaped by fitting its outline as an unrelated thin stroke.

The source trace also limits copy-back from the old native guard. Unsupported guard pixels use the existing reconstructed pyramid instead of reintroducing native texture. This is separate from fitting strength: **0** means traced preservation without fitting, **100** applies the regular fit, and **200** uses longer same-path smoothing. All views share one frozen global RGB color transform, or source colors when no reliable fit exists. The V2.17 surface-median cleanup is removed.

Use result zoom and drag to pan. Zoom uses nearest-neighbor display; the fitted stroke itself has antialiased coverage. Save always writes the full native image. **Save PNG + timings** retains the actual applied strength and preparation settings.

**Save live test** writes `00_original_preservation_base.png`, `01_reconstruction_off.png`, `02_selected.png`, `03_reconstruction_200.png`, full inputs and settings. It also includes binary accepted-centerline, filled-region and source-copy-back masks. A share ZIP is added within 30 MiB. The original base includes the current border correction and precedes trace gating; it is not a frozen earlier-version control.

**Save maps** includes `stroke_path_ids` (zero = not fitted; positive values identify individual paths, not confidence), accepted centerlines, filled exclusions and copy-back support. `source_preservation_signed_rgb` is traced zero minus original wide-preservation base; `line_preservation_signed_rgb` is the displayed result minus traced zero. They sum exactly to the total displayed change from the original base. Change maps use mean absolute RGB / 16. Exact IDs/signs stay in the NPZ; clipped color previews cannot identify every distinct path.

Changing inputs or starting normal Run clears the live cache. Other controls need Prepare again. Normal Run, optional legacy strokes/AA, Preserve Edits and comparisons other than line borders retain their prior processing. The live path fitter includes its own edge coverage, while those separate finishing switches remain off in the experiment.

This is source-based geometry rather than semantic line recognition. Missing/weak evidence, legitimate tiny features, complicated junctions, long structured texture and unrecognized filled details remain limits. See [V2.18 validation](VALIDATION_V218.md).

## Experimental reconstruction comparison

Choose **Compare reconstruction** after loading your usual pair and denoiser settings. Normal **Run / Preview** retains the accepted V2.12 processing; the new methods are only available through this comparison while they are evaluated. The engine's normal-run report therefore still identifies V2.12 processing.

The button produces four full-size images: `01_accepted.png`, `02_pyramid.png`, `03_hard_colors.png`, and `04_hard_with_gradients.png`. The candidates run at full strength. Stroke cleanup and AA are off in all four, regardless of their checkboxes. No new restoration-strength controls are required for this test.

The accepted full-resolution denoiser runs once. Quarter and half images are independently reduced from the edited source, then independently processed by the selected backend and local cleanup with broad correction off. Auto estimates their settings separately. Exact native ink is retained at the final scale using the original source-line map, rather than enlarged low-resolution ink. This costs additional denoiser time; it is not a cached preview of a previous Run.

The pyramid starts with the quarter layer, joins the half layer, and enlarges to full size with boundary guidance from the independently processed native image. The solid-color experiment uses sharp, scale-supported boundaries and the native source-line map to partition paint regions. Each region receives one robust color from its coarse samples. It does not turn every gradual color difference into a new region. Small regions without usable coarse samples use the reconstructed field, not unfiltered native texture.

The fourth view can replace a region's flat fill with a smooth LAB plane. The plane must improve held-out spatial tiles and have matching direction and amplitude at half and quarter size. Existing bright-neutral texture permission can veto the exception. It does not paste the native color residual back. This is a test for supported smooth variation, not recognition of iridescence, highlights, or noise. Curved/localized color fades can be lost, and genuine gradients can fail these tests.

All four views share one fitted **Robust global** RGB transform so color correction cannot create spatial patterns inside a solid fill. If that fit is rejected, the comparison retains source colors for all four images and reports why. The normal Run color-method selection and Classic fallback are unchanged. Reference geometry never enters reconstruction.

The comparison folder includes full inputs/results, independent coarse layers, before-color outputs, a contact sheet, eight native crops, source protection, accepted gradient regions, raw reconstruction evidence and actual settings/timings. `share_reconstruction_test.zip` includes full inputs/results and available supporting files within 30 MiB. The JSON lists omitted optional files. Raw NPZ and extra before-color images stay outside the ZIP.

Check the tree shade, tail color fades, sparkle halos and cigarette smoke. Solid fills can flatten shading where a real boundary is missed. Exact ink pixels alone do not guarantee unchanged surrounding contrast. Coarse denoising and guided reconstruction can also leave boundary rims. See [reconstruction validation](VALIDATION_V213.md).

The active code now lives in `stable_shift/`. See [cleanup notes](CLEANUP.md) for upgrading an existing folder and backing up old root scripts.

## V2.11 blotch regression removed

V2.12 removes V2.11's shading-restoration stage and restores the accepted V2.10 Robust global behavior. The attempted fix used lightness differences from Classic, including variation from the local-cleanup baseline before broad correction. That variation included coherent blotches. Tests for fine grain and one tree contrast measurement did not establish that cleaned surfaces stayed clean.

Robust global again applies only its global RGB transform to the fully cleaned pixels. The earlier baseline still estimates global coefficients, as before, but no spatial residual from that baseline is added to the output. When the fit selects Robust global, identical cleaned RGB pixels receive identical corrected RGB values regardless of position or the earlier baseline's local blotches. Classic fallback remains unchanged.

Choose **Robust global** for normal Run, or **Compare colors** for `01_classic.png` versus `02_robust_global.png`. Strokes and AA remain off in that comparison. Six native crops now include the tree-root area, thigh and tail so tonal regressions are visible alongside the line-work crops. The withdrawn V2.11 output is not a product option. Denoising, automatic strength, source tracing, surface cleanup, stroke cleanup and AA are unchanged.

Normal Run's tree shading remains at the accepted V2.10/V2.12 level. Reconstruction candidates are isolated in the new comparison rather than enabled in normal processing. See [regression validation](VALIDATION_V212.md).

## Stroke cleanup

**Compare strokes 0 / 60 / 100** is the first test to use. Set the usual denoiser, cleanup and color method, then choose a parent folder. The comparison runs those upstream stages once, including the selected color correction once. It builds one full stroke-repair candidate, then blends it at 0, 60 and 100 with AA off throughout. There is no automatic strength reduction on this finishing control. The 60 and 100 outputs match normal Run at those settings.

The new `stroke_test_v210_<timestamp>` folder contains `00_strokes_off.png`, `01_strokes_60.png`, `02_strokes_100.png`, full source/reference images, `source_line_core.png`, actual `stroke_support.png`, `stroke_change_100.png`, native crops, a contact sheet and settings/timings. `share_stroke_test.zip` includes these images and JSON within a 30-MiB budget; otherwise individual files remain. No large NPZ is required for this comparison. Reports record candidate and actual changed area, RGB changes and timing, so an active map is not mistaken for an applied repair.

For normal Run, enable **Stroke cleanup**. It starts at strength **100** when enabled, applying the full candidate. Normal processing starts with the checkbox off. The accepted denoiser and source protection still run first; this finishing stage is deliberately allowed to change the previously protected stroke pixels.

The method uses the carried source map to locate possible line regions, then reads RGB cross-sections from the post-color image. A darker stroke has supporting contrast on both sides; a broad smoke/shading step usually has a matching flank. A direction field follows the stroke through bends. Cross-sections are aligned to their estimated centers before sampling up to nine native pixels in each direction. A sample from the darker quarter favors intact colored ink over pale grid cuts, without using a fixed black color. RGB compatibility scales with local stroke contrast to avoid borrowing unrelated ink from a nearby contour. Short dashes reject background samples; continuous profiles can also regularize small edge fluctuations. These are image measurements, not semantic recognition.

**Preview strokes on last result** reapplies stroke cleanup and the current AA setting from cached post-color pixels. It reruns no denoiser, cleanup or color fit, and previews do not accumulate. Actual upstream settings remain in the save report even if other controls were changed. Replacing an input clears the finishing cache. **Preview AA on last result** changes AA alone and retains the last stroke result. To change strokes use Preview strokes or Run; to change denoising/colors use Run.

Strong cleanup can make strokes heavier, affect tiny details or change narrow intersections. The first version repairs existing stroke evidence; it does not fit a complete vector drawing or reconstruct long missing lines. Preserve Edits is unchanged. Compare colors, Compare auto and Legacy manual disable stroke cleanup and AA so their existing tests stay separate.

## Color comparison

V2.9 keeps accepted V2.8 denoising, source tracing and cleanup unchanged. **Classic** remains the default color method. **Robust global** is opt-in and fits a single RGB channel matrix and offset from coarse, low-gradient paired colors. This permits cross-channel correction that independent LAB offsets/gains cannot express. It applies the coefficients directly to native pixels; no reference detail or spatial correction field is copied into the new method's output. A reference grid can still bias color statistics slightly.

The fit uses robust residual weights to reduce the influence of changed objects. Separate held-out tiles compare it against Classic. It falls back to the exact Classic path for insufficient color diversity, collapsing/extreme transforms, poor paired agreement, or no meaningful improvement. The report and status record which method was actually selected and why. These checks are conservative fit heuristics, not a semantic assessment. Differently composed references may fall back even when their palette is useful; Classic remains available for that use. Clipped colors or distinct colors already collapsed together cannot always be recovered by one global transform.

Start with **Compare colors**. It runs the currently configured denoising and cleanup once. Both color methods receive that exact cleaned image and use the same local baseline from before broad correction. Reference correction is on and **stroke cleanup and AA are off** for this comparison, regardless of finishing controls. The new `color_test_v29_<timestamp>` folder contains `00_before_color.png`, `01_classic.png`, `02_robust_global.png`, full inputs, source protection, settings/fit reports, native crops and a contact sheet. The Robust global file can match Classic when fallback is selected. `share_color_test.zip` includes the three full outputs, inputs, protection and JSON when they fit within 30 MiB; otherwise individual files remain. Large raw NPZ maps are not part of this color test.

For normal Run, choose the desired method in **Color method**. The Reference color correction checkbox still controls whether it runs at all. No denoiser strength is changed by the color method. The older Compare auto retains its shared Classic palette field and disables AA; Legacy manual comparison also uses Classic with AA off.

## Optional antialiasing

**Optional edge antialiasing** starts off. When enabled it applies an FXAA-style directional filter after stroke cleanup, at the image's native resolution. Short bilinear samples along the estimated edge direction soften staircase steps. Low-contrast/flat pixels bypass it. Strength starts at 35; 100 is the full filter. It does not trace new curves, reconnect missing strokes, or reconstruct the reference's clean linework. Fine texture or tiny strokes can soften at high strengths.

Run once, then use **Preview AA on last result** to compare strengths quickly without another BM3D, cleanup or color-fit run. It always starts from cached pre-AA pixels, so previews do not accumulate; the last stroke result is retained. Uncheck AA and preview again to recover those exact pixels. Other changed controls require Run / Preview; an AA preview retains the actual original upstream settings in saved reports. Replacing either input clears the cache. AA preview is for Restore Quality; Preserve Edits remains unchanged.

AA has separate signed diagnostics and timings. `denoise + cleanup + palette + stroke + antialias = total` exactly in int16 RGB maps. Source-core RGB protection applies before color/strokes/AA: optional finishing may change those final line pixels intentionally. Preview timing reports separate the quick AA operation from the original full run; the displayed total combines measured upstream timings with the latest AA/diagnostic timings.

## Bright surface adjustment

V2.8 retains V2.7's selected backend settings and source tracing. It adds a local permission floor for fine texture within supported bright, low-chroma surfaces. This addresses gray/blue speckling around white sparkle details that the earlier colored-variation requirement and extra protection fade left behind.

The cue uses source LAB lightness/chroma, broad support for a bright neutral surface and local fine-scale luminance scatter. It does not inspect reference geometry or identify an object. Constant or gently shaded clean surfaces receive no extra permission. Exact source-core pixels remain excluded; the existing filters retain their own barriers. Eligible gaps can receive more of the existing denoiser, local and broad corrections without the extra wide automatic fade around every small point detail.

This rule is applied after backend-strength estimation, so it does not retarget or add a denoiser run. Its `auto_bright_neutral_permission` map is merged into the actual luminance/chroma permission fields used by the stages. The report records active area and mean permission. It can soften intentional fine gray texture on bright neutral objects; it is not semantic recognition of unwanted sparkle halos.

## Automatic strength

The new checkbox controls **Restore Quality**. It starts enabled. Luminance denoise, Color denoise, Surface cleanup, Brightness cleanup and Broad correction start at 100 as maximum permitted strengths. Auto selects denoiser candidate strengths and limits the denoiser handoff and local/broad cleanup spatially. Similarity range and neighborhood radius keep their existing meanings and defaults (12 LAB, 16 pixels).

Start with the usual edited image and color reference, source tracing enabled, and Run / Preview. The status describes candidate denoiser strengths or a skipped backend, plus average luminance/chroma surface permissions. A stronger candidate can still have little effect in a quiet area because its correction is limited by location. These averages are not percentages of noise removed. Turning Auto off restores direct manual control. The API retains manual behavior by default: use `Options(auto_strength=True)` to enable the controller.

The controller measures three kinds of source evidence:

1. Robust high-pass LAB scatter is measured at the native size and analysis scales 2, 4, 8 and 16. Box-average scale compensation gives white-noise-equivalent candidate cues. Coarse samples require sufficient eligible colored-interior support, with protected source edges excluded. These cues set the existing denoiser sliders, capped by requested ceilings. They can include real shading, so they are not estimates of certain noise. BM3D sigma mappings are unchanged; legacy methods have different strength scales.
2. Medium-scale luminance/chroma variation identifies possible correlated contamination. The general luminance rule requires accompanying colored variation, since gray variation alone can be smoke, shading or deliberate texture. V2.8 adds the separate supported bright-neutral fine-texture cue described above.
3. Strong shared directionality in luminance and chroma reduces permission near coherent shading. Luminance directionality alone does not veto grid cleanup. The general rule uses a six-pixel fade beside source protection; eligible bright-neutral fine texture can receive additional permission as described above. Retained surface filters also have their own barriers/fades. Zero-weight pixels keep exact input RGB for that stage, and the original source core remains protected.

Auto now limits the guarded backend correction as well as both retained V2.4 surface candidates, independently in LAB luminance/chroma. Native independent grain can authorize fine denoising of gray areas without authorizing broad brightness flattening. No new smoothing filter is added. If neither native nor eligible coarse scatter justifies the backend minimum, Auto skips it and records why. If only one selected slider is zero, that backend channel still uses its unchanged manual minimum, subject to the spatial limits.

This is conservative source analysis, not a learned or semantic classifier. Gray-only coarse blotches, subtle contamination and some protected texture can remain. Intentional colored texture can still be softened. Auto does not repair missing source strokes or guarantee unchanged contrast after color conversion. Repeated passes need not converge to an artistically correct image.

## Controlled comparison

Choose **Compare auto** and a parent folder. It creates `auto_test_v28_<timestamp>` containing:

- `00_manual_before_palette.png`: requested manual strengths, V2.4 tracing/cleanup, before colors.
- `01_auto_before_palette.png`: automatic strengths and limits, before colors.
- `02_manual_same_palette.png`: manual result with the frozen manual-baseline palette field.
- `03_auto_same_palette.png`: automatic result with that exact field.

Judge 02 versus 03; inspect 00 versus 01 if a color difference obscures the cleanup. The source tracer and its settings are identical in both. The accepted V2.4 tracer is the default (`faint_continuity=False`); V2.5's optional faint continuation is retained in the legacy Python comparison and is not part of the new test.

Different selected strengths require separate backend runs. Auto may skip its fine stage. The comparison reports per-run processing and paired palette timing; exports are outside those timers. Normal Run fits the existing palette matcher to its own local-cleanup result. Compare auto freezes the field fitted to the manual local-cleanup baseline, so its automatic final image can differ from a normal Run preview. With reference correction off, neither variant receives a palette transform.

The folder includes `edited_source.png`, `color_reference.png`, common `source_protection.png`, raw denoiser images, `auto_controlled_denoiser.png`, settings/timings, stage maps, native crops and a contact sheet. The controlled denoiser view includes guards and automatic spatial limits, before surface cleanup. Protection checks count changed common source-core pixels before and after the shared palette. Those checks establish exact core retention, not unchanged contrast around every stroke.

**share_auto_test.zip** excludes large NPZ files and extra previews. Four full-resolution outputs, source, protection and settings are required. The color reference is added first if it fits, followed by automatic raw/controlled denoiser views, strength maps and the manual raw denoiser view, within a 30-MiB budget. The JSON lists omitted optional files. If required images exceed the budget, individual files remain and no ZIP is produced. Source files are included so a subsequent test can use the actual input.

The **Legacy manual comparison** button under Advanced / legacy retains the earlier V2 comparison with automatic strength and broad correction disabled. Historical line/blotch comparison modules also force manual strengths to avoid mislabeling a reused backend candidate.

## Diagnostics

Save maps and Compare export exact arrays in `diagnostics_raw.npz` and pictures with a legend. Comparison prefixes are `manual_` and `auto_`.

- `auto_luminance_strength`, `auto_chroma_strength`: actual 0–1 fields applied to both surface candidates. `auto_denoise_luminance_strength` and `auto_denoise_chroma_strength` control the guarded backend handoff. These are permission weights, not noise probabilities.
- `auto_bright_neutral_permission`: additional source-derived permission for fine mottling within supported bright neutral surfaces; it does not change candidate settings or source cores.
- `auto_color_variation`: medium chroma variation divided by 2 for display. `auto_luminance_coherence`: directional coherence, 0–1.
- `source_line_core`: binary original-pixel protection passed to both cleanup stages. White pixels keep source RGB before final color correction. Reference geometry does not supply this map.
- `unprotected_denoise_signed_rgb`: raw backend minus original; `guard_signed_rgb`: guards/source copy-back minus raw backend; `auto_denoise_limit_signed_rgb`: spatially limited handoff minus guarded handoff. All three sum to `denoise_signed_rgb`. Manual runs omit the third term. When Auto skips the backend, raw denoising change is zero.
- `local_cleanup_signed_rgb`, `blotch_signed_rgb`: actual local/broad corrections after automatic limits. Their sum is `cleanup_signed_rgb`.
- `denoise_signed_rgb`, `cleanup_signed_rgb`, `palette_signed_rgb`, `stroke_signed_rgb`, `antialias_signed_rgb`: actual stages whose sum equals `total_signed_rgb`. Native signed values are int16 RGB, after minus before. AA is zero when off.
- `*_change`: mean absolute RGB change divided by 16, with the same fixed display scale for every stage. The legacy `difference` alias is total change divided by 70. Neither is a detected-noise map.
- `blotch_automatic_amount`: V2.4's candidate confidence before the additional automatic limits; consult `blotch_change` for applied correction. `v2_boundaries` and `blotch_boundaries` show actual cleanup exclusions.

Heatmap colors encode numbers, not the original hue or kind of noise. Signed previews show separate RGB channels, blue for negative, gray for zero and orange for positive, saturating at +/-16 levels; they can be resized. NPZ retains exact values. Raw map exports can use substantial disk space at 2K/4K.

## Retained processing

All structural analysis uses the edited image. Supported weak source edges link to strong seeds or survive as long coherent segments; a small support band retains stroke centers. BM3D/NLM do not accept these masks internally. Legacy blending and exact source-core copy-back happen at their handoff. V2 cleanup uses the same core inside its sampling barriers.

Local cleanup samples similar LAB neighbors at fine/medium/broad distances on the full-resolution grid. A straight sampling path must avoid blocked boundary links. Broad normalization partitions unprotected interiors, detrends regional samples, smooths local residuals, and fades correction beside boundaries. Its candidate steps remain capped at 3 LAB units and within the observed 49×49 RGB envelope. Auto limits those candidates and the backend handoff; cleanup algorithms and BM3D adapters are unchanged. Only analysis uses smaller grids; restoration pixels stay at the original resolution.

Reference correction follows cleanup and precedes optional stroke cleanup and AA. Classic uses the inherited LAB engine; Robust global is described above. Color correction can recolor protected line pixels and compress faint contrast. Preserve Edits remains the existing registered pixel-replacement workflow; it requires matching input dimensions and ignores the restoration controller and new finishing options. Restore Quality allows differently sized references.

## Installation, themes and input

Extract outside Forge. Use 64-bit Python with Tkinter; Python 3.11/3.12 are recommended for optional BM3D dependencies. Start **START_Stable_Shift.bat**. Base requirements include `tkinterdnd2==0.7.0`, with native Tcl/Tk 9 support. The launcher upgrades an older installation. Internet is needed for initial dependencies; normal launches with dependencies present do not run pip.

Each extracted folder has its own `.venv`. Install optional CPU/GPU BM3D there using the app buttons. Updating an existing folder can reuse its installed environment; do not copy virtual environments between machines. CPU BM3D uses `bm3d==4.0.3`; GPU uses `bm3d-cupy[cuda12]==0.1.3`.

Drop one image onto either input panel or its Open button. Spaces, braces and Unicode paths are parsed as a Tcl file list. Multiple files are rejected. Inputs cannot change during processing; replacing one clears stale output. File dialogs remember each input's last directory. If native drag/drop fails, Open remains available and startup.log records the error. Launch normally for Windows Explorer drag/drop.

System/Dark/Light themes remain. Windows System follows AppsUseLightTheme; other systems default to dark if detection is unavailable. Native dialogs use the OS theme.

## Timings and hardware

Live elapsed and completed stage timings remain. Save PNG writes the actual run settings, effective automatic choices and timings alongside the image, even if controls changed afterward. Timers exclude input loading, rendering and export. Native/coarse estimation is included in source-analysis time; spatial backend limiting is included in denoising time. First GPU execution can include CUDA setup/compilation. Local/broad cleanup runs on CPU NumPy/OpenCV.

GPU BM3D errors are explicit; no CPU fallback runs. Auto can legitimately skip GPU work when neither native nor eligible coarse scatter justifies the minimum, which is recorded separately. A CuPy CUDA-path warning alone is not a traceback or proof of an incomplete install. If a GPU stage finishes it executed and synchronized GPU operations. This Linux development environment has no GPU to validate that path.

Optional backend license references: [CPU BM3D](https://pypi.org/project/bm3d/) (published noncommercial package terms), [bm3d-cupy](https://pypi.org/project/bm3d-cupy/) and its [source](https://github.com/kvttt/bm3d_cupy).

## Developer checks

Install base requirements, CPU BM3D and pytest, then run `python -m pytest -q`. Native Tk integration tests need a display on Linux. See [VALIDATION.md](VALIDATION.md) for actual checks and the smoke diagnosis. Dependencies and virtual environments are not committed.

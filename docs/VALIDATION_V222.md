# V2.22 — reference lighting on the active SCUNet path

V2.21 borrowed a reconstruction-comparison color helper that replaced a failed
paired fit with Off. A different composition could therefore prevent an
enabled reference from darkening or recoloring SCUNet's output.

The SCUNet path now prefers the existing robust paired RGB fit, then falls
back to **Global palette**. Independent RGB distributions are resized to at
most 384 pixels, winsorized at the 2nd/98th percentiles, and summarized by mean
and channel spread. Positive diagonal gains (bounded 0.05–4) and pivots define
one uniform RGB transform. Nearly constant source channels receive the reference
offset without division by an unobserved spread. The transform stays frozen
across all cleanup strengths. Reference geometry and spatial artifacts cannot
be copied into the output. The result bar identifies the effective method.

The accepted SCUNet inference, blotch filter and cached blending are unchanged.
A sparkle-halo prototype was excluded after it also changed faint shading on
the accepted cabin image. No new halo pass or tuning control is included.

Validation is focused on this change: **six automated checks**, including
recomposed darker warm/cool references, degenerate channels, explicit Off,
reference lighting across cached strengths, common coefficients and one live
UI/save check. Historical BM3D, pyramid, stroke and AA suites were not rerun.

The cabin and beach cached real-model inputs retain pixel-identical accepted
color output. For the alley model output, a controlled flipped reference with
known darker channel gains demonstrates that the old fit rejects the pairing
while Global palette still transfers the intended lighting at 0, 100 and 200%.
The original warm reference is available only inline in the conversation, so
this controlled reference is explicitly synthetic rather than a replay of
that exact pair. Existing real SCUNet results are reused; the model is unchanged
and no repeat inference was needed. Windows/CUDA execution was not available.

Independent statistics provide an overall palette transfer, not semantic
matching of objects. New or differently sized colors may influence the result.

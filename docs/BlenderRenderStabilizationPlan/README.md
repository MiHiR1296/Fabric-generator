# Blender Render Stabilization Plan

This folder is the active working plan for stabilizing the Blender render
pipeline after the `blender-method-deep-learning.html` review. It exists
because older docs disagree with the live `.blend`, and the live Blender
session is the only source of truth for graph state while this work is active.

## Read Order

1. [current_state.md](current_state.md) - live MCP readback and current code truth.
2. [action_plan.md](action_plan.md) - phase-by-phase implementation plan.
3. [decision_log.md](decision_log.md) - methods kept, rejected, removed, or deferred.
4. [verification_matrix.md](verification_matrix.md) - exact tests and readbacks.
5. [phase_log.md](phase_log.md) - append-only implementation history.

## Current Diagnosis

The render problem is not a simple source-resolution problem. The verified
runtime yarn texture is full resolution, the live material uses the expected
UDIM/PBR path, and the current Blender graph has the approved Arc 2 same-yarn
U behavior. The remaining high-value issues are:

- Generated preview materials linked alpha directly into Principled alpha, so
  low-alpha haze could wash out twist and fiber detail.
- Metadata-only live pushes did not pin root `Texture Scale U`, so stale manual
  values could survive a bandmeta update.
- The graph has no `Profile V Steps` control yet, so V-profile density is still
  a manual node edit instead of a quality preset.
- The graph has no `Texture World Width BU` socket yet, so U world width still
  goes through `Image Width Px / Scanner Pixels Per BU`.

## Source-Of-Truth Rule

When docs, code comments, and Blender disagree, trust this order:

1. Live Blender MCP readback from `127.0.0.1:9876`.
2. Current generated Python script in `backend/app/render_jobs.py`.
3. Backend/live sync code in `backend/app/blender_live.py` and
   `backend/app/blender_sync.py`.
4. Historical docs and phase logs.

If a future phase mutates `Codex_ParametricWeave.blend`, capture a readback
before and after the change and append it to [phase_log.md](phase_log.md).

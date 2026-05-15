// @ts-nocheck — faithful port of yarnseamless JSX. TypeScript checking off in this file;
//                 the source is preserved byte-for-byte (Phase 2c, putting-it-together/phase_log.md).
//                 Re-enable per-file as we type things up in Phase 2e or beyond.
import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { inpaintJoin, assembleTileable } from '../../lib/yarnseamless/multiStitch';

/**
 * Unified multi-fragment yarn stitcher (v2).
 *
 * Fragments are placed touching (no spatial gap). Each junction has a yellow
 * semi-transparent "mask zone" overlay straddling the seam — that's the region
 * LaMa will repaint. The user can paint extra mask area with the brush. Each
 * fragment has a global Y offset (used in every join it participates in).
 *
 * "Inpaint All Joins" runs N independent LaMa calls (one per junction) and
 * streams each result back into the canvas as it completes. "Assemble" stitches
 * everything into one tileable image.
 */

function loadImg(url) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res(im);
    im.onerror = rej;
    im.src = url;
  });
}

// Detect the dominant horizontal thread band — rows of an image that contain the main thread.
// Robust against small stray content (watermarks, labels) because it expands outward from the
// row with the most non-bg pixels and only includes rows whose content density stays high.
// Returns { y0, y1 } in image-local pixel coordinates.
function detectThreadBand(image) {
  const off = document.createElement('canvas');
  off.width = image.width;
  off.height = image.height;
  const ctx = off.getContext('2d');
  ctx.drawImage(image, 0, 0);
  const data = ctx.getImageData(0, 0, image.width, image.height).data;
  const w = image.width;
  const h = image.height;
  const rowCounts = new Array(h).fill(0);
  for (let y = 0; y < h; y++) {
    let count = 0;
    for (let x = 0; x < w; x++) {
      const idx = (y * w + x) * 4;
      const r = data[idx], g = data[idx + 1], b = data[idx + 2];
      const gray = (r + g + b) / 3;
      if (gray > 25 && gray < 230) count++;
    }
    rowCounts[y] = count;
  }
  let peakRow = 0, peakCount = 0;
  for (let y = 0; y < h; y++) {
    if (rowCounts[y] > peakCount) { peakCount = rowCounts[y]; peakRow = y; }
  }
  if (peakCount === 0) return { y0: Math.floor(h * 0.4), y1: Math.ceil(h * 0.6) };
  // Expand while content density stays > 60% of peak (rejects frayed-fiber wisps and watermarks)
  const threshold = Math.max(peakCount * 0.60, w * 0.05);
  let y0 = peakRow;
  while (y0 > 0 && rowCounts[y0 - 1] >= threshold) y0--;
  let y1 = peakRow;
  while (y1 < h - 1 && rowCounts[y1 + 1] >= threshold) y1++;
  return { y0, y1: y1 + 1 };
}

const STRIP_WIDTH = 512;          // pixels (full-res) of context taken from each fragment (each side of junction)
const LAMA_CROP_SIZE = 1024;      // square crop (full-res) sent to LaMa
const DEFAULT_MASK_ZONE = 30;     // mask rectangle width in DISPLAY pixels
const DEFAULT_MASK_HEIGHT_PAD = 10; // extra px (full-res) above + below the detected thread band

// Browsers have a hard canvas-dimension limit (Chrome ~32767, Safari often smaller). Stitching
// N huge thread images side-by-side easily blows past this. We pick a base viewScale so the
// "fit" canvas stays within MAX_DISPLAY_W. When the user zooms in, we redraw at a higher
// internal resolution (up to MAX_INTERNAL_W) so zoomed-in content stays crisp. LaMa still
// always receives full-resolution 1024×1024 crops regardless of viewport / zoom.
const MAX_DISPLAY_W = 12288;
const MAX_INTERNAL_W = 16384;

export default function MultiFragmentEditor({
  fragments,
  setFragments,
  onAssembleDone,
  onCancel,
  onCropFragment,
  brushSize, setBrushSize,
}) {
  const N = fragments.length;
  const [maskZoneW, setMaskZoneW] = useState(DEFAULT_MASK_ZONE);
  // Absolute mask height in unified pixels. null = auto (thread band + small padding).
  const [maskHeightOverride, setMaskHeightOverride] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [busyMessage, setBusyMessage] = useState('');
  const [tool, setTool] = useState('drag'); // 'drag' | 'paint'
  const [joinResults, setJoinResults] = useState({}); // { [joinIdx]: { dataUrl, img } }
  // Per-join "use inpainted vs skip the inpaint" toggle. Default: 'inpaint'.
  // 'skip' means use the natural overlap of the two strips (no LaMa output).
  const [joinUsage, setJoinUsage] = useState({}); // { [joinIdx]: 'inpaint' | 'skip' }
  // Highlight which box (join) the user is hovering / inspecting.
  const [highlightJoin, setHighlightJoin] = useState(null); // null | number
  const [debugSessionId, setDebugSessionId] = useState(null);
  const [debugDir, setDebugDir] = useState(null);

  // Post-assemble "result" view state
  const [view, setView] = useState('edit'); // 'edit' | 'result'
  const [assembledDataUrl, setAssembledDataUrl] = useState(null);
  const [assembledAlphaDataUrl, setAssembledAlphaDataUrl] = useState(null);
  const [assembledRgbaDataUrl, setAssembledRgbaDataUrl] = useState(null);
  const [assembledDarkBlueDataUrl, setAssembledDarkBlueDataUrl] = useState(null);
  // Pre-fetched metadata URL — populated automatically after assemble so the
  // "Download Metadata" button is one click (no server round-trip).
  const [metadataUrl, setMetadataUrl] = useState(null);
  // X-coordinates (in assembled image space) of each join's centerline. Used
  // by the result view's "show join lines" toggle to overlay green vertical
  // lines so the user can see where the inpainted seams are.
  const [joinXCenters, setJoinXCenters] = useState(null);
  // [{ joinIdx, segments: [{startX, endX}], usage, isWraparound }] — start/end
  // of each join's mask box in EXPORT coords. Wraparound has two segments
  // because the box spans the tile boundary. Computed in `getJoinBoxesExport`.
  const [joinBoxes, setJoinBoxes] = useState([]);
  const [showTile, setShowTile] = useState(false);
  const [showAlphaOverlay, setShowAlphaOverlay] = useState(false);
  const [showJoinLines, setShowJoinLines] = useState(false);
  const [showSolidBand, setShowSolidBand] = useState(false);
  const [showWidths, setShowWidths] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [regeneratingAlpha, setRegeneratingAlpha] = useState(false);
  const [savingToLibrary, setSavingToLibrary] = useState(false);
  const [libraryStatus, setLibraryStatus] = useState(null);  // { yarnId, libraryPath } | { error }

  // Helper: per-join usage as an array (always length N), default 'inpaint'.
  function getJoinUsageArray() {
    return Array.from({ length: N }, (_, i) => joinUsage[i] || 'inpaint');
  }

  const fileInputSingleRef = useRef(null);
  const fileInputBulkRef = useRef(null);
  const dragReorderIdxRef = useRef(null);

  const canvasRef = useRef(null);
  const canvasScrollRef = useRef(null); // wrapping div with overflow-auto
  const paintOffscreenRef = useRef(null); // user-painted extra mask in unified coords
  const fragImgsRef = useRef([]);
  const contentRowsRef = useRef([]); // per-fragment { y0, y1 } in image-local coords

  const dragStateRef = useRef(null);

  // Zoom: 1 = fit-to-height (520px tall display). Higher = zoom in.
  const [zoom, setZoom] = useState(1);
  const ZOOM_MIN = 1, ZOOM_MAX = 16, ZOOM_STEP = 1.25, FIT_DISPLAY_H = 520;

  // Stable structural key — only changes when fragments are added/removed/reordered
  // or their data/dimensions change, NOT when yOffset changes.
  const structuralKey = useMemo(
    () => fragments.map(f => `${f.id}:${f.w}x${f.h}`).join('|'),
    [fragments]
  );

  // ===== File handling =====
  function readFiles(files) {
    return Promise.all(Array.from(files).map(f => new Promise((res) => {
      const r = new FileReader();
      r.onload = () => {
        const im = new Image();
        im.onload = () => res({
          id: `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
          name: f.name,
          dataUrl: r.result,
          w: im.width, h: im.height,
          yOffset: 0,
        });
        im.onerror = () => res(null);
        im.src = r.result;
      };
      r.readAsDataURL(f);
    })));
  }

  async function handleSingleFile(e) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const newFrags = (await readFiles(files)).filter(Boolean);
    setFragments(prev => [...prev, ...newFrags]);
    e.target.value = '';
    setJoinResults({});
  }

  async function handleMultiFiles(e) {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const sorted = Array.from(files).sort((a, b) => a.name.localeCompare(b.name));
    const newFrags = (await readFiles(sorted)).filter(Boolean);
    setFragments(prev => [...prev, ...newFrags]);
    e.target.value = '';
    setJoinResults({});
  }

  function removeFragment(id) {
    setFragments(prev => prev.filter(f => f.id !== id));
    setJoinResults({});
  }

  function moveFragment(fromIdx, toIdx) {
    if (fromIdx === toIdx) return;
    setFragments(prev => {
      const next = prev.slice();
      const [moved] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, moved);
      return next;
    });
    setJoinResults({});
  }

  function setFragYOffset(idx, value) {
    setFragments(prev => prev.map((f, i) => i === idx ? { ...f, yOffset: value } : f));
  }

  // ===== Layout: depends ONLY on structural changes (not yOffset) =====
  // Fragments touch — no gap. Total width = sum of widths + frag0.width (phantom).
  const [layout, setLayout] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      if (fragments.length === 0) {
        fragImgsRef.current = [];
        setLayout(null);
        return;
      }
      const imgs = await Promise.all(fragments.map(f => loadImg(f.dataUrl)));
      if (!alive) return;
      fragImgsRef.current = imgs;

      // Detect thread content rows for each fragment (used for auto mask Y range)
      contentRowsRef.current = imgs.map(im => detectThreadBand(im));

      // Compute logical (full-res) dimensions. Layout coords are stored at BASE display scale
      // (the lowest internal resolution we'd use). Higher zoom redraws use a derived
      // "effectiveScale" that's ≥ baseViewScale, so zoomed-in canvases get crisp detail.
      let logicalW = 0;
      for (let i = 0; i < imgs.length; i++) logicalW += imgs[i].width;
      logicalW += imgs[0].width; // phantom wraparound copy
      const baseViewScale = Math.min(1, MAX_DISPLAY_W / logicalW);
      const maxH = Math.max(...imgs.map(i => i.height));

      // Layout (in BASE display coords) — used for CSS sizing of the canvas
      const fragX = [];
      const junctionX = [];
      const fragW = [];
      let x = 0;
      for (let i = 0; i < imgs.length; i++) {
        fragX.push(x);
        const dw = Math.round(imgs[i].width * baseViewScale);
        fragW.push(dw);
        x += dw;
        junctionX.push(x);
      }
      const wrapX = x;
      const phantomW = Math.round(imgs[0].width * baseViewScale);
      x += phantomW;
      const totalW = x;
      const displayMaxH = Math.round(maxH * baseViewScale);
      const totalH = displayMaxH + 600; // headroom for ±300 (full-res) yOffset

      setLayout({
        fragX, junctionX, fragW, phantomW, wrapX, totalW, totalH,
        viewScale: baseViewScale,         // legacy alias (still used for mouse coord math)
        baseViewScale,
        logicalW, logicalMaxH: maxH,
      });

      // Paint offscreen mirrors the display canvas size (no precision loss vs display)
      const cv = document.createElement('canvas');
      cv.width = totalW;
      cv.height = totalH;
      paintOffscreenRef.current = cv;
    })();
    return () => { alive = false; };
  }, [structuralKey]); // intentionally not depending on yOffsets — those don't change layout

  // Recompute the join-mask boxes in EXPORT image coords whenever the layout
  // or per-join state changes. Each entry has 1-or-2 segments (the wraparound
  // join's mask straddles the tile boundary, so it shows up at both edges).
  useEffect(() => {
    if (!fragments || fragments.length < 2) { setJoinBoxes([]); return; }
    const Nf = fragments.length;
    const sw = STRIP_WIDTH;
    const joinCanvasW = 2 * sw;
    const interiorW = fragments.map(f => Math.max(0, (f.w || 0) - 2 * sw));
    // Wraparound assembled width = export width (invariant of our trim fix).
    let xWalk = 0;
    const joinStartXAssembled = [];
    for (let j = 0; j < Nf; j++) {
      xWalk += interiorW[j];
      joinStartXAssembled.push(xWalk);  // left edge of join j's canvas in WRAPAROUND assembled
      xWalk += joinCanvasW;
    }
    const Ww = xWalk; // assembled width

    const boxes = [];
    for (let j = 0; j < Nf; j++) {
      const isWraparound = (j === Nf - 1);
      const usage = joinUsage[j] || 'inpaint';
      // Mask rect in per-join canvas coords {x, w}. Prefer the rect that was
      // actually inpainted; fall back to the current paint-zone (centered on
      // the seam at canvas col strip_w).
      let rx, rw;
      const stored = joinResults[j]?.atInpaint?.maskRectFull;
      if (stored && typeof stored.x === 'number' && typeof stored.w === 'number') {
        rx = stored.x; rw = stored.w;
      } else {
        const vs = layout?.viewScale || 1;
        const maskZoneW_full = maskZoneW / vs;
        const half = maskZoneW_full / 2;
        rx = Math.max(0, Math.floor(sw - half));
        rw = Math.min(joinCanvasW, Math.ceil(sw + half)) - rx;
      }

      if (!isWraparound) {
        // Non-wraparound: assembled cols [joinStartXAssembled[j]+rx, +rx+rw)
        // shifted +sw in export (because export prepends the wrap-right-half).
        const startX = joinStartXAssembled[j] + rx + sw;
        const endX   = startX + rw;
        boxes.push({ joinIdx: j, usage, isWraparound: false, segments: [{ startX, endX }] });
      } else {
        // Wraparound: canvas cols [0, sw) → export cols [Ww-sw, Ww);
        //             canvas cols [sw, 2*sw) → export cols [0, sw).
        const rxEnd = rx + rw;
        const segments = [];
        if (rx < sw) {
          // Left half of mask (on thread N-1's side → ends at right edge of export)
          const cStart = rx;
          const cEnd   = Math.min(sw, rxEnd);
          segments.push({ startX: Ww - sw + cStart, endX: Ww - sw + cEnd });
        }
        if (rxEnd > sw) {
          // Right half of mask (on thread 0's side → starts at left edge of export)
          const cStart = Math.max(sw, rx);
          const cEnd   = rxEnd;
          segments.push({ startX: cStart - sw, endX: cEnd - sw });
        }
        boxes.push({ joinIdx: j, usage, isWraparound: true, segments });
      }
    }
    setJoinBoxes(boxes);
  }, [fragments, joinResults, joinUsage, maskZoneW, layout?.viewScale]);

  // For a given junction (between frag j and frag (j+1) % N), compute the mask rectangle in
  // unified canvas coordinates: { x, y, w, h }. The rectangle is SYMMETRIC about the thread
  // center (average of the two flanking fragments' thread centers in canvas Y).
  // All values returned here are in DISPLAY pixel coords (the unified canvas's coord system).
  // yOffset is in FULL-RES pixels — multiply by vs when converting to display.
  function computeMaskRectUnified(joinIdx) {
    if (!layout) return null;
    const imgs = fragImgsRef.current;
    if (imgs.length === 0) return null;
    if (imgs.length !== fragments.length) return null;
    const N = imgs.length;
    const vs = layout.viewScale;
    const lf = imgs[joinIdx];
    const rf = imgs[(joinIdx + 1) % N];
    const lc = contentRowsRef.current[joinIdx] || { y0: lf.height * 0.4, y1: lf.height * 0.6 };
    const rc = contentRowsRef.current[(joinIdx + 1) % N] || { y0: rf.height * 0.4, y1: rf.height * 0.6 };
    // Thread center for each fragment in DISPLAY canvas Y coords
    const yoL = (fragments[joinIdx].yOffset || 0) * vs;
    const yoR = (fragments[(joinIdx + 1) % N].yOffset || 0) * vs;
    const lYCenter = (layout.totalH - lf.height * vs) / 2 + yoL + ((lc.y0 + lc.y1) / 2) * vs;
    const rYCenter = (layout.totalH - rf.height * vs) / 2 + yoR + ((rc.y0 + rc.y1) / 2) * vs;
    const centerY = (lYCenter + rYCenter) / 2;
    const detectedH = Math.max(lc.y1 - lc.y0, rc.y1 - rc.y0);
    const autoH_display = (detectedH + DEFAULT_MASK_HEIGHT_PAD) * vs;
    const h = (maskHeightOverride != null ? maskHeightOverride : autoH_display);
    const y = Math.round(centerY - h / 2);
    const jx = layout.junctionX[joinIdx];
    const x = Math.round(jx - maskZoneW / 2);
    return { x, y, w: maskZoneW, h: Math.round(h) };
  }

  // ===== Redraw =====
  const redraw = useCallback(() => {
    const dc = canvasRef.current;
    if (!dc || !layout) return;
    const imgs = fragImgsRef.current;
    if (imgs.length === 0) return;
    // When fragments are added/removed, `fragments` (state) updates synchronously
    // but `fragImgsRef.current` only updates inside the async load effect. Skip
    // this draw pass to avoid `fragments[i]` returning undefined for stale i.
    if (imgs.length !== fragments.length) return;

    // Pick a render scale that grows with zoom so zoom-in stays crisp. Capped at the browser
    // canvas-dimension limit (MAX_INTERNAL_W) and at full source resolution.
    const baseVS = layout.baseViewScale;
    const desiredScale = Math.max(baseVS, baseVS * zoom);
    const cappedScale = Math.min(1, MAX_INTERNAL_W / layout.logicalW, desiredScale);
    const renderScale = cappedScale; // canvas internal pixels per source pixel
    const renderRatio = renderScale / baseVS; // canvas internal × this = base display coords

    const internalW = Math.round(layout.totalW * renderRatio);
    const internalH = Math.round(layout.totalH * renderRatio);
    if (dc.width !== internalW) dc.width = internalW;
    if (dc.height !== internalH) dc.height = internalH;
    const ctx = dc.getContext('2d');
    ctx.fillStyle = 'black';
    ctx.fillRect(0, 0, dc.width, dc.height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    // Draw fragments at their natural size. NO row-padding (no edge-extension).
    // Fill only the actual strip zone [globalTop, globalBot] with sampled
    // bg-red so adjacent strips of different heights blend continuously,
    // but leave the yOffset headroom (extra 300 px above and below) BLACK
    // so the user sees the strip at its natural size with a tight visual frame.
    const fragYs = imgs.map((im, i) => {
      const yoFull = fragments[i].yOffset || 0;
      const dh = Math.round(im.height * renderScale);
      return Math.round((internalH - dh) / 2 + yoFull * renderScale);
    });
    const fragYBots = imgs.map((im, i) =>
      fragYs[i] + Math.round(im.height * renderScale));
    const globalTop = Math.min(...fragYs);
    const globalBot = Math.max(...fragYBots);

    // Sample bg-red from fragment 0's top-left corner (geometrically guaranteed
    // bg). Used to fill ONLY the strip-zone rows, where adjacent strips of
    // different heights would otherwise show black canvas-fill between them.
    let bgFill = 'rgb(140, 50, 50)';   // fallback
    try {
      const probe = document.createElement('canvas');
      probe.width = 4; probe.height = 4;
      const pctx = probe.getContext('2d', { willReadFrequently: true });
      pctx.drawImage(imgs[0], 0, 0, 4, 4, 0, 0, 4, 4);
      const px = pctx.getImageData(0, 0, 4, 4).data;
      let r = 0, g = 0, b = 0;
      for (let p = 0; p < 16; p++) { r += px[p*4]; g += px[p*4+1]; b += px[p*4+2]; }
      bgFill = `rgb(${Math.round(r/16)},${Math.round(g/16)},${Math.round(b/16)})`;
    } catch {}
    ctx.fillStyle = bgFill;
    ctx.fillRect(0, globalTop, internalW, Math.max(0, globalBot - globalTop));

    // Chain x positions: next fragment starts EXACTLY where this one ends.
    // (Independently rounding each `Math.round(layout.fragX[i] * renderRatio)`
    // can produce occasional 1-px gaps at seams — those gaps were the thin red
    // stripes the user noticed between thread 2/3.)
    let xCur = Math.round(layout.fragX[0] * renderRatio);
    for (let i = 0; i < imgs.length; i++) {
      const im = imgs[i];
      const dw = Math.round(layout.fragW[i] * renderRatio);
      const dh = Math.round(im.height * renderScale);
      const y = fragYs[i];
      ctx.drawImage(im, 0, 0, im.width, im.height, xCur, y, dw, dh);
      xCur += dw;
    }

    // Phantom wraparound = fragment 0 at wrapX. Chain x from where the last
    // real fragment ended so the wraparound abuts seam-tight (same fix as
    // above, applied to this drawing too).
    {
      const im = imgs[0];
      const yoFull = fragments[0].yOffset || 0;
      const dw = Math.round(layout.phantomW * renderRatio);
      const dh = Math.round(im.height * renderScale);
      const x = xCur;   // chained from the main fragment loop above
      const y = Math.round((internalH - dh) / 2 + yoFull * renderScale);
      ctx.save();
      ctx.globalAlpha = 0.55;
      ctx.drawImage(im, 0, 0, im.width, im.height, x, y, dw, dh);
      ctx.restore();
      ctx.save();
      ctx.strokeStyle = 'rgba(255, 220, 0, 0.6)';
      ctx.setLineDash([10 * renderRatio, 6 * renderRatio]);
      ctx.lineWidth = 2 * renderRatio;
      ctx.strokeRect(x, y, dw, dh);
      ctx.restore();
    }

    // Auto mask zones — yellow rectangles centered on each junction, sized to thread height
    ctx.save();
    ctx.globalAlpha = 0.40;
    ctx.fillStyle = 'rgba(255, 220, 0, 1)';
    for (let i = 0; i < imgs.length; i++) {
      if (joinResults[i]) continue;
      const r = computeMaskRectUnified(i);
      if (!r) continue;
      ctx.fillRect(r.x * renderRatio, r.y * renderRatio, r.w * renderRatio, r.h * renderRatio);
    }
    ctx.globalAlpha = 0.9;
    ctx.strokeStyle = 'rgba(255, 200, 0, 0.85)';
    ctx.lineWidth = 3 * renderRatio;
    ctx.setLineDash([8 * renderRatio, 4 * renderRatio]);
    for (let i = 0; i < imgs.length; i++) {
      if (joinResults[i]) continue;
      const r = computeMaskRectUnified(i);
      if (!r) continue;
      ctx.strokeRect(r.x * renderRatio, r.y * renderRatio, r.w * renderRatio, r.h * renderRatio);
    }
    ctx.setLineDash([]);
    ctx.restore();

    // User-painted mask overlay (cyan) — paint canvas is at base display resolution
    const pc = paintOffscreenRef.current;
    if (pc) {
      const tmp = document.createElement('canvas');
      tmp.width = dc.width; tmp.height = dc.height;
      const tctx = tmp.getContext('2d');
      tctx.imageSmoothingEnabled = true;
      tctx.drawImage(pc, 0, 0, pc.width, pc.height, 0, 0, dc.width, dc.height);
      tctx.globalCompositeOperation = 'source-in';
      tctx.fillStyle = 'rgba(80, 200, 255, 1)';
      tctx.fillRect(0, 0, dc.width, dc.height);
      ctx.save();
      ctx.globalAlpha = 0.45;
      ctx.drawImage(tmp, 0, 0);
      ctx.restore();
    }

    // Inpainted join results — paste back using the SNAPSHOT taken at inpaint time, not the
    // current mask rect (so live mask H/W changes don't move the inpaint result around).
    for (let i = 0; i < imgs.length; i++) {
      const r = joinResults[i];
      if (!r?.img || !r.atInpaint) continue;
      const baseVS_local = layout.baseViewScale;
      const { maskRectFull, fullH } = r.atInpaint;
      // Source rect = the masked region inside the per-join (full-res) canvas
      const srcX = maskRectFull.x;
      const srcY = maskRectFull.y;
      const srcW = maskRectFull.w;
      const srcH = maskRectFull.h;
      // Dest rect in BASE display coords. The per-join canvas (full-res) is centered
      // vertically inside the unified canvas: per-join Y * vs + (totalH − fullH * vs)/2 = display Y
      const yShiftDisplay = (layout.totalH - fullH * baseVS_local) / 2;
      const destX_disp = layout.junctionX[i] - (srcW * baseVS_local) / 2;
      const destY_disp = srcY * baseVS_local + yShiftDisplay;
      const destW_disp = srcW * baseVS_local;
      const destH_disp = srcH * baseVS_local;
      const usage = joinUsage[i] || 'inpaint';
      // Only paste the inpaint when the user wants it. When skipping, the
      // canvas already shows the natural overlap of the two adjacent strips
      // (which was drawn earlier in this same effect). The label / outline
      // below still draw so the user can see which box is which.
      if (usage !== 'skip') {
        ctx.drawImage(r.img, srcX, srcY, srcW, srcH,
          destX_disp * renderRatio, destY_disp * renderRatio,
          destW_disp * renderRatio, destH_disp * renderRatio);
      }

      // Box number label + status above the inpainted region. Highlights
      // brighter when the user is hovering its toggle button.
      const isSkip = usage === 'skip';
      const isHover = highlightJoin === i;
      const boxX = (destX_disp + destW_disp / 2) * renderRatio;
      const boxY = (destY_disp - 14) * renderRatio;
      const rad = (isHover ? 18 : 14) * renderRatio;
      ctx.save();
      // box outline (yellow if skipped, green if inpainted)
      ctx.strokeStyle = isSkip ? 'rgba(234, 179, 8, 1)' : 'rgba(16, 185, 129, 1)';
      ctx.lineWidth = (isHover ? 4 : 2) * renderRatio;
      ctx.setLineDash(isSkip ? [8 * renderRatio, 6 * renderRatio] : []);
      ctx.strokeRect(
        destX_disp * renderRatio, destY_disp * renderRatio,
        destW_disp * renderRatio, destH_disp * renderRatio,
      );
      ctx.setLineDash([]);
      // label badge
      ctx.fillStyle = isSkip ? 'rgba(234, 179, 8, 0.95)' : 'rgba(16, 185, 129, 0.95)';
      ctx.beginPath(); ctx.arc(boxX, boxY, rad, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = 'white';
      ctx.font = `bold ${Math.round((isHover ? 18 : 16) * renderRatio)}px sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(`${i + 1}`, boxX, boxY);
      ctx.restore();
    }

    // Fragment number badges (top-left of each frag)
    for (let i = 0; i < imgs.length; i++) {
      const x = (layout.fragX[i] + 30) * renderRatio;
      const cy = 30 * renderRatio;
      const r = 22 * renderRatio;
      ctx.save();
      ctx.fillStyle = 'rgba(33, 99, 235, 0.92)';
      ctx.beginPath(); ctx.arc(x, cy, r, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = 'white';
      ctx.font = `bold ${Math.round(28 * renderRatio)}px sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(String(i + 1), x, cy);
      ctx.restore();
    }
    {
      const x = (layout.wrapX + 30) * renderRatio;
      const cy = 30 * renderRatio;
      const r = 22 * renderRatio;
      ctx.save();
      ctx.fillStyle = 'rgba(120, 120, 120, 0.85)';
      ctx.beginPath(); ctx.arc(x, cy, r, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = 'white';
      ctx.font = `bold ${Math.round(18 * renderRatio)}px sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText('1↺', x, cy);
      ctx.restore();
    }

    // Width markers — blue dashed verticals at 5 X-positions per fragment,
    // labelled with mm + px. Coords come from the multithread session's
    // width_samples (measured strictly within the c_band).
    if (showWidths) {
      const baseVS = layout.baseViewScale;
      ctx.save();
      const fontPx = Math.max(10, Math.round(14 * renderRatio));
      ctx.font = `bold ${fontPx}px ui-sans-serif, system-ui, sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
      for (let i = 0; i < imgs.length; i++) {
        const f = fragments[i];
        const samples = f?.mtiWidthSamples;
        if (!Array.isArray(samples) || samples.length === 0) continue;
        const im = imgs[i];
        const dh = Math.round(im.height * renderScale);
        const yo = (f.yOffset || 0) * renderScale;
        const fragYTop = Math.round((internalH - dh) / 2 + yo);
        const lineW = Math.max(2, Math.round(3 * renderRatio));
        const dashLen = Math.max(4, Math.round(8 * renderRatio));
        for (const s of samples) {
          const x = Math.round((layout.fragX[i] + s.x * baseVS) * renderRatio);
          const y0 = fragYTop + Math.round(s.top_y * renderScale);
          const y1 = fragYTop + Math.round(s.bottom_y * renderScale);
          ctx.fillStyle = 'rgba(59, 130, 246, 1)';   // blue-500
          for (let yy = y0; yy <= y1; yy += dashLen * 2) {
            const segH = Math.min(dashLen, y1 - yy + 1);
            if (segH <= 0) break;
            ctx.fillRect(x - Math.floor(lineW / 2), yy, lineW, segH);
          }
          const label = `${s.width_mm.toFixed(2)} mm · ${s.width_px} px`;
          const padX = Math.round(fontPx * 0.3);
          const padY = Math.round(fontPx * 0.18);
          const tw = ctx.measureText(label).width;
          let labelY = y0 - Math.round(fontPx * 0.4);
          if (labelY - fontPx < 0) labelY = y1 + fontPx + Math.round(fontPx * 0.4);
          ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
          ctx.fillRect(x - tw / 2 - padX, labelY - fontPx - padY,
                       tw + padX * 2, fontPx + padY * 2);
          ctx.fillStyle = 'rgba(147, 197, 253, 1)';   // blue-300
          ctx.fillText(label, x, labelY);
        }
      }
      ctx.restore();
    }
  }, [fragments, layout, maskZoneW, maskHeightOverride, joinResults, joinUsage, highlightJoin, zoom, showWidths]);

  useEffect(() => { redraw(); }, [redraw]);

  // ===== Mouse handling =====
  // Returns coords in BASE display space (= layout.totalW × layout.totalH coord system).
  // The internal canvas may be larger when zoomed in (for crispness); we divide by
  // renderRatio so callers (paint, fragmentAtX, drag) keep working in the stable base space.
  function getUnifiedPos(e) {
    const dc = canvasRef.current;
    if (!dc) return null;
    const r = dc.getBoundingClientRect();
    if (!layout) return null;
    const baseVS = layout.baseViewScale;
    const desiredScale = Math.max(baseVS, baseVS * zoom);
    const cappedScale = Math.min(1, MAX_INTERNAL_W / layout.logicalW, desiredScale);
    const renderRatio = cappedScale / baseVS;
    const xInternal = (e.clientX - r.left) * (dc.width / r.width);
    const yInternal = (e.clientY - r.top) * (dc.height / r.height);
    return {
      x: xInternal / renderRatio,
      y: yInternal / renderRatio,
      clientY: e.clientY,
    };
  }

  function fragmentAtX(x) {
    if (!layout) return -1;
    const imgs = fragImgsRef.current;
    for (let i = 0; i < imgs.length; i++) {
      const x0 = layout.fragX[i];
      const x1 = x0 + layout.fragW[i];
      if (x >= x0 && x < x1) return i;
    }
    if (x >= layout.wrapX && x < layout.wrapX + layout.phantomW) return 0;
    return -1;
  }

  const lastPaintRef = useRef(null);
  function paintStrokeAt(x, y, erase = false) {
    const pc = paintOffscreenRef.current;
    if (!pc) return;
    const ctx = pc.getContext('2d');
    if (erase) {
      ctx.globalCompositeOperation = 'destination-out';
      ctx.strokeStyle = 'rgba(0,0,0,1)'; ctx.fillStyle = 'rgba(0,0,0,1)';
    } else {
      ctx.globalCompositeOperation = 'source-over';
      ctx.strokeStyle = 'white'; ctx.fillStyle = 'white';
    }
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.lineWidth = brushSize;
    const last = lastPaintRef.current;
    if (last) {
      ctx.beginPath();
      ctx.moveTo(last.x, last.y);
      ctx.lineTo(x, y);
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(x, y, brushSize / 2, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = 'source-over';
    lastPaintRef.current = { x, y };
  }

  function handleMouseDown(e) {
    e.preventDefault();
    const p = getUnifiedPos(e);
    if (!p) return;
    if (tool === 'drag') {
      const fIdx = fragmentAtX(p.x);
      if (fIdx >= 0) {
        dragStateRef.current = { fragIdx: fIdx, startClientY: p.clientY, startYOffset: fragments[fIdx].yOffset || 0 };
      }
    } else if (tool === 'paint') {
      lastPaintRef.current = null;
      paintStrokeAt(p.x, p.y, e.shiftKey);
      redraw();
    }
  }
  function handleMouseMove(e) {
    const p = getUnifiedPos(e);
    if (!p) return;
    if (tool === 'drag' && dragStateRef.current) {
      e.preventDefault();
      const ds = dragStateRef.current;
      const dc = canvasRef.current;
      const r = dc.getBoundingClientRect();
      const yScale = dc.height / r.height;
      // Mouse delta is in CSS px → display canvas px (×yScale) → full-res yOffset (÷viewScale)
      const dyDisplay = (p.clientY - ds.startClientY) * yScale;
      const vs = layout?.viewScale || 1;
      const dyFull = dyDisplay / vs;
      const newOffset = Math.round(ds.startYOffset + dyFull);
      // Clamp to ±max(300, h/2) full-res — generous so the user can drag the thread anywhere
      const fragH = fragImgsRef.current[ds.fragIdx]?.height || 600;
      const clampLimit = Math.max(300, Math.floor(fragH / 2));
      const clamped = Math.max(-clampLimit, Math.min(clampLimit, newOffset));
      setFragYOffset(ds.fragIdx, clamped);
    } else if (tool === 'paint' && (e.buttons & 1)) {
      e.preventDefault();
      paintStrokeAt(p.x, p.y, e.shiftKey);
      redraw();
    }
  }
  function handleMouseUp() {
    dragStateRef.current = null;
    lastPaintRef.current = null;
  }

  // ===== Zoom handling =====
  // Hold Cmd/Ctrl and scroll, or use the toolbar buttons. Keeps the point under the cursor
  // anchored at the same screen position while zooming.
  function setZoomAt(targetZoom, clientX, clientY) {
    const z = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, targetZoom));
    const container = canvasScrollRef.current;
    if (!container) { setZoom(z); return; }
    const rect = container.getBoundingClientRect();
    // If a cursor was passed, anchor on it; otherwise anchor on the container center
    const anchorX = clientX != null ? clientX - rect.left : rect.width / 2;
    const anchorY = clientY != null ? clientY - rect.top : rect.height / 2;
    // Where the anchor sits in canvas-local (pre-zoom) coords
    const cx = (container.scrollLeft + anchorX) / zoom;
    const cy = (container.scrollTop + anchorY) / zoom;
    setZoom(z);
    requestAnimationFrame(() => {
      container.scrollLeft = cx * z - anchorX;
      container.scrollTop = cy * z - anchorY;
    });
  }

  function zoomFit() { setZoom(1); }

  // Attach a non-passive wheel listener so e.preventDefault() works
  // (React's onWheel is passive by default in modern setups).
  useEffect(() => {
    const el = canvasScrollRef.current;
    if (!el) return;
    function onWheel(e) {
      if (!(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      setZoomAt(zoom * factor, e.clientX, e.clientY);
    }
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [zoom, layout]);

  function clearPaint() {
    const pc = paintOffscreenRef.current;
    if (pc) pc.getContext('2d').clearRect(0, 0, pc.width, pc.height);
    redraw();
  }

  // ===== Build per-join LaMa input =====
  // Two canvases are produced:
  //   1. Full per-join canvas (STRIP_WIDTH*2 wide × max(fragH) tall) — strips drawn at their
  //      yOffsets. Used by assembleTileable to interleave with fragment interiors.
  //   2. LaMa input crop (LAMA_CROP_SIZE × LAMA_CROP_SIZE) cut out of the full canvas, centered
  //      on the mask rectangle. This is what we send to LaMa — a square crop ≈ matching
  //      LaMa's training distribution (no extreme aspect ratios, no mostly-empty space).
  // After LaMa returns, the result is pasted back into the full canvas (see runInpaintAll).
  function buildJoinCanvasAndMask(joinIdx) {
    const imgs = fragImgsRef.current;
    const N = imgs.length;
    if (imgs.length !== fragments.length) {
      throw new Error('Fragment list updating — try again in a moment');
    }
    const vs = layout ? layout.viewScale : 1;
    const leftFrag = imgs[joinIdx];
    const rightFrag = imgs[(joinIdx + 1) % N];
    // yOffset is stored in FULL-RES pixels — use directly.
    const leftYOffset = fragments[joinIdx].yOffset || 0;
    const rightYOffset = fragments[(joinIdx + 1) % N].yOffset || 0;
    const sL = Math.min(STRIP_WIDTH, leftFrag.width);
    const sR = Math.min(STRIP_WIDTH, rightFrag.width);
    const fullW = sL + sR;
    const fullH = Math.max(leftFrag.height, rightFrag.height);
    const junctionX = sL;

    // ---- Full per-join canvas (full-res) ----
    // CRITICAL: do NOT fill with black. The black canvas-fill above/below
    // the shorter strip becomes part of the LaMa input crop, and LaMa then
    // generates dark/black-tinged content extending into the inpainted area
    // — which makes both the alpha and the composite look bad. Instead,
    // edge-extend each strip's top and bottom row vertically so LaMa sees
    // continuous bg (the strip's edge rows are naturally bg-red since the
    // thread is in the middle).
    const fullCv = document.createElement('canvas');
    fullCv.width = fullW; fullCv.height = fullH;
    const fctx = fullCv.getContext('2d');
    fctx.imageSmoothingEnabled = true;
    const leftY = Math.round((fullH - leftFrag.height) / 2 + leftYOffset);
    const rightY = Math.round((fullH - rightFrag.height) / 2 + rightYOffset);
    const leftSx = leftFrag.width - sL;
    // Left half: top edge row stretched up + bottom edge row stretched down
    if (leftY > 0) {
      fctx.drawImage(leftFrag, leftSx, 0, sL, 1,  0, 0, sL, leftY);
    }
    if (leftY + leftFrag.height < fullH) {
      fctx.drawImage(leftFrag, leftSx, leftFrag.height - 1, sL, 1,
                     0, leftY + leftFrag.height, sL, fullH - (leftY + leftFrag.height));
    }
    fctx.drawImage(leftFrag, leftSx, 0, sL, leftFrag.height, 0, leftY, sL, leftFrag.height);
    // Right half: same pattern
    if (rightY > 0) {
      fctx.drawImage(rightFrag, 0, 0, sR, 1,  sL, 0, sR, rightY);
    }
    if (rightY + rightFrag.height < fullH) {
      fctx.drawImage(rightFrag, 0, rightFrag.height - 1, sR, 1,
                     sL, rightY + rightFrag.height, sR, fullH - (rightY + rightFrag.height));
    }
    fctx.drawImage(rightFrag, 0, 0, sR, rightFrag.height, sL, rightY, sR, rightFrag.height);

    // ---- Full per-join mask (full-res) ----
    const fullMask = document.createElement('canvas');
    fullMask.width = fullW; fullMask.height = fullH;
    const mctx = fullMask.getContext('2d');
    mctx.fillStyle = 'black';
    mctx.fillRect(0, 0, fullW, fullH);
    mctx.fillStyle = 'white';
    // Convert mask dimensions from DISPLAY to full-res (the canvas we draw into is full-res)
    const maskZoneW_full = maskZoneW / vs;
    const halfMask = maskZoneW_full / 2;
    const maskLeft = Math.max(0, Math.floor(junctionX - halfMask));
    const maskRight = Math.min(fullW, Math.ceil(junctionX + halfMask));
    const lc = contentRowsRef.current[joinIdx] || { y0: leftFrag.height * 0.4, y1: leftFrag.height * 0.6 };
    const rc = contentRowsRef.current[(joinIdx + 1) % N] || { y0: rightFrag.height * 0.4, y1: rightFrag.height * 0.6 };
    const lYCenter = leftY + (lc.y0 + lc.y1) / 2;
    const rYCenter = rightY + (rc.y0 + rc.y1) / 2;
    const centerY = (lYCenter + rYCenter) / 2;
    const detectedH = Math.max(lc.y1 - lc.y0, rc.y1 - rc.y0);
    const autoH_full = detectedH + DEFAULT_MASK_HEIGHT_PAD;
    const mh_full = (maskHeightOverride != null ? maskHeightOverride / vs : autoH_full);
    const my = Math.max(0, Math.round(centerY - mh_full / 2));
    mctx.fillRect(maskLeft, my, maskRight - maskLeft, Math.min(Math.round(mh_full), fullH - my));

    // User-painted mask: paint canvas is at DISPLAY resolution. Copy the strip column from
    // the paint canvas, scale up by 1/vs into the full-res mask, with vertical alignment so
    // the unified canvas's center row maps to the per-join canvas's center row.
    const pc = paintOffscreenRef.current;
    if (pc && layout) {
      const isWrap = (joinIdx === N - 1);
      const sL_disp = Math.round(sL * vs);
      const sR_disp = Math.round(sR * vs);
      const leftSrcX_disp = layout.fragX[joinIdx] + layout.fragW[joinIdx] - sL_disp;
      const rightSrcX_disp = isWrap ? layout.wrapX : layout.fragX[joinIdx + 1];
      // Dest rect in mask covers the entire pc height scaled to full-res; the unified-canvas
      // padding ends up clipped because dy is negative when totalH/vs > fullH.
      const destH = layout.totalH / vs;
      const destDY = Math.round((fullH - destH) / 2);
      mctx.drawImage(pc, leftSrcX_disp, 0, sL_disp, layout.totalH,  0,  destDY, sL, destH);
      mctx.drawImage(pc, rightSrcX_disp, 0, sR_disp, layout.totalH, sL, destDY, sR, destH);
    }

    // ---- Cut out the 1024×1024 LaMa input crop centered on the mask ----
    const cropSize = LAMA_CROP_SIZE;
    const cropX = Math.round(junctionX - cropSize / 2);
    const cropY = Math.round(centerY - cropSize / 2);

    function cropTo1024(srcCanvas) {
      const out = document.createElement('canvas');
      out.width = cropSize; out.height = cropSize;
      const octx = out.getContext('2d');
      octx.imageSmoothingEnabled = true;
      // In-bounds source rectangle
      const sx = Math.max(0, cropX);
      const sy = Math.max(0, cropY);
      const sxEnd = Math.min(fullW, cropX + cropSize);
      const syEnd = Math.min(fullH, cropY + cropSize);
      const sw = sxEnd - sx;
      const sh = syEnd - sy;
      if (sw > 0 && sh > 0) {
        // Edge-extend rows that fall above the source canvas (cropY < 0).
        // Use the source's TOP row at the same columns. Mirrors the
        // edge-extension done for fullCv: prevents black bands from leaking
        // into the LaMa input.
        if (cropY < 0) {
          octx.drawImage(srcCanvas, sx, 0, sw, 1,  sx - cropX, 0, sw, -cropY);
        }
        // Edge-extend rows below the source canvas.
        if (cropY + cropSize > fullH) {
          const overflow = (cropY + cropSize) - fullH;
          octx.drawImage(srcCanvas, sx, fullH - 1, sw, 1,
                         sx - cropX, fullH - cropY, sw, overflow);
        }
        // The actual in-bounds content
        octx.drawImage(srcCanvas, sx, sy, sw, sh, sx - cropX, sy - cropY, sw, sh);
      }
      return out;
    }
    const cropCv = cropTo1024(fullCv);
    const cropMask = cropTo1024(fullMask);

    return {
      // What we send to LaMa (1024×1024 square)
      canvasDataUrl: cropCv.toDataURL('image/png'),
      maskDataUrl: cropMask.toDataURL('image/png'),
      canvasW: cropSize,
      canvasH: cropSize,
      // Full per-join canvas (used to paste the inpainted crop back)
      fullCanvasDataUrl: fullCv.toDataURL('image/png'),
      fullW, fullH,
      cropX, cropY,
      // Mask rect in full-canvas coords (for debugging / paste-back hints)
      maskRectFull: { x: maskLeft, y: my, w: maskRight - maskLeft, h: Math.min(Math.round(mh_full), fullH - my) },
    };
  }

  // Helper: POST a debug bundle for one join
  async function saveDebugBundle(sid, files, metadata) {
    try {
      const r = await fetch('/api/multifragment/save-debug', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid, files, metadata }),
      });
      const data = await r.json();
      if (data.dir) setDebugDir(data.dir);
    } catch (e) { console.warn('[multifrag-debug] save failed:', e.message); }
  }

  function openDebugFolder() {
    if (!debugSessionId) return;
    fetch('/api/multifragment/open-debug', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: debugSessionId }),
    }).catch(() => {});
  }

  // ===== Inpaint all joins sequentially =====
  async function runInpaintAll() {
    if (N < 2) { setError('Need at least 2 fragments'); return; }
    setBusy(true);
    setError(null);

    // Generate a debug session id (timestamp + small random suffix)
    const now = new Date();
    const ts = `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}_${String(now.getHours()).padStart(2,'0')}${String(now.getMinutes()).padStart(2,'0')}${String(now.getSeconds()).padStart(2,'0')}`;
    const sid = `${ts}_${Math.random().toString(36).slice(2, 6)}`;
    setDebugSessionId(sid);
    setDebugDir(null);

    // Save originals + metadata once at the start
    const origFiles = {};
    fragments.forEach((f, i) => { origFiles[`fragment_${i}_original.png`] = f.dataUrl; });
    await saveDebugBundle(sid, origFiles, {
      timestamp: now.toISOString(),
      fragments: fragments.map((f, i) => ({ index: i, name: f.name, w: f.w, h: f.h, yOffset: f.yOffset || 0 })),
      maskZoneW, stripWidth: STRIP_WIDTH, lamaCropSize: LAMA_CROP_SIZE,
      n_joins: N,
    });

    const newResults = {};
    try {
      for (let i = 0; i < N; i++) {
        setBusyMessage(`Inpainting join ${i + 1} / ${N}...`);
        const built = buildJoinCanvasAndMask(i);
        // Save what was actually sent to LaMa (the 1024×1024 crop) + the full per-join canvas
        await saveDebugBundle(sid, {
          [`join_${i}_lama_input.png`]: built.canvasDataUrl,
          [`join_${i}_lama_mask.png`]: built.maskDataUrl,
          [`join_${i}_full_canvas.png`]: built.fullCanvasDataUrl,
        });
        // Run LaMa on the 1024×1024 crop
        const cropResultUrl = await inpaintJoin({
          canvasDataUrl: built.canvasDataUrl,
          maskDataUrl: built.maskDataUrl,
        });
        // Paste the crop result back into the full per-join canvas at (cropX, cropY)
        const fullImg = await loadImg(built.fullCanvasDataUrl);
        const cropImg = await loadImg(cropResultUrl);
        const finalCv = document.createElement('canvas');
        finalCv.width = built.fullW;
        finalCv.height = built.fullH;
        const fctx = finalCv.getContext('2d');
        fctx.drawImage(fullImg, 0, 0);
        // drawImage clips automatically when the destination region falls outside the canvas
        fctx.drawImage(cropImg, built.cropX, built.cropY);
        const finalUrl = finalCv.toDataURL('image/png');
        const finalLoaded = await loadImg(finalUrl);
        // Snapshot the mask context at INPAINT TIME — paste-back uses these values so the
        // visible box stays anchored to the actual inpainted region even if the user later
        // changes maskZoneW or maskHeightOverride.
        const maskRectAtInpaint = computeMaskRectUnified(i); // base display coords
        newResults[i] = {
          dataUrl: finalUrl,
          img: finalLoaded,
          atInpaint: {
            maskRectFull: built.maskRectFull,    // {x, y, w, h} in full-res join-canvas coords
            maskRectDisplay: maskRectAtInpaint,  // base display coords used at inpaint time
            fullW: built.fullW,
            fullH: built.fullH,
          },
        };
        setJoinResults({ ...newResults });
        // Save outputs
        await saveDebugBundle(sid, {
          [`join_${i}_lama_output.png`]: cropResultUrl,
          [`join_${i}_pasted_back.png`]: finalUrl,
        });
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      setBusyMessage('');
    }
  }

  async function runAssemble() {
    if (N === 0) return;
    setBusy(true);
    setBusyMessage('Assembling...');
    setError(null);
    try {
      // Any join the user hasn't opened gets auto-stitched (no LaMa call).
      // We track the result map locally because setJoinResults / setDebugSessionId
      // only commit on the next render — the rest of this function needs the
      // up-to-date values right now.
      let effectiveSid = debugSessionId;
      let effectiveResults = joinResults;
      let effectiveUsage = joinUsage;

      const missing = [];
      for (let i = 0; i < N; i++) if (!joinResults[i]) missing.push(i);
      if (missing.length) {
        if (!effectiveSid) {
          const now = new Date();
          const ts = `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}_${String(now.getHours()).padStart(2,'0')}${String(now.getMinutes()).padStart(2,'0')}${String(now.getSeconds()).padStart(2,'0')}`;
          effectiveSid = `${ts}_${Math.random().toString(36).slice(2, 6)}`;
          setDebugSessionId(effectiveSid);
          const origFiles = {};
          fragments.forEach((f, i) => { origFiles[`fragment_${i}_original.png`] = f.dataUrl; });
          await saveDebugBundle(effectiveSid, origFiles, {
            timestamp: now.toISOString(),
            fragments: fragments.map((f, i) => ({ index: i, name: f.name, w: f.w, h: f.h, yOffset: f.yOffset || 0 })),
            maskZoneW, stripWidth: STRIP_WIDTH, lamaCropSize: LAMA_CROP_SIZE,
            n_joins: N,
          });
        }
        effectiveResults = { ...joinResults };
        effectiveUsage = { ...joinUsage };
        for (const i of missing) {
          setBusyMessage(`Stitching join ${i + 1} / ${N} (no inpaint)...`);
          const built = buildJoinCanvasAndMask(i);
          await saveDebugBundle(effectiveSid, {
            [`join_${i}_full_canvas.png`]: built.fullCanvasDataUrl,
          });
          const loaded = await loadImg(built.fullCanvasDataUrl);
          effectiveResults[i] = {
            dataUrl: built.fullCanvasDataUrl,
            img: loaded,
            atInpaint: null,
          };
          effectiveUsage[i] = 'skip';
        }
        setJoinResults(effectiveResults);
        setJoinUsage(effectiveUsage);
      }

      // Decide assembly strategy. The browser's canvas dimension limit is ~32767 px in Chrome,
      // less in Safari. Sum of fragment widths can easily exceed this for the multi-thread flow
      // (4 × 17000 = 68000). When fragments come from the multi-thread flow (have mtiSessionId)
      // and the source files are on disk, do server-side assembly via Pillow — no canvas limit.
      const totalLogicalW = fragments.reduce((s, f) => s + Math.max(0, (f.w || 0) - 2 * STRIP_WIDTH), 0)
                          + N * 1024 /* approx join width */;
      const useServerSide = (totalLogicalW > 32000) && fragments.every(f => f.mtiSessionId != null && f.mtiThreadIndex != null) && effectiveSid;

      const joinUsageArray = Array.from({ length: N }, (_, i) => effectiveUsage[i] || 'inpaint');

      let assembledUrl;
      if (useServerSide) {
        setBusyMessage('Assembling on server (Pillow)...');
        const r = await fetch('/api/multithread/assemble', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            multifragment_session_id: effectiveSid,
            multithread_session_id: fragments[0].mtiSessionId,
            strip_width: STRIP_WIDTH,
            join_usage: joinUsageArray,
            fragments: fragments.map(f => ({
              thread_index: f.mtiThreadIndex,
              w: f.w, h: f.h,
              yOffset: f.yOffset || 0,
              name: f.name,
            })),
          }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || `Server assembly failed (${r.status})`);
        assembledUrl = data.assembled_url;
        setJoinXCenters(Array.isArray(data.join_x_centers) ? data.join_x_centers : null);
      } else {
        // Fallback: client-side assembly via canvas (works for smaller totals)
        const joins = [];
        for (let i = 0; i < N; i++) {
          const r = effectiveResults[i];
          if (!r || !r.dataUrl) throw new Error(`Internal: join ${i + 1} has no dataUrl after auto-stitch`);
          joins.push({ dataUrl: r.dataUrl });
        }
        assembledUrl = await assembleTileable({
          fragments, joinResults: joins,
          stripL: STRIP_WIDTH, stripR: STRIP_WIDTH,
        });
        if (effectiveSid) {
          await saveDebugBundle(effectiveSid, { 'assembled_final.png': assembledUrl });
        }
      }
      setAssembledDataUrl(assembledUrl);
      setAssembledAlphaDataUrl(null);
      setAssembledDarkBlueDataUrl(null);
      setShowTile(false);
      setShowAlphaOverlay(false);
      setShowJoinLines(false);
      setView('result');

      // Auto-trigger alpha regeneration so the user immediately sees all 3
      // result images (RGB / α / dark-blue composite) without an extra click.
      // Only meaningful for the multithread flow (we need the saved B_red).
      const allMti = fragments.length > 0 && fragments.every(f => f.mtiSessionId && f.mtiThreadIndex != null);
      if (allMti && effectiveSid) {
        setBusyMessage('Generating final alpha + dark-blue composite...');
        await regenerateAlphaInternal({ sid: effectiveSid, results: effectiveResults, usage: effectiveUsage });
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
      setBusyMessage('');
    }
  }

  const joinDoneCount = Object.keys(joinResults).length;
  // Assemble is allowed as soon as there are ≥2 fragments. Any untouched
  // join is auto-stitched (no inpaint) by runAssemble.
  const allDone = N >= 2;

  function useAsWorkingImage() {
    if (!assembledDataUrl) return;
    onAssembleDone(assembledDataUrl);
  }

  function backToEditing() {
    setView('edit');
  }

  // Internal: actually call the regen-alpha endpoint and update state.
  // No try/finally for setRegeneratingAlpha so it can be reused inside
  // runAssemble's own try/finally without stomping on busy state.
  async function regenerateAlphaInternal(overrides = {}) {
    // overrides.{sid,results,usage} let runAssemble pass fresh local values
    // when the relevant React state hasn't committed yet (auto-stitch path).
    const sid     = overrides.sid     ?? debugSessionId;
    const results = overrides.results ?? joinResults;
    const usage   = overrides.usage   ?? joinUsage;
    if (!sid) throw new Error('No debug session — re-run Inpaint All Joins first');
    const allMti = fragments.length > 0 && fragments.every(f => f.mtiSessionId && f.mtiThreadIndex != null);
    // For each join, send the LaMa-mask rectangle in per-join canvas coords.
    // The backend uses this to constrain legacy alpha-regen to ONLY the
    // inpainted pixels and copy the per-thread alpha everywhere else.
    const joinsMeta = Array.from({ length: N }, (_, i) => {
      const r = results[i];
      return r?.atInpaint ? {
        maskRectFull: r.atInpaint.maskRectFull,
        fullW: r.atInpaint.fullW,
        fullH: r.atInpaint.fullH,
      } : null;
    });
    const joinUsageArr = Array.from({ length: N }, (_, i) => usage[i] || 'inpaint');
    const body = {
      multifragment_session_id: sid,
      multithread_session_id: allMti ? fragments[0].mtiSessionId : null,
      strip_width: STRIP_WIDTH,
      make_rgba: true,
      make_dark_blue: true,
      join_usage: joinUsageArr,
      joins: joinsMeta,
      fragments: fragments.map(f => ({
        thread_index: f.mtiThreadIndex,
        w: f.w, h: f.h,
        yOffset: f.yOffset || 0,
        name: f.name,
      })),
    };
    const r = await fetch('/api/multithread/regenerate-alpha', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `Server error ${r.status}`);
    const cacheBust = `?t=${Date.now()}`;
    // Prefer the no-wraparound "export" URLs the server now produces alongside
    // the wraparound versions. The editor view should match exactly what the
    // user will download. Tile preview repeats this 2× to verify closure.
    const exp = data.export_urls || {};
    const pick = (expKey, wrapUrl) => {
      if (exp[expKey]) return exp[expKey] + cacheBust;
      return wrapUrl ? wrapUrl + cacheBust : null;
    };
    setAssembledAlphaDataUrl(pick('alpha', data.assembled_alpha_url));
    setAssembledRgbaDataUrl(pick('rgba', data.assembled_rgba_url));
    setAssembledDarkBlueDataUrl(pick('dark_blue', data.assembled_dark_blue_url));
    // Also swap the top RGB viewer to the no-wraparound version.
    if (exp.final) setAssembledDataUrl(exp.final + cacheBust);

    // Pre-fetch the metadata JSON so the "Download Metadata" button is instant.
    // metadata_only=true short-circuits the export route (no image transforms).
    try {
      const mr = await fetch('/api/multithread/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...body, metadata_only: true }),
      });
      const md = await mr.json();
      if (mr.ok && md.export_urls?.metadata) {
        setMetadataUrl(md.export_urls.metadata + cacheBust);
      }
    } catch (_) { /* non-fatal: button falls back to lazy fetch */ }
  }

  async function regenerateAlphaForInpaints() {
    setRegeneratingAlpha(true);
    setError(null);
    try {
      await regenerateAlphaInternal();
    } catch (e) {
      setError(e.message);
    } finally {
      setRegeneratingAlpha(false);
    }
  }

  async function downloadMetadataOnly() {
    if (!debugSessionId) return;
    // Fast path: if metadata was pre-fetched at assemble time, just download.
    if (metadataUrl) {
      const a = document.createElement('a');
      a.href = metadataUrl;
      a.download = 'export_metadata.json';
      document.body.appendChild(a); a.click(); a.remove();
      return;
    }
    try {
      const allMti = fragments.length > 0 && fragments.every(f => f.mtiSessionId && f.mtiThreadIndex != null);
      const body = {
        multifragment_session_id: debugSessionId,
        multithread_session_id: allMti ? fragments[0].mtiSessionId : null,
        strip_width: STRIP_WIDTH,
        join_usage: getJoinUsageArray(),
        metadata_only: true,
        fragments: fragments.map(f => ({
          thread_index: f.mtiThreadIndex,
          w: f.w, h: f.h,
          yOffset: f.yOffset || 0,
          name: f.name,
        })),
      };
      const r = await fetch('/api/multithread/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || `Server error ${r.status}`);
      const url = data.export_urls?.metadata;
      if (!url) throw new Error('No metadata URL returned');
      const a = document.createElement('a');
      a.href = url + `?t=${Date.now()}`;
      a.download = 'export_metadata.json';
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e) {
      setError(`Metadata download failed: ${e.message}`);
    }
  }

  // Compose F · α + customBg · (1−α) client-side and trigger a download.
  // Uses the already-loaded assembled_F + assembled_alpha (so no extra
  // server roundtrip beyond what we already did to load them).
  async function downloadCustomBgComposite(rgbHex) {
    if (!assembledRgbaDataUrl) {
      setError('Need assembled outputs first');
      return;
    }
    try {
      const hex = rgbHex.replace('#', '');
      const r = parseInt(hex.slice(0, 2), 16);
      const g = parseInt(hex.slice(2, 4), 16);
      const b = parseInt(hex.slice(4, 6), 16);

      // We compose from assembled_rgba (which already has F as RGB + α as alpha)
      // because that's the canonical "thread on transparent" image. comp = F·α + bg·(1−α).
      const im = await new Promise((res, rej) => {
        const x = new Image();
        x.crossOrigin = 'anonymous';
        x.onload = () => res(x);
        x.onerror = rej;
        x.src = assembledRgbaDataUrl;
      });
      const cv = document.createElement('canvas');
      cv.width = im.width; cv.height = im.height;
      const cctx = cv.getContext('2d');
      // Fill bg first, then composite the RGBA on top — browser does the
      // standard F · α + bg · (1−α) for us via drawImage with default
      // composite op.
      cctx.fillStyle = `rgb(${r},${g},${b})`;
      cctx.fillRect(0, 0, cv.width, cv.height);
      cctx.drawImage(im, 0, 0);

      // Trigger download
      const blob = await new Promise(res => cv.toBlob(res, 'image/png'));
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `assembled_on_bg_${hex}.png`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError(`Custom-bg composite failed: ${e.message}`);
    }
  }

  async function exportFinal() {
    if (!debugSessionId) return;
    setExporting(true);
    setError(null);
    try {
      const allMti = fragments.length > 0 && fragments.every(f => f.mtiSessionId && f.mtiThreadIndex != null);
      const body = {
        multifragment_session_id: debugSessionId,
        multithread_session_id: allMti ? fragments[0].mtiSessionId : null,
        strip_width: STRIP_WIDTH,
        join_usage: getJoinUsageArray(),
        fragments: fragments.map(f => ({
          thread_index: f.mtiThreadIndex,
          w: f.w, h: f.h,
          yOffset: f.yOffset || 0,
          name: f.name,
        })),
      };
      const r = await fetch('/api/multithread/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || `Server error ${r.status}`);

      // Slimmed: Export now downloads only the RGBA (no-bg cutout) + metadata JSON.
      // For the other formats (RGB, α, dark-blue, custom-bg), the user has
      // dedicated buttons in the lower toolbar.
      const cacheBust = `?t=${Date.now()}`;
      const triggers = [];
      const order = ['rgba', 'metadata'];
      for (const key of order) {
        const url = data.export_urls?.[key];
        if (!url) continue;
        triggers.push({
          url: url + cacheBust,
          filename: key === 'metadata'
            ? 'export_metadata.json'
            : `export_assembled_${key}.png`,
        });
      }
      // Programmatic anchor-clicks; small stagger so the browser doesn't drop any.
      for (let i = 0; i < triggers.length; i++) {
        const t = triggers[i];
        const a = document.createElement('a');
        a.href = t.url;
        a.download = t.filename;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        a.remove();
        await new Promise(res => setTimeout(res, 250));
      }
    } catch (e) {
      setError(`Export failed: ${e.message}`);
    } finally {
      setExporting(false);
    }
  }

  async function saveToLibrary() {
    if (!debugSessionId) return;
    const defaultLabel = fragments[0]?.name?.replace(/\.[^.]+$/, '') || 'yarn';
    const label = window.prompt('Label for this yarn in the library:', defaultLabel);
    if (label === null) return;  // user cancelled
    const allMti = fragments.length > 0 && fragments.every(f => f.mtiSessionId && f.mtiThreadIndex != null);
    setSavingToLibrary(true);
    setError(null);
    setLibraryStatus(null);
    try {
      // Make sure the export image set + metadata are on disk before we save.
      const exportBody = {
        multifragment_session_id: debugSessionId,
        multithread_session_id: allMti ? fragments[0].mtiSessionId : null,
        strip_width: STRIP_WIDTH,
        join_usage: getJoinUsageArray(),
        fragments: fragments.map(f => ({
          thread_index: f.mtiThreadIndex,
          w: f.w, h: f.h,
          yOffset: f.yOffset || 0,
          name: f.name,
        })),
      };
      const eRes = await fetch('/api/multithread/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(exportBody),
      });
      const eData = await eRes.json();
      if (!eRes.ok) throw new Error(eData.error || `Export step failed (${eRes.status})`);

      const sRes = await fetch('/api/multithread/save-to-library', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          multifragment_session_id: debugSessionId,
          multithread_session_id: allMti ? fragments[0].mtiSessionId : null,
          label: label.trim() || defaultLabel,
        }),
      });
      const sData = await sRes.json();
      if (!sRes.ok) throw new Error(sData.error || `Save failed (${sRes.status})`);
      setLibraryStatus({ yarnId: sData.id, libraryPath: sData.libraryPath, label: sData.label });
    } catch (e) {
      setLibraryStatus({ error: e.message });
      setError(`Save to Library failed: ${e.message}`);
    } finally {
      setSavingToLibrary(false);
    }
  }

  // ===== Render =====
  // Result view (post-Assemble): show the assembled image + tile preview + alpha controls.
  if (view === 'result' && assembledDataUrl) {
    // Compute the two STRAIGHT solid-band lines for the assembled view.
    // Each fragment carries its own band (mtiBand.top_y, bottom_y in
    // thread-local coords). After centred-alignment the band centres should
    // land at the same assembled Y; we average top and bottom across all
    // fragments to get the unified lines.
    let solidBandLines = null;
    let widthMarkersAssembled = [];   // [{x_assembled, top_y, bottom_y, width_mm, width_px, fragIdx}]
    try {
      const total_h = Math.max(...fragments.map(f => f.h || 0));
      const tops = [], bots = [];
      for (const f of fragments) {
        const b = f.mtiBand;
        if (!b || b.top_y == null || b.bottom_y == null || b.top_y < 0 || b.bottom_y < 0) continue;
        const yo = f.yOffset || 0;
        const frag_y = (total_h - (f.h || 0)) / 2 + yo;
        tops.push(frag_y + b.top_y);
        bots.push(frag_y + b.bottom_y);
      }
      if (tops.length > 0 && bots.length > 0) {
        const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
        solidBandLines = { top_y: Math.round(mean(tops)), bottom_y: Math.round(mean(bots)) };
      }
      // Width markers — every marker uses the unified solidBandLines values
      // (so all markers across all 4 threads show the SAME width in the
      // assembled view, since the band lines are straight/parallel). 5 X
      // positions per fragment are kept just for label placement.
      const dpi = fragments[0]?.mtiDpi || 1600;
      let unified_width_px = null, unified_width_mm = null;
      if (solidBandLines) {
        unified_width_px = solidBandLines.bottom_y - solidBandLines.top_y + 1;
        unified_width_mm = (unified_width_px / dpi) * 25.4;
      }
      const STRIP = STRIP_WIDTH;
      const JOIN_W = STRIP * 2;  // every per-join canvas is 1024 wide
      let x_cur = 0;
      for (let i = 0; i < fragments.length; i++) {
        const f = fragments[i];
        const interior_w = Math.max(0, (f.w || 0) - 2 * STRIP);
        const samples = f.mtiWidthSamples;
        if (Array.isArray(samples) && solidBandLines) {
          for (const s of samples) {
            if (s.x < STRIP || s.x > (f.w || 0) - STRIP) continue;
            widthMarkersAssembled.push({
              fragIdx: i,
              x_assembled: x_cur + (s.x - STRIP),
              top_y: solidBandLines.top_y,
              bottom_y: solidBandLines.bottom_y,
              width_mm: unified_width_mm,
              width_px: unified_width_px,
            });
          }
        }
        x_cur += interior_w + JOIN_W;
      }
    } catch {}
    return (
      <ResultView
        assembledDataUrl={assembledDataUrl}
        assembledAlphaDataUrl={assembledAlphaDataUrl}
        assembledRgbaDataUrl={assembledRgbaDataUrl}
        assembledDarkBlueDataUrl={assembledDarkBlueDataUrl}
        joinBoxes={joinBoxes}
        showJoinLines={showJoinLines}
        setShowJoinLines={setShowJoinLines}
        showTile={showTile}
        setShowTile={setShowTile}
        showAlphaOverlay={showAlphaOverlay}
        setShowAlphaOverlay={setShowAlphaOverlay}
        showSolidBand={showSolidBand}
        setShowSolidBand={setShowSolidBand}
        solidBandLines={solidBandLines}
        showWidths={showWidths}
        setShowWidths={setShowWidths}
        widthMarkers={widthMarkersAssembled}
        dpi={fragments[0]?.mtiDpi || 1600}
        onRegenerateAlpha={regenerateAlphaForInpaints}
        regenerating={regeneratingAlpha}
        onExport={exportFinal}
        exporting={exporting}
        onSaveToLibrary={saveToLibrary}
        savingToLibrary={savingToLibrary}
        libraryStatus={libraryStatus}
        onDownloadMetadata={downloadMetadataOnly}
        onDownloadCustomBg={downloadCustomBgComposite}
        onUseAsWorkingImage={useAsWorkingImage}
        onBackToEditing={backToEditing}
        onCancel={onCancel}
        debugDir={debugDir}
        debugSessionId={debugSessionId}
        error={error}
      />
    );
  }

  return (
    <main className="flex-1 flex flex-col p-4 bg-gray-950 gap-3 overflow-auto">
      <div className="flex items-center gap-3 flex-wrap">
        <h2 className="text-white text-base font-medium">Multi-Fragment Stitcher</h2>
        <span className="text-xs text-gray-400">
          {N === 0 ? 'No fragments yet'
            : `${N} fragment${N > 1 ? 's' : ''}${N >= 2 ? ` — ${joinDoneCount}/${N} joins inpainted` : ' — need 2+ to inpaint'}`}
        </span>
        <div className="flex-1" />
        <button onClick={() => fileInputSingleRef.current?.click()} disabled={busy}
          className="bg-gray-700 hover:bg-gray-600 text-white text-xs py-1.5 px-3 rounded disabled:opacity-50">+ Add Fragment</button>
        <button onClick={() => fileInputBulkRef.current?.click()} disabled={busy}
          className="bg-gray-700 hover:bg-gray-600 text-white text-xs py-1.5 px-3 rounded disabled:opacity-50">+ Bulk Upload</button>
        <button onClick={onCancel} disabled={busy}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs py-1.5 px-3 rounded disabled:opacity-50">Cancel</button>
        <input ref={fileInputSingleRef} type="file" accept="image/*" onChange={handleSingleFile} className="hidden" />
        <input ref={fileInputBulkRef} type="file" accept="image/*" multiple onChange={handleMultiFiles} className="hidden" />
      </div>

      {error && <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-2 rounded text-sm">{error}</div>}

      {N === 0 && (
        <div className="rounded border-2 border-dashed border-gray-700 p-12 text-center text-gray-400 text-sm">
          Upload fragments of the same thread that need to be stitched together.<br/>
          Use <span className="text-gray-200">+ Bulk Upload</span> to pick multiple at once (sorted by filename).
        </div>
      )}

      {/* Fragment cards with prominent Y sliders */}
      {N > 0 && (
        <div className="flex gap-2 flex-wrap">
          {fragments.map((f, i) => (
            <div
              key={f.id}
              draggable
              onDragStart={() => { dragReorderIdxRef.current = i; }}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); moveFragment(dragReorderIdxRef.current, i); dragReorderIdxRef.current = null; }}
              className="bg-gray-900 border border-gray-700 rounded p-2 flex flex-col gap-1.5 w-44"
            >
              <div className="flex items-center gap-1.5">
                <span className="bg-blue-700 text-white font-bold rounded-full w-6 h-6 flex items-center justify-center text-xs">{i + 1}</span>
                <span className="text-[10px] text-gray-300 truncate flex-1" title={f.name}>{f.name}</span>
                <button onClick={() => onCropFragment(f.id)}
                  className="text-[10px] bg-gray-800 hover:bg-gray-700 text-gray-300 py-0.5 px-1.5 rounded">✂</button>
                <button onClick={() => removeFragment(f.id)}
                  className="text-[10px] bg-red-900 hover:bg-red-800 text-red-200 py-0.5 px-1.5 rounded">✕</button>
              </div>
              <img src={f.dataUrl} alt={f.name} className="w-full h-12 object-cover rounded" />
              <div>
                <div className="flex items-center justify-between text-[10px] text-gray-400">
                  <span>↕ Y offset</span>
                  <span className={`font-mono ${(f.yOffset || 0) !== 0 ? 'text-yellow-300' : 'text-gray-500'}`}>{f.yOffset || 0}px</span>
                </div>
                <input
                  type="range"
                  min={-Math.max(300, Math.floor(f.h / 2))}
                  max={Math.max(300, Math.floor(f.h / 2))}
                  step={1}
                  value={f.yOffset || 0}
                  onChange={e => setFragYOffset(i, parseInt(e.target.value))}
                  className="w-full"
                />
                <div className="flex justify-between gap-1 mt-0.5">
                  <button onClick={() => setFragYOffset(i, (f.yOffset || 0) - 10)}
                    className="flex-1 text-[10px] bg-gray-800 hover:bg-gray-700 text-gray-300 py-0.5 rounded">↑ 10</button>
                  <button onClick={() => setFragYOffset(i, 0)}
                    className="text-[10px] bg-gray-800 hover:bg-gray-700 text-gray-300 py-0.5 px-2 rounded">0</button>
                  <button onClick={() => setFragYOffset(i, (f.yOffset || 0) + 10)}
                    className="flex-1 text-[10px] bg-gray-800 hover:bg-gray-700 text-gray-300 py-0.5 rounded">↓ 10</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Toolbar */}
      {N >= 1 && (
        <div className="flex gap-2 items-center flex-wrap bg-gray-900 border border-gray-800 rounded p-2">
          <button onClick={() => setTool('drag')}
            className={`text-xs px-3 py-1.5 rounded font-medium ${tool === 'drag' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            Drag (move fragment Y)
          </button>
          <button onClick={() => setTool('paint')}
            className={`text-xs px-3 py-1.5 rounded font-medium ${tool === 'paint' ? 'bg-cyan-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            Paint Mask
          </button>
          {tool === 'paint' && (
            <>
              <label className="text-xs text-gray-400">Brush:</label>
              <input type="range" min={5} max={300} value={brushSize} onChange={e => setBrushSize(parseInt(e.target.value))} className="w-28" />
              <span className="text-xs text-gray-400 w-12">{brushSize}px</span>
              <button onClick={clearPaint}
                className="text-xs px-3 py-1.5 rounded bg-red-900 text-red-300 hover:bg-red-800">Clear Paint</button>
            </>
          )}
          <span className="border-l border-gray-700 h-4" />
          <label className="text-xs text-gray-400">Mask W:</label>
          <input type="range" min={10} max={500} value={maskZoneW} onChange={e => setMaskZoneW(parseInt(e.target.value))} className="w-28" />
          <span className="text-xs text-gray-400 w-14">{maskZoneW}px</span>
          <label className="text-xs text-gray-400">Mask H:</label>
          <input type="range" min={40} max={800}
            value={maskHeightOverride ?? (() => {
              const r = computeMaskRectUnified(0); return r ? r.h : 200;
            })()}
            onChange={e => setMaskHeightOverride(parseInt(e.target.value))}
            className="w-28" />
          <span className="text-xs text-gray-400 w-14">
            {maskHeightOverride != null ? `${maskHeightOverride}px` : 'auto'}
          </span>
          <button onClick={() => setMaskHeightOverride(null)}
            className="text-[10px] bg-gray-800 hover:bg-gray-700 text-gray-300 py-0.5 px-2 rounded"
            title="Reset to auto-detected thread height">↺</button>
          <span className="border-l border-gray-700 h-4" />
          <button
            onClick={() => setShowWidths(v => !v)}
            title="Toggle thread-width markers (blue dashed verticals at 5 X-positions per thread, labelled mm + px)"
            className={`text-xs px-3 py-1.5 rounded font-medium ${
              showWidths ? 'bg-blue-700 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            {showWidths ? '✓ Widths' : 'Show Widths'}
          </button>
          <div className="flex-1" />
          <button
            onClick={runInpaintAll}
            disabled={busy || N < 2}
            className="bg-purple-700 hover:bg-purple-600 disabled:bg-gray-800 disabled:text-gray-600 text-white text-sm py-1.5 px-4 rounded font-medium"
          >
            {busy && busyMessage ? busyMessage : (joinDoneCount > 0 ? 'Re-Inpaint All Joins' : 'Inpaint All Joins')}
          </button>
          <button
            onClick={runAssemble}
            disabled={!allDone || busy}
            className="bg-green-600 hover:bg-green-500 disabled:bg-gray-800 disabled:text-gray-600 text-white text-sm py-1.5 px-4 rounded font-medium"
          >
            Assemble Final
          </button>
        </div>
      )}

      {/* Per-box "use inpainted vs skip" toggles. Visible once all joins
          have been inpainted at least once. Each box corresponds to a join
          location — click to skip its LaMa output (use natural overlap).
          Hover to highlight the box on the canvas. */}
      {N >= 2 && joinDoneCount === N && (
        <div className="bg-gray-900 border border-gray-800 rounded px-3 py-2 flex items-center gap-2 text-xs flex-wrap">
          <span className="text-gray-300 font-medium">Boxes:</span>
          <span className="text-gray-500">click to skip the inpaint for that box (uses raw overlap instead).</span>
          <div className="flex-1" />
          {Array.from({ length: N }, (_, i) => {
            const usage = joinUsage[i] || 'inpaint';
            const isSkip = usage === 'skip';
            return (
              <button
                key={i}
                onClick={() => setJoinUsage(prev => ({ ...prev, [i]: isSkip ? 'inpaint' : 'skip' }))}
                onMouseEnter={() => setHighlightJoin(i)}
                onMouseLeave={() => setHighlightJoin(null)}
                title={isSkip ? `Box ${i + 1}: stitched (no LaMa, raw overlap of the two strips)` : `Box ${i + 1}: inpainted by LaMa — click to switch to stitched`}
                className={`text-xs py-1 px-2 rounded font-mono inline-flex items-center gap-1.5 ${
                  isSkip
                    ? 'bg-yellow-700 hover:bg-yellow-600 text-yellow-100'
                    : 'bg-emerald-700 hover:bg-emerald-600 text-emerald-100'
                }`}
              >
                <span className="font-bold">Box {i + 1}</span>
                <span className="opacity-90">·</span>
                <span className="text-[10px] uppercase tracking-wider">{isSkip ? 'Stitched' : 'Inpainted'}</span>
              </button>
            );
          })}
          <button
            onClick={() => setJoinUsage({})}
            className="text-[11px] bg-gray-800 hover:bg-gray-700 text-gray-300 py-1 px-2 rounded ml-1"
            title="Reset all to use the inpainted version"
          >
            Reset all
          </button>
        </div>
      )}

      {/* Debug session info */}
      {debugSessionId && (
        <div className="bg-gray-900 border border-gray-800 rounded px-3 py-2 text-xs flex items-center gap-3">
          <span className="text-gray-400">Debug session:</span>
          <span className="font-mono text-gray-300">{debugSessionId}</span>
          {debugDir && <span className="text-gray-500 truncate flex-1" title={debugDir}>{debugDir}</span>}
          <button onClick={openDebugFolder}
            className="bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs py-1 px-2 rounded">Open Folder</button>
        </div>
      )}

      {/* Zoom controls */}
      {N >= 1 && layout && (
        <div className="bg-gray-900 border border-gray-800 rounded px-3 py-2 flex items-center gap-2 text-xs flex-wrap">
          <span className="text-gray-400">Zoom:</span>
          <button onClick={() => setZoomAt(zoom / ZOOM_STEP)}
            className="bg-gray-800 hover:bg-gray-700 text-gray-200 w-7 h-7 rounded font-bold">−</button>
          <input
            type="range"
            min={ZOOM_MIN} max={ZOOM_MAX} step={0.1}
            value={zoom}
            onChange={e => setZoomAt(parseFloat(e.target.value))}
            className="w-32"
          />
          <button onClick={() => setZoomAt(zoom * ZOOM_STEP)}
            className="bg-gray-800 hover:bg-gray-700 text-gray-200 w-7 h-7 rounded font-bold">+</button>
          <span className="text-gray-300 font-mono w-14 text-right">{(zoom * 100).toFixed(0)}%</span>
          <button onClick={zoomFit}
            className="bg-gray-800 hover:bg-gray-700 text-gray-200 px-2 py-1 rounded">Fit</button>
          <span className="text-gray-500 ml-2 hidden md:inline">Tip: hold ⌘/Ctrl + scroll inside the canvas to zoom on the cursor</span>
        </div>
      )}

      {/* Unified canvas */}
      {N >= 1 && layout && (() => {
        // Compute display size given zoom. At zoom=1 the canvas fits FIT_DISPLAY_H tall.
        const dispH = Math.round(FIT_DISPLAY_H * zoom);
        const dispW = Math.round((layout.totalW / layout.totalH) * dispH);
        return (
          <div
            ref={canvasScrollRef}
            className="rounded border border-gray-700 overflow-auto bg-black self-start max-w-full"
            style={{ maxHeight: `${FIT_DISPLAY_H}px` }}
          >
            <canvas
              ref={canvasRef}
              className="block"
              style={{
                width: `${dispW}px`,
                height: `${dispH}px`,
                cursor: tool === 'drag' ? 'ns-resize' : 'crosshair',
                imageRendering: zoom > 2 ? 'pixelated' : 'auto',
              }}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            />
          </div>
        );
      })()}

      <p className="text-xs text-gray-500">
        {tool === 'drag'
          ? 'Drag any fragment up/down to align (or use the slider on each card). Yellow zone = will be inpainted by LaMa. Cyan = your paint additions.'
          : 'Paint extra mask area in cyan. Shift+drag to erase. Switch to Drag to nudge fragments.'}
      </p>
    </main>
  );
}

// ResultCanvas — unified canvas renderer for all three result panels (RGB,
// alpha matte, dark-blue composite). Same MAX_W scaling so all three end up
// at the same display width. Draws all overlays consistently:
//   - join lines (vertical green/yellow with badge)
//   - solid-band (two horizontal dashed-red lines at unified y_top/y_bottom)
//   - width markers (blue dashed verticals at each X with mm + px label)
//   - alpha overlay (red-tinted where alpha < 0.5; only on the RGB panel)
//   - tile preview (3× repeat, only for the RGB panel)
function ResultCanvas({
  src, alphaSrc, onDims,
  showAlphaOverlay = false, showTile = false,
  showJoinLines, joinBoxes,
  showSolidBand, solidBandLines,
  showWidths, widthMarkers,
  maxHeight,
}) {
  const ref = useRef(null);
  useEffect(() => {
    if (!src) return;
    let cancelled = false;
    const im = new Image();
    im.onload = async () => {
      if (cancelled) return;
      const cv = ref.current;
      if (!cv) return;
      const W = im.width, H = im.height;
      const MAX_W = 12288;
      const repeats = showTile ? 2 : 1;
      const targetW = W * repeats;
      const vs = Math.min(1, MAX_W / targetW);
      cv.width = Math.round(targetW * vs);
      cv.height = Math.round(H * vs);
      const ctx = cv.getContext('2d');
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.fillStyle = 'black';
      ctx.fillRect(0, 0, cv.width, cv.height);
      for (let r = 0; r < repeats; r++) {
        ctx.drawImage(im, 0, 0, W, H,
          Math.round(r * W * vs), 0, Math.round(W * vs), Math.round(H * vs));
      }
      // Alpha overlay (RGB panel only)
      if (showAlphaOverlay && alphaSrc) {
        const a = await new Promise((res, rej) => {
          const aim = new Image();
          aim.onload = () => res(aim);
          aim.onerror = rej;
          aim.src = alphaSrc;
        });
        const tmp = document.createElement('canvas');
        tmp.width = cv.width; tmp.height = cv.height;
        const tctx = tmp.getContext('2d');
        for (let r = 0; r < repeats; r++) {
          tctx.drawImage(a, 0, 0, a.width, a.height,
            Math.round(r * W * vs), 0, Math.round(W * vs), Math.round(H * vs));
        }
        const id = tctx.getImageData(0, 0, tmp.width, tmp.height);
        const d = id.data;
        for (let p = 0; p < d.length; p += 4) {
          const v = d[p];
          if (v < 128) { d[p] = 255; d[p+1] = 0; d[p+2] = 0; d[p+3] = 110; }
          else { d[p+3] = 0; }
        }
        tctx.putImageData(id, 0, 0);
        ctx.drawImage(tmp, 0, 0);
      }
      // Tile-preview seam markers
      if (showTile && repeats > 1) {
        ctx.save();
        ctx.strokeStyle = 'rgba(255, 100, 100, 0.5)';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        for (let r = 1; r < repeats; r++) {
          const x = Math.round(r * W * vs);
          ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, cv.height); ctx.stroke();
        }
        ctx.restore();
      }
      // Width markers — blue dashed verticals (5 ON, 5 OFF)
      if (showWidths && Array.isArray(widthMarkers) && widthMarkers.length) {
        ctx.save();
        const fontPx = Math.max(10, Math.round(11 / Math.max(0.4, vs)) * vs);
        ctx.font = `bold ${fontPx}px ui-sans-serif, system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        const lineW = Math.max(2, Math.round(2 / Math.max(0.4, vs) * vs));
        const dashLen = 5;   // 5 px ON, 5 px OFF (period 10) — vertical
        for (let r = 0; r < repeats; r++) {
          for (const m of widthMarkers) {
            const x = Math.round((r * W + m.x_assembled) * vs);
            const y0 = Math.round(m.top_y * vs);
            const y1 = Math.round(m.bottom_y * vs);
            ctx.fillStyle = 'rgba(59, 130, 246, 1)';
            for (let yy = y0; yy <= y1; yy += dashLen * 2) {
              const segH = Math.min(dashLen, y1 - yy + 1);
              if (segH <= 0) break;
              ctx.fillRect(x - Math.floor(lineW / 2), yy, lineW, segH);
            }
            const label = `${m.width_mm.toFixed(2)} mm · ${m.width_px} px`;
            const padX = Math.round(fontPx * 0.3);
            const padY = Math.round(fontPx * 0.2);
            const tw = ctx.measureText(label).width;
            let labelY = y0 - Math.round(fontPx * 0.4);
            if (labelY - fontPx < 0) labelY = y1 + fontPx + Math.round(fontPx * 0.4);
            ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
            ctx.fillRect(x - tw / 2 - padX, labelY - fontPx - padY,
                         tw + padX * 2, fontPx + padY * 2);
            ctx.fillStyle = 'rgba(147, 197, 253, 1)';
            ctx.fillText(label, x, labelY);
          }
        }
        ctx.restore();
      }
      // Solid-band lines — thin dashed red horizontals (10 ON, 10 OFF)
      if (showSolidBand && solidBandLines &&
          Number.isFinite(solidBandLines.top_y) && Number.isFinite(solidBandLines.bottom_y)) {
        ctx.save();
        const thickness = Math.max(2, Math.round(cv.height * 0.012));
        const dashLen = 10;   // 10 px ON, 10 px OFF (period 20) — horizontal
        ctx.fillStyle = 'rgba(239, 68, 68, 1)';
        for (let r = 0; r < repeats; r++) {
          const x0 = Math.round(r * W * vs);
          const x1 = Math.round((r + 1) * W * vs);
          for (const yLogical of [solidBandLines.top_y, solidBandLines.bottom_y]) {
            const y = Math.round(yLogical * vs - thickness / 2);
            for (let xx = x0; xx < x1; xx += dashLen * 2) {
              const segW = Math.min(dashLen, x1 - xx);
              if (segW <= 0) break;
              ctx.fillRect(xx, y, segW, thickness);
            }
          }
        }
        ctx.restore();
      }
      // Join boxes — two vertical lines per box (start + end), same colour
      // and label. For the wraparound join, the box straddles the tile
      // boundary so it has two segments — one at each edge of the image.
      if (showJoinLines && Array.isArray(joinBoxes) && joinBoxes.length) {
        ctx.save();
        const labelFont = `bold ${Math.max(10, Math.round(11 / Math.max(0.5, vs)) * vs)}px sans-serif`;
        for (let r = 0; r < repeats; r++) {
          for (let i = 0; i < joinBoxes.length; i++) {
            const box = joinBoxes[i];
            const isSkip = box.usage === 'skip';
            const colour = isSkip ? 'rgba(234, 179, 8, 0.95)' : 'rgba(16, 185, 129, 0.95)';
            const text = `${box.joinIdx + 1} · ${isSkip ? 'STITCHED' : 'INPAINTED'}`;
            for (const seg of (box.segments || [])) {
              const x0 = Math.round((r * W + seg.startX) * vs);
              const x1 = Math.round((r * W + seg.endX)   * vs);
              ctx.strokeStyle = colour;
              ctx.lineWidth = 2;
              ctx.setLineDash(isSkip ? [8, 6] : []);
              ctx.beginPath(); ctx.moveTo(x0, 0); ctx.lineTo(x0, cv.height); ctx.stroke();
              ctx.beginPath(); ctx.moveTo(x1, 0); ctx.lineTo(x1, cv.height); ctx.stroke();
              ctx.setLineDash([]);
              // Label between the two lines (or clamped to canvas)
              ctx.font = labelFont;
              const tw = ctx.measureText(text).width;
              const padX = 6, badgeH = 18;
              const cx = (x0 + x1) / 2;
              const bx = Math.max(0, Math.min(cv.width - tw - 2 * padX, cx - (tw + 2 * padX) / 2));
              const by = 4;
              ctx.fillStyle = colour;
              ctx.fillRect(bx, by, tw + 2 * padX, badgeH);
              ctx.fillStyle = '#000';
              ctx.textBaseline = 'middle';
              ctx.fillText(text, bx + padX, by + badgeH / 2);
            }
          }
        }
        ctx.restore();
      }
      if (onDims) onDims({ w: W, h: H });
    };
    im.src = src;
    return () => { cancelled = true; };
  }, [src, alphaSrc, showAlphaOverlay, showTile,
      showJoinLines, joinBoxes,
      showSolidBand, solidBandLines?.top_y, solidBandLines?.bottom_y,
      showWidths, widthMarkers?.length]);

  return (
    <div className="rounded border border-gray-700 overflow-auto bg-black max-w-full" style={{ maxHeight }}>
      <canvas ref={ref} className="block" style={{ imageRendering: 'pixelated' }} />
    </div>
  );
}

// ImageWithJoinLines — wraps a static <img> in a relative-positioned container
// so we can overlay vertical lines at each join's X-center when the toggle is on.
// imgDims gives the natural image dimensions (used to convert pixel-space join
// X coords into a percentage of the displayed width).
function ImageWithJoinLines({ src, alt, imgDims, joinXCenters, joinUsage, showJoinLines, maxHeight }) {
  const W = imgDims?.w;
  const showLines = showJoinLines && Array.isArray(joinXCenters) && joinXCenters.length > 0 && W > 0;
  return (
    <div className="rounded border border-gray-700 overflow-auto bg-black max-w-full" style={{ maxHeight: `${maxHeight}px` }}>
      <div className="relative inline-block">
        <img src={src} alt={alt} className="block max-w-none" style={{ imageRendering: 'pixelated' }} />
        {showLines && joinXCenters.map((jx, i) => {
          const usage = (joinUsage && joinUsage[i]) || 'inpaint';
          const isSkip = usage === 'skip';
          const leftPct = (jx / W) * 100;
          const colour = isSkip ? 'rgba(234, 179, 8, 0.95)' : 'rgba(16, 185, 129, 0.95)';
          return (
            <div key={i}>
              {/* The vertical line */}
              <div
                className="absolute top-0 bottom-0 pointer-events-none"
                style={{
                  left: `${leftPct}%`,
                  width: '2px',
                  backgroundColor: colour,
                  borderLeft: isSkip ? '1px dashed rgba(234, 179, 8, 0.95)' : 'none',
                  transform: 'translateX(-1px)',
                }}
              />
              {/* Label badge (1 · INPAINTED / STITCHED) anchored at top of line */}
              <div
                className="absolute top-1 pointer-events-none text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
                style={{
                  left: `${leftPct}%`,
                  backgroundColor: colour,
                  color: '#000',
                  transform: 'translateX(-50%)',
                  whiteSpace: 'nowrap',
                }}
              >
                {i + 1} · {isSkip ? 'STITCHED' : 'INPAINTED'}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================================
// ResultView — shown after Assemble Final. Displays the assembled image, lets the user
// preview tiling, regenerate alpha for the inpainted regions only, then "use" the
// result as the working image (which exits to single-image mode for further pipeline ops).
// ============================================================================
function ResultView({
  assembledDataUrl, assembledAlphaDataUrl, assembledRgbaDataUrl, assembledDarkBlueDataUrl,
  joinBoxes,
  showTile, setShowTile, showAlphaOverlay, setShowAlphaOverlay,
  showJoinLines, setShowJoinLines,
  showSolidBand, setShowSolidBand, solidBandLines,
  showWidths, setShowWidths, widthMarkers,
  dpi,
  onRegenerateAlpha, regenerating,
  onExport, exporting,
  onSaveToLibrary, savingToLibrary, libraryStatus,
  onDownloadMetadata, onDownloadCustomBg,
  onUseAsWorkingImage, onBackToEditing, onCancel,
  debugDir, debugSessionId, error,
}) {
  const [imgDims, setImgDims] = useState(null);
  // All 3 result panels now use the shared <ResultCanvas/> component which
  // handles its own image load + overlay drawing at the same scale.

  return (
    <main className="flex-1 flex flex-col p-4 bg-gray-950 gap-3 overflow-auto">
      <div className="flex items-center gap-3 flex-wrap">
        <h2 className="text-white text-base font-medium">Assembled Result</h2>
        {imgDims && (
          <span className="text-xs text-gray-400 font-mono">{imgDims.w}×{imgDims.h}</span>
        )}
        <div className="flex-1" />
        {Array.isArray(joinBoxes) && joinBoxes.length > 0 && (
          <button
            onClick={() => setShowJoinLines(v => !v)}
            title={showJoinLines ? 'Hide the green/yellow lines marking the start and end of each join box' : 'Show two vertical lines per join: start and end of the box'}
            className={`text-xs px-3 py-1.5 rounded font-medium ${
              showJoinLines ? 'bg-emerald-700 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            {showJoinLines ? 'Hide Join Lines' : 'Show Join Lines'}
          </button>
        )}
        {solidBandLines && (
          <button
            onClick={() => setShowSolidBand(v => !v)}
            title={showSolidBand
              ? 'Hide the unified solid-band lines (top + bottom of the merged thread core)'
              : 'Show two horizontal lines marking the unified solid-thread top and bottom across all threads (alignment sanity check + tube-mapping reference)'}
            className={`text-xs px-3 py-1.5 rounded font-medium ${
              showSolidBand ? 'bg-red-700 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            {showSolidBand ? '✓ Solid Band' : 'Show Solid Band'}
          </button>
        )}
        {Array.isArray(widthMarkers) && widthMarkers.length > 0 && (
          <button
            onClick={() => setShowWidths(v => !v)}
            title="Toggle thread-width markers (blue dashed verticals at 5 X-positions per thread, labelled mm + px)"
            className={`text-xs px-3 py-1.5 rounded font-medium ${
              showWidths ? 'bg-blue-700 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            {showWidths ? '✓ Widths' : 'Show Widths'}
          </button>
        )}
        <button onClick={onExport} disabled={exporting}
          title="Build non-wraparound export images (start at fragment 0's left edge, end at fragment N-1's right edge — no tile-able wraparound) plus a metadata JSON. Then download all of it."
          className="bg-amber-600 hover:bg-amber-500 disabled:bg-gray-800 disabled:text-gray-600 text-white text-xs py-1.5 px-3 rounded font-medium">
          {exporting ? 'Exporting…' : '⬇ Export'}
        </button>
        {onSaveToLibrary && (
          <button onClick={onSaveToLibrary} disabled={savingToLibrary}
            title="Save this yarn (RGBA + dimensions + band metadata) to the shared yarn library so Fabric-generator can import it as a draft material."
            className="bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-800 disabled:text-gray-600 text-white text-xs py-1.5 px-3 rounded font-medium">
            {savingToLibrary ? 'Saving…' : '＋ Save to Library'}
          </button>
        )}
        {libraryStatus?.yarnId && (
          <span className="text-xs text-emerald-300 font-mono"
            title={libraryStatus.libraryPath || ''}>
            ✓ {libraryStatus.label || libraryStatus.yarnId}
          </span>
        )}
        <button onClick={onBackToEditing}
          className="bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs py-1.5 px-3 rounded">← Back to stitching</button>
        <button onClick={onCancel}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs py-1.5 px-3 rounded">Cancel</button>
      </div>

      {error && <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-2 rounded text-sm">{error}</div>}

      {/* Action toolbar */}
      <div className="bg-gray-900 border border-gray-800 rounded p-2 flex gap-2 items-center flex-wrap">
        <button onClick={() => setShowTile(v => !v)}
          className={`text-xs px-3 py-1.5 rounded font-medium ${showTile ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'}`}>
          {showTile ? 'Single (1×)' : 'Tile Preview (3×)'}
        </button>
        <button onClick={onRegenerateAlpha} disabled={regenerating}
          className="bg-purple-700 hover:bg-purple-600 disabled:bg-gray-800 disabled:text-gray-600 text-white text-xs py-1.5 px-3 rounded font-medium">
          {regenerating ? 'Regenerating Alpha…' : (assembledAlphaDataUrl ? 'Re-Regenerate Alpha' : 'Regenerate Alpha (inpainted boxes only)')}
        </button>
        {assembledAlphaDataUrl && (
          <button onClick={() => setShowAlphaOverlay(v => !v)}
            className={`text-xs px-3 py-1.5 rounded font-medium ${showAlphaOverlay ? 'bg-cyan-700 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'}`}>
            {showAlphaOverlay ? 'Hide α Overlay' : 'Show α Overlay'}
          </button>
        )}
        <a download="assembled_rgb.png" href={assembledDataUrl}
          className="text-xs px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300">Download RGB</a>
        {assembledAlphaDataUrl && (
          <a download="assembled_alpha.png" href={assembledAlphaDataUrl}
            className="text-xs px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300">Download α</a>
        )}
        {assembledRgbaDataUrl && (
          <a download="assembled_rgba.png" href={assembledRgbaDataUrl}
            className="text-xs px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white font-medium">Download RGBA (no bg)</a>
        )}
        <button onClick={onDownloadMetadata}
          title="Download just the export_metadata.json (DPI, width, length, joins config)"
          className="text-xs px-3 py-1.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 font-medium">
          Download Metadata
        </button>
        {assembledRgbaDataUrl && (
          <span className="flex items-center gap-1 text-xs text-gray-400">
            <span>Custom bg:</span>
            <input type="color" defaultValue="#0a2882"
              id="custom-bg-picker"
              className="w-7 h-7 rounded border border-gray-700 bg-gray-800 cursor-pointer p-0"
              title="Pick a background colour" />
            <button
              onClick={() => {
                const inp = document.getElementById('custom-bg-picker');
                onDownloadCustomBg(inp?.value || '#0a2882');
              }}
              title="Composite the thread onto the picked colour and download as PNG"
              className="text-xs px-2 py-1 rounded bg-indigo-700 hover:bg-indigo-600 text-white font-medium">
              Download
            </button>
          </span>
        )}
        <div className="flex-1" />
        <button onClick={onUseAsWorkingImage}
          className="bg-green-600 hover:bg-green-500 text-white font-medium text-sm py-1.5 px-4 rounded">
          Use as Working Image →
        </button>
      </div>

      {debugDir && (
        <div className="bg-gray-900 border border-gray-800 rounded px-3 py-2 text-xs text-gray-400 font-mono truncate" title={debugDir}>
          Debug folder: {debugDir}
        </div>
      )}

      {/* Three result panels: RGB, α matte, dark-blue composite — all
          rendered through ResultCanvas at the same scale + the same overlays. */}
      <div className="flex flex-col gap-3">
        <div>
          <div className="text-[11px] text-gray-400 mb-1 font-medium">1. Assembled RGB (full yarn)</div>
          <ResultCanvas
            src={assembledDataUrl}
            alphaSrc={assembledAlphaDataUrl}
            onDims={setImgDims}
            showAlphaOverlay={showAlphaOverlay}
            showTile={showTile}
            showJoinLines={showJoinLines} joinBoxes={joinBoxes}
            showSolidBand={showSolidBand} solidBandLines={solidBandLines}
            showWidths={showWidths} widthMarkers={widthMarkers}
            maxHeight={320}
          />
          <p className="text-[11px] text-gray-500 mt-1">
            {showTile
              ? 'Tiled 2× — red dashed line = tile seam. If invisible, the wraparound is seamless.'
              : 'The full assembled thread. Tile Preview verifies the wraparound.'}
          </p>
        </div>

        <div>
          <div className="text-[11px] text-gray-400 mb-1 font-medium">2. Assembled α matte</div>
          {assembledAlphaDataUrl ? (
            <ResultCanvas
              src={assembledAlphaDataUrl}
              showJoinLines={showJoinLines} joinBoxes={joinBoxes}
              showSolidBand={showSolidBand} solidBandLines={solidBandLines}
              showWidths={showWidths} widthMarkers={widthMarkers}
              maxHeight={320}
            />
          ) : (
            <div className="rounded border border-gray-800 bg-gray-900 p-6 text-center text-xs text-gray-500">
              {regenerating ? 'Generating…' : 'Not yet computed — click "Regenerate Alpha" above.'}
            </div>
          )}
        </div>

        <div>
          <div className="text-[11px] text-gray-400 mb-1 font-medium">3. Yarn composited on dark blue (sRGB 10, 40, 130)</div>
          {assembledDarkBlueDataUrl ? (
            <ResultCanvas
              src={assembledDarkBlueDataUrl}
              showJoinLines={showJoinLines} joinBoxes={joinBoxes}
              showSolidBand={showSolidBand} solidBandLines={solidBandLines}
              showWidths={showWidths} widthMarkers={widthMarkers}
              maxHeight={320}
            />
          ) : (
            <div className="rounded border border-gray-800 bg-gray-900 p-6 text-center text-xs text-gray-500">
              {regenerating ? 'Generating…' : 'Not yet computed — generates with the alpha.'}
            </div>
          )}
        </div>
      </div>

      {/* Dimensions summary — width (top-bottom of solid band) + length (left-right of assembled) */}
      {(() => {
        const widthPx = solidBandLines && Number.isFinite(solidBandLines.top_y) && Number.isFinite(solidBandLines.bottom_y)
          ? (solidBandLines.bottom_y - solidBandLines.top_y + 1) : null;
        const lengthPx = imgDims?.w || null;
        const d = dpi || 1600;
        const fmtMm = (px) => px == null ? '—' : `${(px / d * 25.4).toFixed(2)} mm`;
        return (
          <div className="rounded border border-gray-700 bg-gray-900 p-3 text-sm">
            <div className="text-xs text-gray-400 mb-2 font-medium">Thread dimensions ({d} dpi)</div>
            <div className="grid grid-cols-2 gap-3 max-w-md">
              <div className="bg-gray-950/60 border border-gray-800 rounded px-3 py-2">
                <div className="text-[11px] text-gray-500">Width (top ↔ bottom of solid band)</div>
                <div className="text-gray-100 font-mono">
                  {widthPx != null ? `${widthPx} px` : '—'}
                  <span className="ml-2 text-blue-300">{fmtMm(widthPx)}</span>
                </div>
              </div>
              <div className="bg-gray-950/60 border border-gray-800 rounded px-3 py-2">
                <div className="text-[11px] text-gray-500">Length (left ↔ right of thread)</div>
                <div className="text-gray-100 font-mono">
                  {lengthPx != null ? `${lengthPx} px` : '—'}
                  <span className="ml-2 text-blue-300">{fmtMm(lengthPx)}</span>
                </div>
              </div>
            </div>
          </div>
        );
      })()}
    </main>
  );
}

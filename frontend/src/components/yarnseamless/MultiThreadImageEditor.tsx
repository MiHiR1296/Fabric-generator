// @ts-nocheck — faithful port of yarnseamless JSX. TypeScript checking off in this file;
//                 the source is preserved byte-for-byte (Phase 2c, putting-it-together/phase_log.md).
//                 Re-enable per-file as we type things up in Phase 2e or beyond.
import { useEffect, useRef, useState, useCallback } from 'react';

/**
 * Multi-Thread Image editor.
 *
 * Three sub-views:
 *   1. 'upload'    — pick one scan that contains multiple parallel threads + n_threads
 *   2. 'processing' — backend pipeline running (~30s for large scans)
 *   3. 'review'    — per-thread leveled image with the two red C-band lines drawn
 *                    client-side at full original resolution (lossless PNG, no compression).
 *                    Click 'Next →' to hand the leveled images off as fragments.
 *
 * Quality preservation: we never resize or transcode any image. Uploads are sent as-is
 * (data URI), output PNGs are streamed verbatim from the server, and the canvas displays
 * them at native resolution (CSS scaling only, the underlying pixel data is intact).
 */
// Persisted-state key. We only stash the SMALL summary JSON (5–20 KB) plus
// view/nThreads — the data URI is never persisted. The server-side files
// stay on disk between page loads, so the URLs in summary still resolve.
const SS_KEY = 'mti_state_v1';
function readPersisted() {
  try {
    const raw = sessionStorage.getItem(SS_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch { return null; }
}
function writePersisted(obj) {
  try { sessionStorage.setItem(SS_KEY, JSON.stringify(obj)); } catch {}
}
function clearPersisted() {
  try { sessionStorage.removeItem(SS_KEY); } catch {}
}

export default function MultiThreadImageEditor({ onAssembleDone, onCancel }) {
  const persisted = useRef(readPersisted()).current;
  const [view, setView] = useState(() => persisted?.view || 'upload'); // 'upload' | 'processing' | 'review'
  // null = auto-detect (default); a number forces that count.
  const [nThreads, setNThreads] = useState(() => (persisted?.nThreads ?? null));
  const [dpi, setDpi] = useState(() => persisted?.dpi || 1600);
  const [showWidths, setShowWidths] = useState(false);
  const [showBboxes, setShowBboxes] = useState(false);
  // Server-side upload: client only holds a small thumbnail + an upload_id.
  // The original (possibly 250 MB TIFF) lives on the server in debug/uploads/.
  const [uploadThumbUrl, setUploadThumbUrl] = useState(null);
  const [uploadId, setUploadId] = useState(null);
  const [uploadName, setUploadName] = useState(null);
  // Optional second scan on a different colour card → enables dual-scan matting.
  const [upload2ThumbUrl, setUpload2ThumbUrl] = useState(null);
  const [upload2Id, setUpload2Id] = useState(null);
  const [upload2Name, setUpload2Name] = useState(null);
  const [error, setError] = useState(null);
  const [progressMessage, setProgressMessage] = useState('');
  const [summary, setSummary] = useState(() => persisted?.summary || null); // server response
  const [bandSource, setBandSource] = useState(() => persisted?.bandSource || 'c'); // 'c' | 'd' | 'none'
  const fileInputRef = useRef(null);
  const fileInput2Ref = useRef(null);

  // Keep sessionStorage in sync with the bits worth restoring after a
  // tab discard / reload. Don't include data URIs.
  useEffect(() => {
    if (view === 'review' && summary) {
      writePersisted({ view, nThreads, dpi, summary, bandSource });
    } else if (view === 'upload' && !summary) {
      clearPersisted();
    }
  }, [view, summary, nThreads, dpi, bandSource]);

  async function uploadAndThumbnail(file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch('/api/multithread/upload', { method: 'POST', body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `Upload failed (${r.status})`);
    return data; // { upload_id, ext, width, height, thumbnail_data_url, size_bytes }
  }

  async function handleFile(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploadName(file.name);
    setError(null);
    setSummary(null);
    clearPersisted();
    setProgressMessage('Uploading & generating preview…');
    try {
      const d = await uploadAndThumbnail(file);
      setUploadId(d.upload_id);
      setUploadThumbUrl(d.thumbnail_data_url);
    } catch (err) {
      setError(err.message);
    } finally {
      setProgressMessage('');
    }
  }

  async function handleFile2(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUpload2Name(file.name);
    setError(null);
    setProgressMessage('Uploading 2nd scan & generating preview…');
    try {
      const d = await uploadAndThumbnail(file);
      setUpload2Id(d.upload_id);
      setUpload2ThumbUrl(d.thumbnail_data_url);
    } catch (err) {
      setError(err.message);
    } finally {
      setProgressMessage('');
    }
  }

  function clearSecondImage() {
    setUpload2ThumbUrl(null);
    setUpload2Id(null);
    setUpload2Name(null);
  }

  async function runProcessing() {
    if (!uploadId) { setError('Pick a scan first'); return; }
    if (nThreads != null && (nThreads < 2 || nThreads > 16)) {
      setError('Thread count must be 2–16 (or blank for auto-detect)'); return;
    }
    setError(null);
    setView('processing');
    const dual = !!upload2Id;
    const countLabel = nThreads ? `${nThreads}` : 'auto-detected';
    setProgressMessage(dual
      ? `Splitting both scans into ${countLabel} threads (dual-scan matting)…`
      : `Splitting scan into ${countLabel} threads…`);
    try {
      const body = { upload_id: uploadId, n_threads: nThreads || 'auto', dpi: Number(dpi) };
      if (upload2Id) body.upload_id2 = upload2Id;
      const r = await fetch('/api/multithread/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || `Server error ${r.status}`);
      setSummary(data);
      // If approach C failed for any thread, default to D (band-source toggle)
      const anyC_missing = (data.threads || []).some(t => t.c_band?.top_y < 0);
      setBandSource(anyC_missing ? 'd' : 'c');
      setView('review');
      // Drop the thumbnail/upload-id references; the server's session_id
      // is the new handle for everything downstream.
      setUploadThumbUrl(null);
      setUpload2ThumbUrl(null);
      setUploadId(null);
      setUpload2Id(null);
    } catch (err) {
      setError(err.message);
      setView('upload');
    } finally {
      setProgressMessage('');
    }
  }

  function chosenBand(thread) {
    if (bandSource === 'd') return thread.d_band;
    if (bandSource === 'none') return null;
    // 'c' with auto-fallback to D if C failed
    if (thread.c_band?.top_y >= 0) return thread.c_band;
    return thread.d_band;
  }

  async function handleNext() {
    if (!summary) return;
    setError(null);
    setView('processing');
    setProgressMessage('Loading leveled threads…');
    try {
      // Fetch each leveled image as a Blob → data URL (preserves bytes exactly).
      // We also pass each thread's chosen band Y range so downstream can pre-align.
      const fragments = [];
      for (const t of summary.threads) {
        const url = t.urls.leveled;
        const resp = await fetch(url);
        if (!resp.ok) throw new Error(`Failed to load thread ${t.index}: ${resp.status}`);
        const blob = await resp.blob();
        const dataUrl = await blobToDataUrl(blob);
        const dims = await imageDims(dataUrl);
        const band = chosenBand(t);
        fragments.push({
          id: `mti_${summary.session_id}_${t.index}`,
          name: `thread_${t.index}.png`,
          dataUrl,
          w: dims.w, h: dims.h,
          yOffset: 0,                    // hand-off pre-aligns via yOffset below
          // metadata we keep around in case the receiving editor wants it
          mtiBand: band ? { top_y: band.top_y, bottom_y: band.bottom_y } : null,
          mtiAlphaUrl: t.urls?.alpha || null,
          mtiSessionId: summary.session_id,
          mtiThreadIndex: t.index,
          mtiWidthSamples: Array.isArray(t.width_samples) ? t.width_samples : [],
          mtiDpi: summary.dpi || 1600,
        });
      }
      // Pre-align by C-band center: shift each fragment so all band-centers line up at canvas center
      const centers = fragments.map(f => f.mtiBand ? (f.mtiBand.top_y + f.mtiBand.bottom_y) / 2 : f.h / 2);
      const targetCenter = centers.reduce((a, b) => a + b, 0) / centers.length;
      fragments.forEach((f, i) => {
        const fragmentCenterIfPlacedNeutral = f.h / 2;       // where center sits when yOffset=0 in unified canvas
        const desiredFragmentCenter = targetCenter;          // align all band centers to this row
        const requiredBandCenter = centers[i];               // band center within fragment-local coords
        // unifiedY of band = (totalH-h)/2 + yOffset + requiredBandCenter
        // We want this to equal a fixed value across all fragments.
        // Equivalent condition: (h/2 - requiredBandCenter) + yOffset is the same for all
        //                  →  yOffset_i = (h_i/2 - requiredBandCenter_i) + const
        // Simpler: pick yOffset so that the band-center within the fragment lands at the SAME
        // unified Y for every fragment. Use frag 0 as anchor.
        // f.yOffset = (anchor_band_center_after_centering) - (this_fragment_band_center_after_centering)
        const ownDelta = (f.h / 2) - requiredBandCenter;     // shift needed to bring band to fragment center
        f.yOffset = Math.round(ownDelta);
        // Note: yOffsets are clamped to ±300 by the multi-fragment editor; we'll cap.
        if (f.yOffset > 300) f.yOffset = 300;
        if (f.yOffset < -300) f.yOffset = -300;
      });
      onAssembleDone(fragments);
    } catch (err) {
      setError(err.message);
      setView('review');
    } finally {
      setProgressMessage('');
    }
  }

  return (
    <main className="flex-1 flex flex-col p-4 bg-gray-950 gap-3 overflow-auto">
      <div className="flex items-center gap-3 flex-wrap">
        <h2 className="text-white text-base font-medium">Multi-Thread Image</h2>
        <span className="text-xs text-gray-400">
          {view === 'upload' && 'Upload one scan with multiple parallel threads'}
          {view === 'processing' && (progressMessage || 'Working…')}
          {view === 'review' && `${summary?.threads?.length ?? 0} threads detected — review then click Next`}
        </span>
        <div className="flex-1" />
        {view === 'review' && (
          <button
            onClick={() => { setSummary(null); clearPersisted(); setView('upload'); }}
            disabled={view === 'processing'}
            className="bg-gray-700 hover:bg-gray-600 text-gray-200 text-xs py-1.5 px-3 rounded">← Back to upload</button>
        )}
        <button onClick={onCancel} disabled={view === 'processing'}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs py-1.5 px-3 rounded disabled:opacity-50">Cancel</button>
      </div>

      {error && <div className="bg-red-900/50 border border-red-700 text-red-200 px-4 py-2 rounded text-sm">{error}</div>}

      {view === 'upload' && (
        <UploadView
          fileInputRef={fileInputRef}
          fileInput2Ref={fileInput2Ref}
          uploadThumbUrl={uploadThumbUrl}
          uploadName={uploadName}
          upload2ThumbUrl={upload2ThumbUrl}
          upload2Name={upload2Name}
          nThreads={nThreads}
          setNThreads={setNThreads}
          dpi={dpi}
          setDpi={setDpi}
          onPick={() => fileInputRef.current?.click()}
          onPick2={() => fileInput2Ref.current?.click()}
          onClear2={clearSecondImage}
          onFileChange={handleFile}
          onFile2Change={handleFile2}
          onProcess={runProcessing}
        />
      )}

      {view === 'processing' && (
        <div className="rounded border border-gray-800 bg-gray-900 p-12 text-center">
          <div className="inline-flex items-center gap-3 text-gray-300">
            <svg className="animate-spin h-5 w-5 text-blue-300" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm">{progressMessage || 'Working…'}</span>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            This can take ~30 seconds for very large scans (3300×17000+).
          </p>
        </div>
      )}

      {view === 'review' && summary && (
        <>
          <ReviewView
            summary={summary}
            bandSource={bandSource} setBandSource={setBandSource}
            chosenBand={chosenBand}
            showWidths={showWidths} setShowWidths={setShowWidths}
            showBboxes={showBboxes} setShowBboxes={setShowBboxes}
          />
          <div className="flex justify-end gap-2 mt-2 sticky bottom-0 bg-gray-950 py-3 border-t border-gray-800">
            <span className="text-xs text-gray-500 self-center">
              {summary.threads?.length} threads ready — Next sends them as fragments to the seamless stitcher
            </span>
            <button onClick={handleNext}
              className="bg-green-600 hover:bg-green-500 text-white font-medium text-sm py-2 px-6 rounded">
              Next →
            </button>
          </div>
        </>
      )}
    </main>
  );
}

function UploadView({
  fileInputRef, fileInput2Ref,
  uploadThumbUrl, uploadName, upload2ThumbUrl, upload2Name,
  nThreads, setNThreads,
  dpi, setDpi,
  onPick, onPick2, onClear2,
  onFileChange, onFile2Change, onProcess,
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
      <div className="bg-gray-900 border border-gray-800 rounded p-4 flex flex-col gap-3">
        <p className="text-xs text-gray-400">
          Upload one scan with multiple yarn threads laid parallel.
          The pipeline splits, levels, and detects each thread's solid band, then computes alpha.
        </p>

        {/* Primary scan */}
        <div className="flex gap-2 items-center">
          <button onClick={onPick}
            className="bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium py-2 px-4 rounded">
            {uploadThumbUrl ? 'Choose Different Scan' : 'Choose Scan…'}
          </button>
          <span className="text-xs text-gray-400 truncate">{uploadName || 'No file selected'}</span>
        </div>
        <input ref={fileInputRef} type="file" accept="image/*" onChange={onFileChange} className="hidden" />

        {/* Optional second scan */}
        <div className="border-t border-gray-800 pt-3 flex flex-col gap-2">
          <p className="text-xs text-gray-400">
            <span className="text-gray-300 font-medium">Optional:</span> a second scan of the same yarn on a
            <span className="text-gray-300"> different colour card</span> (e.g. cyan). When provided, the matter
            uses both scans simultaneously — recovers more wispy fibre and removes colour bleed.
          </p>
          <div className="flex gap-2 items-center">
            <button onClick={onPick2}
              className="bg-purple-700 hover:bg-purple-600 text-white text-sm font-medium py-2 px-4 rounded">
              {upload2ThumbUrl ? 'Choose Different 2nd Scan' : 'Choose 2nd Scan… (optional)'}
            </button>
            <span className="text-xs text-gray-400 truncate flex-1">{upload2Name || 'No second scan'}</span>
            {upload2ThumbUrl && (
              <button onClick={onClear2}
                className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs py-1 px-2 rounded">
                Clear
              </button>
            )}
          </div>
          <input ref={fileInput2Ref} type="file" accept="image/*" onChange={onFile2Change} className="hidden" />
        </div>

        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-300">Thread count:</label>
          <input
            type="number" min={2} max={16}
            value={nThreads ?? ''}
            placeholder="auto"
            onChange={e => {
              const v = e.target.value.trim();
              if (v === '') { setNThreads(null); return; }
              const n = parseInt(v);
              setNThreads(Number.isFinite(n) && n > 0 ? n : null);
            }}
            className="w-20 bg-gray-800 text-gray-200 text-sm py-1 px-2 rounded border border-gray-700 focus:border-blue-500 focus:outline-none placeholder-gray-500"
          />
          <span className="text-xs text-gray-500">
            {nThreads ? '(2–16; blank = auto)' : 'auto-detect (override 2–16)'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-300">Scanner DPI:</label>
          <input
            type="number" min={50} max={12800} step={1}
            value={dpi}
            onChange={e => setDpi(parseInt(e.target.value) || 0)}
            className="w-24 bg-gray-800 text-gray-200 text-sm py-1 px-2 rounded border border-gray-700 focus:border-blue-500 focus:outline-none"
          />
          <span className="text-xs text-gray-500">(default 1600 — Epson V850)</span>
        </div>
        <button onClick={onProcess} disabled={!uploadThumbUrl}
          className="bg-green-600 hover:bg-green-500 disabled:bg-gray-800 disabled:text-gray-600 text-white font-medium py-2 px-5 rounded">
          {upload2ThumbUrl ? 'Process Both Scans (dual-bg)' : 'Process Scan'}
        </button>
      </div>
      <div className="bg-gray-900 border border-gray-800 rounded p-2 min-h-[300px] flex flex-col items-center justify-center gap-2">
        {uploadThumbUrl ? (
          <>
            <img src={uploadThumbUrl} alt="upload preview" className="max-h-[300px] w-auto object-contain rounded" />
            <span className="text-[11px] text-gray-500">Primary scan (preview)</span>
          </>
        ) : (
          <p className="text-gray-500 text-sm">Preview will show here</p>
        )}
        {upload2ThumbUrl && (
          <>
            <img src={upload2ThumbUrl} alt="2nd upload preview" className="max-h-[180px] w-auto object-contain rounded border border-purple-900" />
            <span className="text-[11px] text-purple-400">Second scan (preview)</span>
          </>
        )}
      </div>
    </div>
  );
}

function ReviewView({ summary, bandSource, setBandSource, chosenBand, showWidths, setShowWidths, showBboxes, setShowBboxes }) {
  const dual = !!summary.two_image;
  return (
    <div className="flex flex-col gap-3">
      {/* Top toolbar: stats + band selector */}
      <div className="bg-gray-900 border border-gray-800 rounded px-3 py-2 flex items-center gap-3 flex-wrap">
        <span className="text-xs text-gray-400">
          Original {summary.input_size?.[0]}×{summary.input_size?.[1]} — {summary.threads?.length} threads
          {summary.elapsed_seconds ? ` in ${summary.elapsed_seconds}s` : ''}
          {summary.dpi && (
            <span className="ml-2 text-gray-500">@ {summary.dpi} dpi</span>
          )}
          {dual && (
            <span className="ml-2 text-purple-400">
              · dual-scan
              {summary.registration_shift_xy_px && (
                <span className="text-gray-500 font-mono">
                  &nbsp;(shift {summary.registration_shift_xy_px[0]}, {summary.registration_shift_xy_px[1]} px)
                </span>
              )}
            </span>
          )}
        </span>
        <div className="flex-1" />
        <button
          onClick={() => setShowWidths(v => !v)}
          className={`text-xs py-1 px-3 rounded border ${showWidths
            ? 'bg-red-700 border-red-600 text-white'
            : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700'}`}
        >
          {showWidths ? '✓ Show widths (mm)' : 'Show widths (mm)'}
        </button>
        <button
          onClick={() => setShowBboxes(v => !v)}
          title="Show detected thread bounding boxes on the original scan — useful when auto-detect picks the wrong number of threads."
          className={`text-xs py-1 px-3 rounded border ${showBboxes
            ? 'bg-cyan-700 border-cyan-600 text-white'
            : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700'}`}
        >
          {showBboxes ? '✓ Show bboxes' : 'Show bboxes'}
        </button>
        <label className="text-xs text-gray-400">Solid-band lines:</label>
        <select
          value={bandSource}
          onChange={e => setBandSource(e.target.value)}
          className="bg-gray-800 text-gray-200 text-xs py-1 px-2 rounded border border-gray-700"
        >
          <option value="c">Approach C (strict)</option>
          <option value="d">Approach D (smoothed)</option>
          <option value="none">Hide lines</option>
        </select>
      </div>

      {/* Detection-overlay preview: shows where the pipeline thinks each
          thread is on the *original* scan. Toggle it when the per-thread
          count looks wrong. */}
      {showBboxes && summary.urls?.detection_overlay && (
        <div className="bg-gray-900 border border-cyan-800 rounded p-2 flex flex-col gap-1">
          <div className="text-xs text-cyan-300">
            Detection on original scan — {summary.threads?.length} bounding boxes (the strips fed into the pipeline).
            Auto-detect counted these as the threads.
          </div>
          <img src={summary.urls.detection_overlay} alt="detection overlay"
            className="w-full h-auto rounded border border-cyan-900" />
        </div>
      )}

      {/* Per-thread review */}
      <div className="flex flex-col gap-3">
        {summary.threads.map(t => (
          <ThreadReviewRow key={t.index} thread={t} band={chosenBand(t)} showWidths={showWidths} />
        ))}
      </div>
    </div>
  );
}

function ThreadReviewRow({ thread, band, showWidths }) {
  const leveledRef = useRef(null);
  const alphaRef = useRef(null);
  const [imgSize, setImgSize] = useState(null);

  // Draw leveled RGB with the two band lines + (optional) per-sample width
  // markers (vertical red lines spanning the solid band, with mm labels).
  useEffect(() => {
    const cv = leveledRef.current;
    if (!cv) return;
    let cancelled = false;
    const im = new Image();
    im.crossOrigin = 'anonymous';
    im.onload = () => {
      if (cancelled) return;
      cv.width = im.width;
      cv.height = im.height;
      const ctx = cv.getContext('2d');
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(im, 0, 0);
      if (band && band.top_y >= 0 && band.bottom_y >= 0) {
        const thickness = Math.max(3, Math.round(im.height * 0.012));
        const dashLen   = 10;   // 10 px ON, 10 px OFF (period 20)
        // Phase 3g — draw 4 lines: 2 red (core c_band) + 2 amber (outer fibre
        // extents). The amber lines are the same data the producer uses for
        // Arc 2 V Min/Max (strand silhouette), so you can sanity-check the
        // values that go to Blender before saving.
        const linesToDraw = [
          { y: band.top_y,        color: 'rgba(255, 0, 0, 1)' },
          { y: band.bottom_y,     color: 'rgba(255, 0, 0, 1)' },
        ];
        if (typeof band.fiber_top_y === 'number'
            && band.fiber_top_y >= 0
            && band.fiber_top_y !== band.top_y) {
          linesToDraw.push({ y: band.fiber_top_y, color: 'rgba(255, 176, 0, 1)' });
        }
        if (typeof band.fiber_bot_y === 'number'
            && band.fiber_bot_y >= 0
            && band.fiber_bot_y !== band.bottom_y) {
          linesToDraw.push({ y: band.fiber_bot_y, color: 'rgba(255, 176, 0, 1)' });
        }
        for (const { y: yLogical, color } of linesToDraw) {
          ctx.fillStyle = color;
          const y = Math.round(yLogical) - Math.floor(thickness / 2);
          for (let xx = 0; xx < im.width; xx += dashLen * 2) {
            const segW = Math.min(dashLen, im.width - xx);
            if (segW <= 0) break;
            ctx.fillRect(xx, y, segW, thickness);
          }
        }
      }
      // Width samples: vertical BLUE DASHED lines spanning ONLY from the
      // measured solid top to bottom (constrained within the c_band on the
      // backend). Label shows mm and pixels.
      if (showWidths && Array.isArray(thread.width_samples) && thread.width_samples.length) {
        const lineW = Math.max(3, Math.round(im.width * 0.0015));
        const dashLen = 5;   // 5 px ON, 5 px OFF (period 10) — vertical width marker
        const fontPx = Math.max(28, Math.round(im.height * 0.13));
        ctx.font = `bold ${fontPx}px ui-sans-serif, system-ui, sans-serif`;
        ctx.textBaseline = 'bottom';
        ctx.textAlign = 'center';
        for (const s of thread.width_samples) {
          const x = Math.round(s.x);
          const y0 = Math.round(s.top_y);
          const y1 = Math.round(s.bottom_y);
          // Blue dashed line, drawn as filled segments so dash thickness
          // reads cleanly on a downscaled-display canvas.
          ctx.fillStyle = 'rgba(59, 130, 246, 1)';   // blue-500
          for (let yy = y0; yy <= y1; yy += dashLen * 2) {
            const segH = Math.min(dashLen, y1 - yy + 1);
            if (segH <= 0) break;
            ctx.fillRect(x - Math.floor(lineW / 2), yy, lineW, segH);
          }
          // Label: e.g. "1.02 mm · 642 px"
          const label = `${s.width_mm.toFixed(2)} mm · ${s.width_px} px`;
          const padX = Math.round(fontPx * 0.3);
          const padY = Math.round(fontPx * 0.18);
          const tw = ctx.measureText(label).width;
          let labelY = y0 - Math.round(fontPx * 0.4);
          if (labelY - fontPx < 0) labelY = y1 + fontPx + Math.round(fontPx * 0.4);
          ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
          ctx.fillRect(
            x - tw / 2 - padX, labelY - fontPx - padY,
            tw + padX * 2,    fontPx + padY * 2);
          ctx.fillStyle = 'rgba(147, 197, 253, 1)';   // blue-300 — readable on dark bg
          ctx.fillText(label, x, labelY);
        }
      }
      setImgSize({ w: im.width, h: im.height });
    };
    im.src = thread.urls.leveled;
    return () => { cancelled = true; };
  }, [thread.urls.leveled, band?.top_y, band?.bottom_y,
       band?.fiber_top_y, band?.fiber_bot_y, showWidths,
       thread.width_samples?.length]);

  // Draw the alpha matte as a separate canvas underneath.
  useEffect(() => {
    const cv = alphaRef.current;
    if (!cv || !thread.urls.alpha) return;
    let cancelled = false;
    const im = new Image();
    im.crossOrigin = 'anonymous';
    im.onload = () => {
      if (cancelled) return;
      cv.width = im.width;
      cv.height = im.height;
      const ctx = cv.getContext('2d');
      ctx.imageSmoothingEnabled = false;
      // Black background so transparent areas render as black (alpha=0) and
      // the matte luminance reads correctly.
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, cv.width, cv.height);
      ctx.drawImage(im, 0, 0);
    };
    im.src = thread.urls.alpha;
    return () => { cancelled = true; };
  }, [thread.urls.alpha]);

  const heightLabel = band && band.bottom_y >= 0 ? `${band.bottom_y - band.top_y}px` : '—';
  const fiberLabel = (() => {
    if (!band) return null;
    const tH = (typeof band.fiber_top_y === 'number' && band.fiber_top_y >= 0)
      ? Math.max(0, band.top_y - band.fiber_top_y) : null;
    const bH = (typeof band.fiber_bot_y === 'number' && band.fiber_bot_y >= 0)
      ? Math.max(0, band.fiber_bot_y - band.bottom_y) : null;
    if (tH == null && bH == null) return null;
    return `halo top ${tH ?? '—'}px · bot ${bH ?? '—'}px`;
  })();
  const lowConfidence = !band || band.top_y < 0;
  const tt = thread.timings;

  return (
    <div className={`bg-gray-900 border rounded p-3 ${lowConfidence ? 'border-yellow-700' : 'border-gray-800'}`}>
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <span className="bg-blue-700 text-white font-bold rounded-full w-7 h-7 flex items-center justify-center text-sm">
          {thread.index + 1}
        </span>
        <span className="text-sm text-gray-200 font-medium">Thread {thread.index}</span>
        <span className="text-xs text-gray-500 font-mono">
          leveled {thread.leveled_size?.[0]}×{thread.leveled_size?.[1]}
        </span>
        <span className="text-xs text-gray-500">tilt {thread.tilt_angle_deg?.toFixed(2)}°</span>
        <span className="text-xs text-gray-500">band height {heightLabel}</span>
        {fiberLabel && (
          <span className="text-xs text-amber-400/80">{fiberLabel}</span>
        )}
        {tt && (
          <span className="text-[11px] text-gray-500 font-mono ml-auto">
            ⏱ total {tt.total}s (alpha {tt.alpha_run}s · level {tt.preprocess_level}s · band {tt.band_detect}s)
          </span>
        )}
        {lowConfidence && (
          <span className="text-xs text-yellow-300">low confidence — review carefully</span>
        )}
      </div>
      <div className="flex flex-col gap-2">
        <div>
          <div className="text-[11px] text-gray-500 mb-1">Leveled RGB</div>
          <div className="overflow-auto rounded border border-gray-800 bg-black">
            <canvas
              ref={leveledRef}
              className="block max-h-[200px] w-auto"
              style={{ imageRendering: 'pixelated' }}
            />
          </div>
        </div>
        {thread.urls.alpha && (
          <div>
            <div className="text-[11px] text-gray-500 mb-1">Alpha matte (achromatic-F closed-form)</div>
            <div className="overflow-auto rounded border border-gray-800 bg-black">
              <canvas
                ref={alphaRef}
                className="block max-h-[200px] w-auto"
                style={{ imageRendering: 'pixelated' }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Helpers
function blobToDataUrl(blob) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(r.result);
    r.onerror = rej;
    r.readAsDataURL(blob);
  });
}
function imageDims(dataUrl) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.onload = () => res({ w: im.width, h: im.height });
    im.onerror = rej;
    im.src = dataUrl;
  });
}

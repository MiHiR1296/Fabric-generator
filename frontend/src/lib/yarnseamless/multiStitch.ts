// @ts-nocheck — faithful port of yarnseamless JSX. TypeScript checking off in this file;
//                 the source is preserved byte-for-byte (Phase 2c, putting-it-together/phase_log.md).
//                 Re-enable per-file as we type things up in Phase 2e or beyond.
// Multi-fragment stitching helpers.
// Each fragment is { id, dataUrl, name, w, h, yOffset } — yOffset shifts the fragment
// vertically inside the join canvas (positive = move down, negative = move up).

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = url;
  });
}

/**
 * Build the canvas for one join (right strip of left frag + gap + left strip of right frag),
 * with vertical Y offsets applied per fragment. Returns the join image, the auto mask, and
 * the size metadata needed for re-painting the canvas with a custom mask.
 *
 * The canvas height is the max fragment height. Y offsets translate each strip up/down inside
 * that canvas; pixels not covered by either strip are black so LaMa fills them naturally.
 */
export async function buildJoinCanvas({
  leftFrag, rightFrag,
  leftYOffset = 0, rightYOffset = 0,
  stripL = 256, stripR = 256, gap = 200,
}) {
  const [leftImg, rightImg] = await Promise.all([loadImage(leftFrag.dataUrl), loadImage(rightFrag.dataUrl)]);
  const Hl = leftImg.height, Wl = leftImg.width;
  const Hr = rightImg.height, Wr = rightImg.width;

  const sL = Math.min(stripL, Wl);
  const sR = Math.min(stripR, Wr);
  const canvasW = sL + gap + sR;
  const canvasH = Math.max(Hl, Hr);

  // Image canvas: black background; draw left strip then right strip with vertical offsets
  const cv = document.createElement('canvas');
  cv.width = canvasW;
  cv.height = canvasH;
  const ctx = cv.getContext('2d');
  ctx.fillStyle = 'black';
  ctx.fillRect(0, 0, canvasW, canvasH);

  // Center each fragment vertically by default, then apply user offset
  const leftY = Math.round((canvasH - Hl) / 2) + leftYOffset;
  const rightY = Math.round((canvasH - Hr) / 2) + rightYOffset;

  // Left strip: source rect (Wl - sL, 0, sL, Hl) → dest (0, leftY, sL, Hl)
  ctx.drawImage(leftImg, Wl - sL, 0, sL, Hl, 0, leftY, sL, Hl);
  // Right strip: source rect (0, 0, sR, Hr) → dest (sL + gap, rightY, sR, Hr)
  ctx.drawImage(rightImg, 0, 0, sR, Hr, sL + gap, rightY, sR, Hr);

  // Auto mask: white over the gap region, black elsewhere
  // Also auto-mask the black uncovered zones (above/below each strip from the Y offset)
  const mask = document.createElement('canvas');
  mask.width = canvasW;
  mask.height = canvasH;
  const mctx = mask.getContext('2d');
  mctx.fillStyle = 'black';
  mctx.fillRect(0, 0, canvasW, canvasH);
  mctx.fillStyle = 'white';
  // Gap (full height)
  mctx.fillRect(sL, 0, gap, canvasH);
  // Strips' uncovered top/bottom bands (caused by yOffset shifting the strip out of the way)
  if (leftY > 0) mctx.fillRect(0, 0, sL, leftY);
  if (leftY + Hl < canvasH) mctx.fillRect(0, leftY + Hl, sL, canvasH - (leftY + Hl));
  if (rightY > 0) mctx.fillRect(sL + gap, 0, sR, rightY);
  if (rightY + Hr < canvasH) mctx.fillRect(sL + gap, rightY + Hr, sR, canvasH - (rightY + Hr));

  return {
    canvasW, canvasH,
    canvasDataUrl: cv.toDataURL('image/png'),
    autoMaskDataUrl: mask.toDataURL('image/png'),
    stripL: sL, stripR: sR, gap,
  };
}

/**
 * Inpaint a join canvas via the local LaMa server.
 * Returns the inpainted result data URL.
 */
export async function inpaintJoin({ canvasDataUrl, maskDataUrl }) {
  const resp = await fetch('/api/lama/inpaint', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: canvasDataUrl, mask: maskDataUrl }),
  });
  const data = await resp.json();
  if (!resp.ok || data.error) throw new Error(data.error || `Inpaint failed (${resp.status})`);
  return data.image;
}

/**
 * Assemble the final tileable image from N fragments and N inpainted joins.
 *
 * For fragment j (0..N-1) cyclically:
 *   interior_j = frag_j[stripL : W_j - stripR]
 *   inp_j is the inpainted result for the join (frag_j → frag_{(j+1) mod N})
 *
 * Final image (left-to-right):
 *   interior_0 ⊕ inp_0 ⊕ interior_1 ⊕ inp_1 ⊕ ... ⊕ interior_{N-1} ⊕ inp_{N-1}
 *
 * Each inp_j has width stripL + gap + stripR; its leftmost stripL pixels reproduce frag_j's
 * right strip and its rightmost stripR pixels reproduce frag_{j+1}'s left strip. When the
 * resulting image is tiled, the wraparound stitches frag_{N-1}'s left_strip (sitting at the
 * right end of inp_{N-1}) up against interior_0 (= frag_0[stripL:W-stripR]) — together they
 * reconstruct frag_0 sans its right_strip, which sits at the start of inp_0 in the next tile.
 */
export async function assembleTileable({ fragments, joinResults, stripL = 256, stripR = 256 }) {
  const N = fragments.length;
  if (N === 0) throw new Error('No fragments');
  if (joinResults.length !== N) throw new Error(`Need ${N} join results, got ${joinResults.length}`);

  const fragImgs = await Promise.all(fragments.map(f => loadImage(f.dataUrl)));
  const joinImgs = await Promise.all(joinResults.map(r => loadImage(r.dataUrl)));

  // Compute total width
  let totalW = 0;
  const interiorWidths = [];
  for (let j = 0; j < N; j++) {
    const fw = fragImgs[j].width;
    const interior = Math.max(0, fw - stripL - stripR);
    interiorWidths.push(interior);
    totalW += interior + joinImgs[j].width;
  }
  // All join images / fragments may have different heights — final canvas uses max
  const totalH = Math.max(
    ...fragImgs.map(i => i.height),
    ...joinImgs.map(i => i.height),
  );

  const out = document.createElement('canvas');
  out.width = totalW;
  out.height = totalH;
  const octx = out.getContext('2d');
  octx.fillStyle = 'black';
  octx.fillRect(0, 0, totalW, totalH);

  let x = 0;
  for (let j = 0; j < N; j++) {
    const fragImg = fragImgs[j];
    const interior = interiorWidths[j];
    // Apply per-fragment yOffset so the interior aligns with the right_strip baked into the
    // adjacent join images (those strips were drawn with the same yOffset in buildJoinCanvas).
    const yOffset = fragments[j].yOffset || 0;
    const fragY = Math.round((totalH - fragImg.height) / 2) + yOffset;
    if (interior > 0) {
      // Source: frag_j[stripL : W - stripR]
      octx.drawImage(
        fragImg,
        stripL, 0, interior, fragImg.height,
        x, fragY, interior, fragImg.height,
      );
    }
    x += interior;

    const joinImg = joinImgs[j];
    const joinY = Math.round((totalH - joinImg.height) / 2);
    octx.drawImage(joinImg, x, joinY);
    x += joinImg.width;
  }

  return out.toDataURL('image/png');
}

// =============================================================
// Hero floating-yarn background — same logic as the landing
// page thread canvas, minus the hover tooltip / detail box.
// Sized to its parent container, not the viewport.
// =============================================================
(function () {
  function init() {
    const canvas = document.getElementById('heroYarnCanvas');
    if (!canvas) {
      // The studio header may not be mounted yet (React still hydrating).
      // Retry on the next animation frame; bail after a few tries.
      if (init._tries === undefined) init._tries = 0;
      if (init._tries++ < 60) requestAnimationFrame(init);
      return;
    }
    const ctx = canvas.getContext('2d');

    // Smaller hero area than the landing's full viewport, but we keep
    // the same density feel as the landing page.
    const THREAD_COUNT = 280;

    // ===== YARN IMAGE LIBRARY =====
    const yarnImageNames = [
      "1777399447352-346-z-image_00159_.png", "1777399447352-779-z-image_00143_.png",
      "1777399447353-118-z-image_00155_.png", "1777399447353-634-z-image_00157_.png",
      "1777399447353-798-z-image_00158_.png", "1777399447353-91-z-image_00156_.png",
      "1777399447354-217-z-image_00150_.png", "1777399447354-280-z-image_00153_.png",
      "1777399447354-555-z-image_00151_.png", "1777399447354-834-z-image_00152_.png",
      "1777399447354-868-z-image_00148_.png", "1777399447354-899-z-image_00154_.png",
      "1777399447355-563-z-image_00141_.png", "1777399447355-688-z-image_00146_.png",
      "1777399447355-811-z-image_00145_.png", "1777399447355-845-z-image_00140_.png",
      "1777399447355-986-z-image_00142_.png", "1777399447356-186-z-image_00138_.png",
      "1777399447356-341-z-image_00137_.png", "1777399447356-379-z-image_00139_.png",
      "1777399447356-646-z-image_00134_.png", "1777399447356-678-z-image_00136_.png",
      "1777399447356-83-z-image_00135_.png", "1777399447357-280-z-image_00131_.png",
      "1777399447357-359-z-image_00127_.png", "1777399447357-625-z-image_00126_.png",
      "1777399447357-685-z-image_00133_.png", "1777399447357-707-z-image_00130_.png",
      "1777399447357-894-z-image_00125_.png", "1777399447357-923-z-image_00132_.png",
      "1777399447358-176-z-image_00119_.png", "1777399447358-210-z-image_00118_.png",
      "1777399447358-35-z-image_00120_.png", "1777399447358-412-z-image_00124_.png",
      "1777399447358-422-z-image_00123_.png", "1777399447358-605-z-image_00122_.png",
      "1777399447359-33-z-image_00116_.png", "1777399447359-34-z-image_00115_.png",
      "1777399447359-410-z-image_00107_.png", "1777399447359-472-z-image_00112_.png",
      "1777399447359-785-z-image_00110_.png", "1777399447359-832-z-image_00111_.png",
      "1777399447359-972-z-image_00114_.png", "1777399447359-979-z-image_00113_.png",
      "1777399447360-230-z-image_00160_.png",
    ];
    const yarnImages = [];

    // ---- Color utils (cached) ----
    const rgbCache = {};
    function hexToRgb(hex) {
      if (rgbCache[hex]) return rgbCache[hex];
      const h = hex.replace('#', '');
      const result = {
        r: parseInt(h.substring(0, 2), 16),
        g: parseInt(h.substring(2, 4), 16),
        b: parseInt(h.substring(4, 6), 16),
      };
      rgbCache[hex] = result;
      return result;
    }
    function rgbToHex(r, g, b) {
      return (
        '#' +
        ((1 << 24) +
          (Math.max(0, Math.min(255, r | 0)) << 16) +
          (Math.max(0, Math.min(255, g | 0)) << 8) +
          Math.max(0, Math.min(255, b | 0)))
          .toString(16)
          .slice(1)
      );
    }
    function hslToHex(h, s, l) {
      s /= 100;
      l /= 100;
      const c = (1 - Math.abs(2 * l - 1)) * s;
      const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
      const m = l - c / 2;
      let r = 0, g = 0, b = 0;
      if (h < 60) { r = c; g = x; }
      else if (h < 120) { r = x; g = c; }
      else if (h < 180) { g = c; b = x; }
      else if (h < 240) { g = x; b = c; }
      else if (h < 300) { r = x; b = c; }
      else { r = c; b = x; }
      return rgbToHex((r + m) * 255, (g + m) * 255, (b + m) * 255);
    }

    // ---- Sample dominant color from each loaded yarn image ----
    // Same quantized-histogram approach as the landing page so colors
    // match what the user sees in the floating-yarn library.
    function sampleDominantColor(img) {
      if (img._sampled) return;
      img._sampled = true;
      let detectedHex = null;
      try {
        const tmp = document.createElement('canvas');
        const sz = 80;
        tmp.width = sz;
        tmp.height = sz;
        const tctx = tmp.getContext('2d');
        tctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight, 0, 0, sz, sz);
        const data = tctx.getImageData(0, 0, sz, sz).data;
        const buckets = new Map();
        for (let i = 0; i < data.length; i += 4) {
          const r = data[i], g = data[i + 1], b = data[i + 2], a = data[i + 3];
          if (a < 100) continue;
          if (r > 240 && g > 240 && b > 240) continue;
          if (r < 12 && g < 12 && b < 12) continue;
          const mx = Math.max(r, g, b);
          const mn = Math.min(r, g, b);
          const sat = mx === 0 ? 0 : (mx - mn) / mx;
          let weight;
          if (sat > 0.35) weight = 4;
          else if (sat > 0.18) weight = 2;
          else if (sat > 0.08) weight = 0.6;
          else weight = 0.15;
          const key = (r >> 5) * 64 + (g >> 5) * 8 + (b >> 5);
          const bucket = buckets.get(key);
          if (bucket) {
            bucket.r += r * weight;
            bucket.g += g * weight;
            bucket.b += b * weight;
            bucket.w += weight;
          } else {
            buckets.set(key, { r: r * weight, g: g * weight, b: b * weight, w: weight });
          }
        }
        let best = null;
        buckets.forEach((v) => { if (!best || v.w > best.w) best = v; });
        if (best && best.w > 0) {
          detectedHex = rgbToHex(best.r / best.w, best.g / best.w, best.b / best.w);
        }
      } catch (e) {
        // canvas may be tainted under some loaders — fall through to fallback
      }
      if (!detectedHex) {
        const fname = (img.src || '').split('/').pop();
        let hash = 0;
        for (let i = 0; i < fname.length; i++) hash = (hash * 31 + fname.charCodeAt(i)) | 0;
        const hue = ((hash % 360) + 360) % 360;
        const sat = 55 + (Math.abs(hash >> 8) % 35);
        const lit = 35 + (Math.abs(hash >> 16) % 30);
        detectedHex = hslToHex(hue, sat, lit);
      }
      img.dominantHex = detectedHex;
    }

    yarnImageNames.forEach((name) => {
      const img = new Image();
      img.src = '/images/yarns/' + name;
      img.addEventListener('load', () => sampleDominantColor(img));
      img.dominantHex = '#888888';
      yarnImages.push(img);
    });
    function randomYarnImage() {
      return yarnImages[Math.floor(Math.random() * yarnImages.length)];
    }

    // CSS-pixel dimensions (used for hit-testing & physics). The
    // canvas.width/height are only the HiDPI backing buffer.
    let cssW = 0;
    let cssH = 0;
    let threads = [];
    let mouse = { x: -9999, y: -9999 };
    let hoveredThread = null;

    // ===== THREAD CLASS — verbatim from the landing canvas, minus
    // the tooltip-related fields (manufacturer, color name, variants).
    class Thread {
      constructor() {
        this.yarnImage = randomYarnImage();
        this.angle = 30;
        this.angleRad = (this.angle * Math.PI) / 180;
        this.cosA = Math.cos(this.angleRad);
        this.sinA = Math.sin(this.angleRad);

        // Depth: 0 = far (small, slow, faint), 1 = near (big, fast, vivid)
        this.depth = Math.pow(Math.random(), 0.6);

        this.x = 0;
        this.y = 0;
        this.baseX = 0;
        this.baseY = 0;
        this.length = 0;
        this.scale = 1;
        this.targetScale = 1;
        this.zIndex = this.depth * 10;
        this.targetZIndex = this.zIndex;

        this.opacity = 0.25 + this.depth * 0.75;
        this.baseOpacity = this.opacity;
        this.targetOpacity = this.opacity;

        this.bobOffset = Math.random() * Math.PI * 2;
        this.bobSpeed = 0.2 + Math.random() * 0.3;
        this.bobAmt = 1 + Math.random() * 2;
        this.scrollSpeed = 3 + this.depth * 15;
        this.picked = false;
      }

      place(w, h, fromInflow) {
        this.length = h * 3.5;
        if (fromInflow) {
          const vx = Math.abs(this.sinA);
          const vy = Math.abs(this.cosA);
          const bottomChance = vy / (vx + vy);
          if (Math.random() < bottomChance) {
            this.baseX = -this.length * this.sinA + Math.random() * (w + this.length * this.sinA * 1.4);
            this.baseY = h + Math.random() * 120;
          } else {
            this.baseX = w + Math.random() * 120;
            this.baseY = -this.length * this.cosA * 0.3 + Math.random() * h;
          }
        } else {
          this.baseX = -this.length * this.sinA + Math.random() * (w + this.length * this.sinA * 1.4);
          this.baseY = -this.length * this.cosA * 0.3 + Math.random() * (h + this.length * this.cosA * 0.6);
        }
        this.x = this.baseX;
        this.y = this.baseY;
      }

      recycle(w, h) {
        this.yarnImage = randomYarnImage();
        this.depth = Math.pow(Math.random(), 0.6);
        this.opacity = 0.25 + this.depth * 0.75;
        this.baseOpacity = this.opacity;
        this.targetOpacity = this.opacity;
        this.scale = 1;
        this.targetScale = 1;
        this.zIndex = this.depth * 10;
        this.targetZIndex = this.zIndex;
        this.picked = false;
        this.bobOffset = Math.random() * Math.PI * 2;
        this.scrollSpeed = 3 + this.depth * 15;
        this.place(w, h, true);
      }

      containsPoint(px, py) {
        const dx = px - this.x;
        const dy = py - this.y;
        const cos = Math.cos(-this.angleRad);
        const sin = Math.sin(-this.angleRad);
        const localX = dx * cos - dy * sin;
        const localY = dx * sin + dy * cos;
        const s = this.scale;
        const thickness = (8 + this.depth * 28) * s;
        const r = thickness / 2;
        const h = this.length * s;
        const topExtend = h * 0.7;
        return (
          localX > -r - 4 &&
          localX < r + 4 &&
          localY > -topExtend - 4 &&
          localY < h + r + 4
        );
      }

      update(time, dt) {
        if (!this.picked) {
          this.baseX -= this.sinA * this.scrollSpeed * dt;
          this.baseY -= this.cosA * this.scrollSpeed * dt;
        }
        const bob = Math.sin(time * this.bobSpeed + this.bobOffset) * this.bobAmt;
        this.x = this.baseX + this.cosA * bob;
        this.y = this.baseY - this.sinA * bob;
        this.scale += (this.targetScale - this.scale) * 0.1;
        this.opacity += (this.targetOpacity - this.opacity) * 0.1;
        this.zIndex += (this.targetZIndex - this.zIndex) * 0.12;
      }

      isOffScreen() {
        const tipX = this.x + this.length * this.sinA;
        const tipY = this.y + this.length * this.cosA;
        return tipX < -80 || tipY < -80;
      }

      draw() {
        const img = this.yarnImage;
        if (!img || !img.complete || img.naturalWidth === 0) return;
        const s = this.scale;
        const thickness = (8 + this.depth * 28) * s;
        const length = this.length * s;
        ctx.save();
        ctx.translate(this.x, this.y);
        ctx.rotate(this.angleRad);
        ctx.globalAlpha = Math.min(this.opacity, 1);
        const imgW = img.naturalWidth;
        const imgH = img.naturalHeight;
        const tileLen = imgW * (thickness / imgH);
        ctx.rotate(Math.PI / 2);
        const topExtend = length * 0.7;
        const startPos = -Math.ceil(topExtend / tileLen) * tileLen;
        for (let pos = startPos; pos < length; pos += tileLen) {
          ctx.drawImage(img, pos, -thickness / 2, tileLen, thickness);
        }
        ctx.restore();
      }

      setHovered(val) {
        if (val) {
          this.targetScale = 1.8;
          this.targetOpacity = 1;
          this.targetZIndex = 1000;
          this.picked = true;
        } else {
          this.targetScale = 1;
          this.targetOpacity = this.baseOpacity;
          this.targetZIndex = this.depth * 10;
          this.picked = false;
        }
      }
    }

    // ===== Spatial grid for fast hit detection =====
    const GRID_SIZE = 80;
    let gridCols, gridRows, grid;
    function buildGrid() {
      gridCols = Math.ceil(cssW / GRID_SIZE) + 1;
      gridRows = Math.ceil(cssH / GRID_SIZE) + 1;
      grid = new Array(gridCols * gridRows);
      for (let i = 0; i < grid.length; i++) grid[i] = [];
      for (const t of threads) {
        const cx = t.x;
        const cy = t.y + t.length / 2;
        const hw = t.length * Math.abs(t.sinA) / 2 + 20;
        const hh = t.length * Math.abs(t.cosA) / 2 + 20;
        const minCol = Math.max(0, Math.floor((cx - hw) / GRID_SIZE));
        const maxCol = Math.min(gridCols - 1, Math.floor((cx + hw) / GRID_SIZE));
        const minRow = Math.max(0, Math.floor((cy - hh) / GRID_SIZE));
        const maxRow = Math.min(gridRows - 1, Math.floor((cy + hh) / GRID_SIZE));
        for (let r = minRow; r <= maxRow; r++) {
          for (let c = minCol; c <= maxCol; c++) {
            grid[r * gridCols + c].push(t);
          }
        }
      }
    }
    function findThreadAt(px, py) {
      const col = Math.floor(px / GRID_SIZE);
      const row = Math.floor(py / GRID_SIZE);
      if (col < 0 || col >= gridCols || row < 0 || row >= gridRows) return null;
      const cell = grid[row * gridCols + col];
      for (let i = cell.length - 1; i >= 0; i--) {
        if (cell[i].containsPoint(px, py)) return cell[i];
      }
      return null;
    }

    function getSize() {
      const rect = canvas.getBoundingClientRect();
      return {
        w: Math.max(120, Math.floor(rect.width)),
        h: Math.max(80, Math.floor(rect.height)),
      };
    }
    function resizeCanvas(recreate) {
      const { w, h } = getSize();
      cssW = w;
      cssH = h;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = w + 'px';
      canvas.style.height = h + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (recreate) createThreads();
      else buildGrid();
    }
    function createThreads() {
      threads = [];
      for (let i = 0; i < THREAD_COUNT; i++) {
        const t = new Thread();
        t.place(cssW, cssH, false);
        threads.push(t);
      }
      buildGrid();
    }

    // No hover highlighting on the studio hero — threads just float by.
    canvas.style.pointerEvents = 'none';

    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(() => resizeCanvas(false));
      ro.observe(canvas);
    } else {
      window.addEventListener('resize', () => resizeCanvas(false));
    }

    let lastTime = 0;
    let frameCount = 0;
    function animate(timestamp) {
      const time = timestamp / 1000;
      const dt = Math.min(time - lastTime, 0.1);
      lastTime = time;
      ctx.clearRect(0, 0, cssW, cssH);
      for (let i = 0; i < threads.length; i++) {
        threads[i].update(time, dt);
        if (threads[i].isOffScreen()) {
          threads[i].recycle(cssW, cssH);
        }
      }
      if (frameCount++ % 15 === 0) buildGrid();
      threads.sort((a, b) => a.zIndex - b.zIndex);
      for (let i = 0; i < threads.length; i++) threads[i].draw();
      requestAnimationFrame(animate);
    }

    resizeCanvas(true);
    animate(0);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

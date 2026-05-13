// ===== MANUFACTURER DATA =====
const manufacturers = [
    {
        name: "Coats Group PLC",
        initials: "CG",
        location: "London, UK",
        region: "europe",
        category: "industrial",
        desc: "World's leading industrial thread manufacturer. Supplies sewing, embroidery, and specialty threads to apparel, footwear, and automotive industries.",
        tags: ["Industrial", "Sewing", "Embroidery"],
        established: 1755,
        certs: ["ISO 9001", "ISO 14001", "OEKO-TEX"],
        rating: 4.9,
        reviews: 128,
        color: "#1a5276"
    },
    {
        name: "A&E (American & Efird)",
        initials: "AE",
        location: "Charlotte, USA",
        region: "north-america",
        category: "polyester",
        desc: "One of the world's largest thread manufacturers offering polyester, cotton, and nylon sewing threads for the global apparel and industrial markets.",
        tags: ["Polyester", "Cotton", "Nylon"],
        established: 1891,
        certs: ["ISO 9001", "OEKO-TEX"],
        rating: 4.7,
        reviews: 94,
        color: "#2e86c1"
    },
    {
        name: "Madeira Garnfabrik",
        initials: "MG",
        location: "Freiburg, Germany",
        region: "europe",
        category: "specialty",
        desc: "Premium embroidery thread specialists known for vibrant colors and innovative specialty threads for machine embroidery and decorative applications.",
        tags: ["Embroidery", "Specialty", "Decorative"],
        established: 1919,
        certs: ["OEKO-TEX", "ISO 14001"],
        rating: 4.8,
        reviews: 76,
        color: "#8e44ad"
    },
    {
        name: "Amann Group",
        initials: "AG",
        location: "Augsburg, Germany",
        region: "europe",
        category: "polyester",
        desc: "High-quality sewing and embroidery threads for fashion, automotive, and technical textiles. Known for sustainable production and innovative thread technologies.",
        tags: ["Polyester", "Automotive", "Technical"],
        established: 1854,
        certs: ["ISO 9001", "GOTS", "bluesign"],
        rating: 4.8,
        reviews: 89,
        color: "#27ae60"
    },
    {
        name: "Raj Silk Mills",
        initials: "RS",
        location: "Varanasi, India",
        region: "asia",
        category: "silk",
        desc: "Traditional silk thread manufacturer specializing in pure mulberry silk for Banarasi weaving, fashion, and luxury textile applications.",
        tags: ["Silk", "Luxury", "Traditional"],
        established: 1968,
        certs: ["ISO 9001", "Silk Mark"],
        rating: 4.5,
        reviews: 42,
        color: "#c0392b"
    },
    {
        name: "Fujix Ltd.",
        initials: "FX",
        location: "Kyoto, Japan",
        region: "asia",
        category: "polyester",
        desc: "Japanese precision thread manufacturer producing polyester and nylon sewing threads with exceptional strength and color consistency for high-end garment construction.",
        tags: ["Polyester", "Nylon", "Precision"],
        established: 1952,
        certs: ["ISO 9001", "OEKO-TEX"],
        rating: 4.7,
        reviews: 58,
        color: "#2c3e50"
    },
    {
        name: "Nantong Xinhua Thread Co.",
        initials: "NX",
        location: "Nantong, China",
        region: "asia",
        category: "cotton",
        desc: "Large-scale cotton and poly-cotton thread manufacturer exporting to 30+ countries. Competitive pricing with consistent quality for bulk orders.",
        tags: ["Cotton", "Poly-Cotton", "Bulk"],
        established: 1995,
        certs: ["ISO 9001", "BSCI"],
        rating: 4.3,
        reviews: 67,
        color: "#d4a017"
    },
    {
        name: "Brildor S.L.",
        initials: "BR",
        location: "Barcelona, Spain",
        region: "europe",
        category: "specialty",
        desc: "Specialist in embroidery threads, offering 4000+ colors in polyester, rayon, and metallic threads for industrial embroidery machines.",
        tags: ["Embroidery", "Rayon", "Metallic"],
        established: 1982,
        certs: ["OEKO-TEX", "ISO 9001"],
        rating: 4.6,
        reviews: 53,
        color: "#e74c3c"
    },
    {
        name: "SilCon Thread Works",
        initials: "ST",
        location: "Sao Paulo, Brazil",
        region: "south-america",
        category: "cotton",
        desc: "Brazilian cotton thread producer using locally sourced long-staple cotton. Specialized in mercerized threads for the South American textile market.",
        tags: ["Cotton", "Mercerized", "Organic"],
        established: 2001,
        certs: ["GOTS", "Fair Trade"],
        rating: 4.4,
        reviews: 31,
        color: "#16a085"
    },
    {
        name: "Nylon Fibers Corp.",
        initials: "NF",
        location: "Seoul, South Korea",
        region: "asia",
        category: "nylon",
        desc: "Leading nylon thread manufacturer producing bonded nylon, texturized nylon, and monofilament threads for heavy-duty industrial applications.",
        tags: ["Nylon", "Bonded", "Industrial"],
        established: 1978,
        certs: ["ISO 9001", "KS Mark"],
        rating: 4.6,
        reviews: 48,
        color: "#34495e"
    },
    {
        name: "ThreadSol Africa",
        initials: "TA",
        location: "Cape Town, South Africa",
        region: "africa",
        category: "polyester",
        desc: "Growing African thread manufacturer producing core-spun and polyester threads for the local and export markets. Focus on sustainable production.",
        tags: ["Polyester", "Core-Spun", "Sustainable"],
        established: 2008,
        certs: ["ISO 9001"],
        rating: 4.2,
        reviews: 19,
        color: "#f39c12"
    },
    {
        name: "Phong Phu Thread",
        initials: "PP",
        location: "Ho Chi Minh City, Vietnam",
        region: "asia",
        category: "cotton",
        desc: "Vietnamese thread manufacturer specializing in combed cotton sewing threads for the garment export industry. Competitive pricing and fast turnaround.",
        tags: ["Cotton", "Sewing", "Export"],
        established: 1999,
        certs: ["ISO 9001", "WRAP"],
        rating: 4.4,
        reviews: 55,
        color: "#2980b9"
    }
];

// ===== RENDER LISTINGS =====
function renderListings(data) {
    const grid = document.getElementById('listingsGrid');
    const count = document.getElementById('resultsCount');

    if (!grid) return;

    count.textContent = `Showing ${data.length} vendor${data.length !== 1 ? 's' : ''}`;

    if (data.length === 0) {
        grid.innerHTML = `
            <div style="grid-column: 1/-1; text-align: center; padding: 60px 20px; color: var(--text-light);">
                <p style="font-size: 1.1rem; margin-bottom: 8px;">No vendors found</p>
                <p style="font-size: 0.9rem;">Try adjusting your search or filters.</p>
            </div>`;
        return;
    }

    grid.innerHTML = data.map(m => `
        <div class="listing-card">
            <div class="listing-header">
                <div class="listing-avatar" style="--bg: ${m.color}">${m.initials}</div>
                <div>
                    <h3>${m.name}</h3>
                    <p class="listing-location">${m.location}</p>
                </div>
            </div>
            <div class="listing-rating">
                <span class="stars">${'&#9733;'.repeat(Math.floor(m.rating))}${m.rating % 1 >= 0.5 ? '&#9734;' : ''}</span>
                <span class="rating-count">${m.rating} (${m.reviews} reviews)</span>
            </div>
            <p class="listing-desc">${m.desc}</p>
            <div class="listing-tags">
                ${m.tags.map(t => `<span class="tag">${t}</span>`).join('')}
            </div>
            <div class="listing-meta">
                <span class="meta-item">Est. ${m.established}</span>
                ${m.certs.map(c => `<span class="meta-item">${c}</span>`).join('')}
            </div>
            <div class="listing-footer">
                <a href="#" class="btn btn-outline-dark btn-sm">View Profile</a>
                <a href="#" class="btn btn-primary btn-sm">Contact</a>
            </div>
        </div>
    `).join('');
}

// ===== SEARCH & FILTER =====
function filterManufacturers() {
    const query = document.getElementById('searchInput').value.toLowerCase().trim();
    const category = document.getElementById('searchCategory').value;
    const region = document.getElementById('searchRegion').value;

    let results = manufacturers.filter(m => {
        const matchesQuery = !query ||
            m.name.toLowerCase().includes(query) ||
            m.desc.toLowerCase().includes(query) ||
            m.tags.some(t => t.toLowerCase().includes(query)) ||
            m.location.toLowerCase().includes(query);
        const matchesCategory = !category || m.category === category;
        const matchesRegion = !region || m.region === region;
        return matchesQuery && matchesCategory && matchesRegion;
    });

    // Sort
    const sortBy = document.getElementById('sortBy').value;
    if (sortBy === 'name') results.sort((a, b) => a.name.localeCompare(b.name));
    else if (sortBy === 'established') results.sort((a, b) => a.established - b.established);
    else if (sortBy === 'rating') results.sort((a, b) => b.rating - a.rating);

    renderListings(results);
}

// ===== CATEGORY CARD CLICKS =====
document.querySelectorAll('.cat-card[data-filter]').forEach(card => {
    card.addEventListener('click', (e) => {
        e.preventDefault();
        const filter = card.dataset.filter;
        document.getElementById('searchCategory').value = filter;
        document.getElementById('searchInput').value = '';
        document.getElementById('searchRegion').value = '';
        filterManufacturers();
        document.getElementById('listings').scrollIntoView({ behavior: 'smooth' });
    });
});

// ===== EVENT LISTENERS =====
document.getElementById('searchBtn').addEventListener('click', () => {
    filterManufacturers();
    document.getElementById('listings').scrollIntoView({ behavior: 'smooth' });
});

document.getElementById('searchInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        filterManufacturers();
        document.getElementById('listings').scrollIntoView({ behavior: 'smooth' });
    }
});

document.getElementById('sortBy').addEventListener('change', filterManufacturers);

// ===== MOBILE NAV =====
document.getElementById('navToggle').addEventListener('click', () => {
    document.querySelector('.nav').classList.toggle('active');
});

// ===== HEADER SCROLL =====
window.addEventListener('scroll', () => {
    document.querySelector('.header').classList.toggle('scrolled', window.scrollY > 10);
});

// ===== FORM SUBMIT =====
document.getElementById('submitForm').addEventListener('submit', (e) => {
    e.preventDefault();
    alert('Thank you! Your listing has been submitted for review. We will contact you within 2 business days.');
    e.target.reset();
});

// ===== INIT =====
renderListings(manufacturers);

// ===== STUDIO LAUNCH HELPERS =====
function openFabricStudio(context) {
    const url = context && context.hex
        ? '/studio.html?seed=' + encodeURIComponent(context.hex)
        : '/studio.html';
    window.location.href = url;
}

// ===== YARN PICKER MODAL =====
// Click a floating yarn → confirm → upload to /api/yarn/assets → studio.
(function() {
    const picker = document.getElementById('yarnPicker');
    if (!picker) return;

    const dialog = picker.querySelector('.yarn-picker__dialog');
    const imgEl = picker.querySelector('#yarnPickerImage');
    const swatchEl = picker.querySelector('#yarnPickerSwatch');
    const titleEl = picker.querySelector('#yarnPickerTitle');
    const metaEl = picker.querySelector('#yarnPickerMeta');
    const statusEl = picker.querySelector('#yarnPickerStatus');
    const confirmBtn = picker.querySelector('#yarnPickerConfirm');
    const closeButtons = picker.querySelectorAll('[data-yarn-picker-close]');

    let activeThread = null;
    let busy = false;

    function setStatus(text, kind) {
        statusEl.textContent = text || '';
        statusEl.dataset.kind = kind || '';
    }

    function close() {
        if (busy) return;
        picker.hidden = true;
        document.body.classList.remove('yarn-picker-open');
        activeThread = null;
        setStatus('');
    }

    function open(thread) {
        activeThread = thread;
        const img = thread && thread.yarnImage;
        if (img && img.src) {
            imgEl.src = img.src;
            imgEl.alt = (thread.data && thread.data.colorName) || 'Selected yarn';
        }
        const hex = (thread.displayColor) || (thread.data && thread.data.hex) || '#888';
        swatchEl.style.background = hex;
        titleEl.textContent = (thread.data && thread.data.colorName) || 'Yarn';
        const parts = [];
        if (thread.manufacturer) parts.push(thread.manufacturer);
        if (thread.data && thread.data.material) parts.push(thread.data.material);
        metaEl.textContent = parts.join(' · ');
        setStatus('Add this yarn to your library — the studio will process it into seamless diffuse + alpha maps.', 'info');
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Add to Library & Process';
        picker.hidden = false;
        document.body.classList.add('yarn-picker-open');
    }

    closeButtons.forEach((el) => el.addEventListener('click', close));
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !picker.hidden) close();
    });
    dialog.addEventListener('click', (e) => e.stopPropagation());

    async function uploadActiveYarn() {
        if (!activeThread || busy) return;
        const img = activeThread.yarnImage;
        if (!img || !img.src) {
            setStatus('Could not read this yarn image.', 'error');
            return;
        }
        busy = true;
        confirmBtn.disabled = true;
        confirmBtn.textContent = 'Uploading…';
        setStatus('Fetching yarn image…', 'info');
        try {
            const response = await fetch(img.src);
            if (!response.ok) throw new Error('Could not load the yarn image.');
            const blob = await response.blob();
            const filename = (img.src.split('/').pop() || 'yarn.png').split('?')[0];
            const file = new File([blob], filename, { type: blob.type || 'image/png' });

            setStatus('Uploading to your library…', 'info');
            const formData = new FormData();
            formData.append('files', file);
            // Floating yarn images are wide horizontal strands; force orientation.
            formData.append('orientation', 'horizontal');

            const upload = await fetch('/api/yarn/assets', { method: 'POST', body: formData });
            if (!upload.ok) {
                const text = await upload.text();
                throw new Error(`Upload failed (${upload.status}). ${text.slice(0, 200)}`);
            }

            setStatus('Added! Opening the Fabric Generator…', 'success');
            confirmBtn.textContent = 'Opening Studio…';
            // Brief pause so the user sees the success state, then jump to Step 1.
            setTimeout(() => openFabricStudio(), 600);
        } catch (err) {
            console.error(err);
            setStatus(err && err.message ? err.message : 'Something went wrong while adding this yarn.', 'error');
            busy = false;
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Add to Library & Process';
        }
    }

    confirmBtn.addEventListener('click', uploadActiveYarn);

    // Public hook used by the canvas click handler.
    window.openYarnPicker = open;
})();

// ===== CREATE BUTTON: jump straight into the Fabric Generator =====
(function() {
    const btn = document.getElementById('createBtn');
    if (!btn) return;
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        openFabricStudio();
    });
})();

// ===== LIBRARY SEARCH: clicking the search icon opens the Studio =====
(function() {
    const search = document.getElementById('librarySearch');
    const input = document.getElementById('librarySearchInput');
    if (!search || !input) return;

    input.placeholder = 'Open the Fabric Generator…';
    input.readOnly = true;

    search.addEventListener('click', (e) => {
        e.preventDefault();
        openFabricStudio();
    });

    search.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            openFabricStudio();
        }
    });
})();

// ================================================================
// ===== INTERACTIVE THREAD TUBES BACKGROUND (500 threads) ========
// ================================================================
(function() {
    const canvas = document.getElementById('threadCanvas');
    const ctx = canvas.getContext('2d');
    const tooltip = document.getElementById('threadTooltip');
    const tooltipPreview = document.getElementById('tooltipPreview');
    const tooltipName = document.getElementById('tooltipName');
    const tooltipMaterial = document.getElementById('tooltipMaterial');
    const tooltipColors = document.getElementById('tooltipColors');

    const THREAD_COUNT = 600;

    // ===== YARN IMAGE LIBRARY =====
    const yarnImageNames = [
        "1777399447352-346-z-image_00159_.png","1777399447352-779-z-image_00143_.png",
        "1777399447353-118-z-image_00155_.png","1777399447353-634-z-image_00157_.png",
        "1777399447353-798-z-image_00158_.png","1777399447353-91-z-image_00156_.png",
        "1777399447354-217-z-image_00150_.png","1777399447354-280-z-image_00153_.png",
        "1777399447354-555-z-image_00151_.png","1777399447354-834-z-image_00152_.png",
        "1777399447354-868-z-image_00148_.png","1777399447354-899-z-image_00154_.png",
        "1777399447355-563-z-image_00141_.png","1777399447355-688-z-image_00146_.png",
        "1777399447355-811-z-image_00145_.png","1777399447355-845-z-image_00140_.png",
        "1777399447355-986-z-image_00142_.png","1777399447356-186-z-image_00138_.png",
        "1777399447356-341-z-image_00137_.png","1777399447356-379-z-image_00139_.png",
        "1777399447356-646-z-image_00134_.png","1777399447356-678-z-image_00136_.png",
        "1777399447356-83-z-image_00135_.png","1777399447357-280-z-image_00131_.png",
        "1777399447357-359-z-image_00127_.png","1777399447357-625-z-image_00126_.png",
        "1777399447357-685-z-image_00133_.png","1777399447357-707-z-image_00130_.png",
        "1777399447357-894-z-image_00125_.png","1777399447357-923-z-image_00132_.png",
        "1777399447358-176-z-image_00119_.png","1777399447358-210-z-image_00118_.png",
        "1777399447358-35-z-image_00120_.png","1777399447358-412-z-image_00124_.png",
        "1777399447358-422-z-image_00123_.png","1777399447358-605-z-image_00122_.png",
        "1777399447359-33-z-image_00116_.png","1777399447359-34-z-image_00115_.png",
        "1777399447359-410-z-image_00107_.png","1777399447359-472-z-image_00112_.png",
        "1777399447359-785-z-image_00110_.png","1777399447359-832-z-image_00111_.png",
        "1777399447359-972-z-image_00114_.png","1777399447359-979-z-image_00113_.png",
        "1777399447360-230-z-image_00160_.png"
    ];
    const yarnImages = [];

    // Material pool — paired randomly with each thread
    const yarnMaterials = [
        "100% Mercerized Cotton", "Pure Silk Filament", "Combed Cotton Ne 40",
        "Polyester Bonded Thread", "Nylon 6.6 Industrial", "Linen/Flax Natural",
        "Bamboo Viscose Blend", "Modal/Cotton 60/40", "Recycled Polyester rPET",
        "Hemp/Cotton 50/50", "Cashmere Wool Blend", "Organic GOTS Cotton",
        "Tencel Lyocell", "Worsted Wool Blend", "Air-Jet Spun Polyester",
        "Ring-Spun Cotton", "Open-End Rotor Cotton", "Supima Premium Cotton",
        "Metallic Lurex Thread", "Core-Spun Polyester"
    ];

    // ---- Color naming based on HSL ----
    function nameFromHex(hex) {
        const c = hexToRgb(hex);
        const rN = c.r / 255, gN = c.g / 255, bN = c.b / 255;
        const max = Math.max(rN, gN, bN);
        const min = Math.min(rN, gN, bN);
        const l = (max + min) / 2;
        const d = max - min;
        let h = 0, s = 0;
        if (d > 0) {
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            if (max === rN) h = ((gN - bN) / d + (gN < bN ? 6 : 0)) * 60;
            else if (max === gN) h = ((bN - rN) / d + 2) * 60;
            else h = ((rN - gN) / d + 4) * 60;
        }

        // Near-grayscale
        if (s < 0.1) {
            if (l < 0.15) return 'Obsidian';
            if (l < 0.32) return 'Charcoal';
            if (l < 0.5)  return 'Slate Gray';
            if (l < 0.7)  return 'Pearl Gray';
            if (l < 0.92) return 'Bone White';
            return 'Ivory';
        }

        const hue = (h + 360) % 360;
        let family;
        if (hue < 12 || hue >= 348)  family = 'Red';
        else if (hue < 25)            family = 'Coral';
        else if (hue < 40)            family = 'Orange';
        else if (hue < 52)            family = 'Amber';
        else if (hue < 68)            family = 'Yellow';
        else if (hue < 92)            family = 'Olive';
        else if (hue < 145)           family = 'Green';
        else if (hue < 175)           family = 'Teal';
        else if (hue < 200)           family = 'Cyan';
        else if (hue < 222)           family = 'Sky';
        else if (hue < 248)           family = 'Blue';
        else if (hue < 272)           family = 'Indigo';
        else if (hue < 298)           family = 'Violet';
        else if (hue < 322)           family = 'Magenta';
        else if (hue < 348)           family = 'Pink';
        else                          family = 'Red';

        // Decorate with lightness/saturation modifiers
        if (l < 0.22) {
            const deepNames = { Red: 'Wine', Coral: 'Maroon', Orange: 'Mahogany', Amber: 'Burnt Caramel',
                Yellow: 'Tobacco', Olive: 'Forest Moss', Green: 'Hunter Green', Teal: 'Deep Teal',
                Cyan: 'Midnight Cyan', Sky: 'Steel Blue', Blue: 'Midnight Navy', Indigo: 'Deep Indigo',
                Violet: 'Royal Purple', Magenta: 'Plum', Pink: 'Mulberry' };
            return deepNames[family] || ('Deep ' + family);
        }
        if (l < 0.4) {
            const darkNames = { Red: 'Burgundy', Coral: 'Brick Red', Orange: 'Rust', Amber: 'Caramel',
                Yellow: 'Mustard', Olive: 'Olive Green', Green: 'Forest Green', Teal: 'Deep Teal',
                Cyan: 'Petrol Blue', Sky: 'Steel Blue', Blue: 'Sapphire', Indigo: 'Indigo',
                Violet: 'Eggplant', Magenta: 'Magenta', Pink: 'Raspberry' };
            return darkNames[family] || ('Dark ' + family);
        }
        if (l > 0.78) {
            const pastelNames = { Red: 'Rose Blush', Coral: 'Peach', Orange: 'Apricot', Amber: 'Buttercream',
                Yellow: 'Lemon Cream', Olive: 'Sage', Green: 'Mint Green', Teal: 'Sea Foam',
                Cyan: 'Aqua Mist', Sky: 'Powder Blue', Blue: 'Baby Blue', Indigo: 'Periwinkle',
                Violet: 'Lilac', Magenta: 'Mauve', Pink: 'Rose Petal' };
            return pastelNames[family] || ('Pastel ' + family);
        }
        if (s < 0.35) return 'Muted ' + family;

        const fancyMap = { Red: 'Crimson Red', Coral: 'Coral Pink', Orange: 'Saffron Orange',
            Amber: 'Honey Amber', Yellow: 'Sunset Gold', Olive: 'Olive Green', Green: 'Emerald Green',
            Teal: 'Teal', Cyan: 'Turquoise', Sky: 'Sky Blue', Blue: 'Ocean Blue', Indigo: 'Indigo',
            Violet: 'Royal Purple', Magenta: 'Magenta', Pink: 'Hot Pink' };
        return fancyMap[family] || family;
    }

    function makeVariants(hex) {
        return [
            lightenHex(hex, 50),
            lightenHex(hex, 25),
            hex,
            darkenHex(hex, 25),
            darkenHex(hex, 50)
        ];
    }

    // ---- Sample dominant color from each loaded yarn image ----
    // Uses a quantized histogram so the most common (mode) color wins,
    // not a noisy average that gets pulled toward the background.
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

            // Draw the FULL image stretched into the sample square so every
            // pixel of the yarn contributes regardless of natural dimensions.
            tctx.drawImage(img, 0, 0, img.naturalWidth, img.naturalHeight, 0, 0, sz, sz);
            const data = tctx.getImageData(0, 0, sz, sz).data;

            // Quantize into 6×6×6 = 216 buckets and weight by saturation
            const buckets = new Map();
            for (let i = 0; i < data.length; i += 4) {
                const r = data[i], g = data[i+1], b = data[i+2], a = data[i+3];
                if (a < 100) continue;
                if (r > 240 && g > 240 && b > 240) continue;   // background
                if (r < 12 && g < 12 && b < 12) continue;       // pure black noise

                const mx = Math.max(r, g, b);
                const mn = Math.min(r, g, b);
                const sat = mx === 0 ? 0 : (mx - mn) / mx;

                // Weight saturated/colored pixels far more than near-grays so
                // an off-white background bleed doesn't dominate the histogram.
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

            // Pick the bucket with the highest weight
            let best = null;
            buckets.forEach(v => { if (!best || v.w > best.w) best = v; });
            if (best && best.w > 0) {
                detectedHex = rgbToHex(best.r / best.w, best.g / best.w, best.b / best.w);
            }
        } catch (e) {
            // file:// often taints the canvas — fall through to filename fallback
        }

        if (!detectedHex) {
            // Deterministic fallback: hash the filename to a hue so each image
            // still gets a stable, unique-looking color even when sampling fails.
            const fname = (img.src || '').split('/').pop();
            let hash = 0;
            for (let i = 0; i < fname.length; i++) hash = (hash * 31 + fname.charCodeAt(i)) | 0;
            const hue = ((hash % 360) + 360) % 360;
            const sat = 55 + (Math.abs(hash >> 8) % 35);   // 55–90%
            const lit = 35 + (Math.abs(hash >> 16) % 30);  // 35–65%
            detectedHex = hslToHex(hue, sat, lit);
        }

        img.dominantHex = detectedHex;
        img.colorName = nameFromHex(detectedHex);
        img.variants = makeVariants(detectedHex);
    }

    function hslToHex(h, s, l) {
        s /= 100; l /= 100;
        const c = (1 - Math.abs(2 * l - 1)) * s;
        const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
        const m = l - c / 2;
        let r = 0, g = 0, b = 0;
        if (h < 60)       { r = c; g = x; }
        else if (h < 120) { r = x; g = c; }
        else if (h < 180) { g = c; b = x; }
        else if (h < 240) { g = x; b = c; }
        else if (h < 300) { r = x; b = c; }
        else              { r = c; b = x; }
        return rgbToHex((r + m) * 255, (g + m) * 255, (b + m) * 255);
    }

    yarnImageNames.forEach(name => {
        const img = new Image();
        img.src = "/images/yarns/" + name;
        img.addEventListener('load', () => sampleDominantColor(img));
        // Pre-fill in case sampling is delayed/blocked (CORS on file://)
        img.dominantHex = '#888888';
        img.colorName = 'Loading…';
        img.variants = ['#888888'];
        yarnImages.push(img);
    });
    function randomYarnImage() {
        return yarnImages[Math.floor(Math.random() * yarnImages.length)];
    }
    function randomMaterial() {
        return yarnMaterials[Math.floor(Math.random() * yarnMaterials.length)];
    }

    // Thread palette: color names, hex, materials, variant swatches
    const threadPalette = [
        { colorName: "Crimson Red",      hex: "#DC143C", material: "100% Mercerized Cotton",        variants: ["#DC143C","#B22222","#FF6B6B","#8B0000","#FF4444"] },
        { colorName: "Ocean Blue",       hex: "#1E90FF", material: "65/35 Poly-Cotton Blend",       variants: ["#1E90FF","#4169E1","#87CEEB","#00008B","#5DADE2"] },
        { colorName: "Emerald Green",    hex: "#2ECC71", material: "Pure Silk Filament",            variants: ["#2ECC71","#27AE60","#58D68D","#1E8449","#ABEBC6"] },
        { colorName: "Sunset Gold",      hex: "#F39C12", material: "Ring-Spun Cotton",              variants: ["#F39C12","#D4A017","#F7DC6F","#B7950B","#FDEBD0"] },
        { colorName: "Royal Purple",     hex: "#8E44AD", material: "Rayon/Viscose Blend",           variants: ["#8E44AD","#6C3483","#BB8FCE","#4A235A","#D7BDE2"] },
        { colorName: "Coral Pink",       hex: "#FF6F61", material: "Organic Cotton GOTS",           variants: ["#FF6F61","#E74C3C","#FDCB6E","#CB4335","#F5B7B1"] },
        { colorName: "Teal",             hex: "#008080", material: "Nylon 6.6 Bonded",              variants: ["#008080","#16A085","#48C9B0","#0E6655","#A3E4D7"] },
        { colorName: "Saffron Orange",   hex: "#FF7F50", material: "Combed Cotton Ne 40",           variants: ["#FF7F50","#E67E22","#EB984E","#CA6F1E","#FAD7A0"] },
        { colorName: "Indigo",           hex: "#3F51B5", material: "Core-Spun Polyester",           variants: ["#3F51B5","#283593","#7986CB","#1A237E","#C5CAE9"] },
        { colorName: "Olive Green",      hex: "#6B8E23", material: "Hemp/Cotton 50/50",             variants: ["#6B8E23","#556B2F","#9ACD32","#2E4600","#C5E1A5"] },
        { colorName: "Magenta",          hex: "#E91E63", material: "Metallic Lurex Thread",         variants: ["#E91E63","#C2185B","#F48FB1","#880E4F","#F8BBD0"] },
        { colorName: "Sky Blue",         hex: "#87CEEB", material: "Air-Jet Spun Polyester",        variants: ["#87CEEB","#4FC3F7","#03A9F4","#0277BD","#B3E5FC"] },
        { colorName: "Burnt Sienna",     hex: "#CD853F", material: "Linen/Flax Natural",            variants: ["#CD853F","#A0522D","#DEB887","#8B4513","#FFECD2"] },
        { colorName: "Chartreuse",       hex: "#7FFF00", material: "Recycled Polyester rPET",       variants: ["#7FFF00","#76FF03","#CCFF90","#64DD17","#B2FF59"] },
        { colorName: "Plum",             hex: "#9C27B0", material: "Bamboo/Tencel Blend",           variants: ["#9C27B0","#7B1FA2","#CE93D8","#4A148C","#E1BEE7"] },
        { colorName: "Rose Blush",       hex: "#FFB6C1", material: "Supima Cotton Premium",         variants: ["#FFB6C1","#FF69B4","#FFC0CB","#DB7093","#FFE4E1"] },
        { colorName: "Midnight Navy",    hex: "#191970", material: "Tex 40 Industrial Thread",      variants: ["#191970","#000080","#4169E1","#0D1B2A","#5C6BC0"] },
        { colorName: "Tangerine",        hex: "#FF6347", material: "Open-End Rotor Cotton",         variants: ["#FF6347","#FF4500","#FFA07A","#CC3300","#FFCCBC"] },
        { colorName: "Mint Green",       hex: "#98FF98", material: "Microfiber Polyester",          variants: ["#98FF98","#00C853","#69F0AE","#2E7D32","#C8E6C9"] },
        { colorName: "Slate Gray",       hex: "#708090", material: "Aramid Technical Thread",       variants: ["#708090","#546E7A","#90A4AE","#37474F","#CFD8DC"] },
        { colorName: "Burgundy",         hex: "#800020", material: "Worsted Wool Blend",            variants: ["#800020","#660018","#A0304A","#4A0012","#C07080"] },
        { colorName: "Turquoise",        hex: "#40E0D0", material: "Lyocell/Tencel",                variants: ["#40E0D0","#00CED1","#7FFFD4","#20B2AA","#AFEEEE"] },
        { colorName: "Lavender",         hex: "#B57EDC", material: "Bamboo Viscose",                variants: ["#B57EDC","#9966CC","#D8B4FE","#7B4FA0","#E8D0FE"] },
        { colorName: "Rust",             hex: "#B7410E", material: "Carded Cotton Ne 20",           variants: ["#B7410E","#A0360C","#D4601A","#8B3008","#E8A070"] },
        { colorName: "Peach",            hex: "#FFCBA4", material: "Modal/Cotton 60/40",            variants: ["#FFCBA4","#FFB380","#FFE0C0","#FF9960","#FFF0E0"] },
        { colorName: "Ivory",            hex: "#FFFFF0", material: "Ecru Raw Cotton",               variants: ["#FFFFF0","#F5F5DC","#FAF0E6","#FFF8DC","#FFFAF0"] },
        { colorName: "Charcoal",         hex: "#36454F", material: "Heavyweight Denim Thread",      variants: ["#36454F","#2F3F4F","#4A5A68","#1C2833","#5D6D7E"] },
        { colorName: "Lemon Yellow",     hex: "#FFF44F", material: "Spun Viscose Rayon",            variants: ["#FFF44F","#F4D03F","#FFEC8B","#D4AC0D","#FDEB71"] },
        { colorName: "Fuchsia",          hex: "#FF00FF", material: "High-Visibility Polyester",     variants: ["#FF00FF","#E91E63","#FF69B4","#B5008D","#FF77FF"] },
        { colorName: "Forest Green",     hex: "#228B22", material: "Heavy-Duty Outdoor Thread",     variants: ["#228B22","#1B5E20","#2E7D32","#0D3B11","#4CAF50"] },
        { colorName: "Aqua Mist",        hex: "#B0E0E6", material: "Microfiber Modal",              variants: ["#B0E0E6","#AFEEEE","#E0FFFF","#76D7EA","#D4F1F4"] },
        { colorName: "Caramel",          hex: "#AF6F09", material: "Raw Linen",                     variants: ["#AF6F09","#8B5A00","#D4883A","#6E4C00","#E0A55C"] },
        { colorName: "Rose Gold",        hex: "#E0B0A4", material: "Metallic Lamé Thread",          variants: ["#E0B0A4","#E8C2B7","#D49C8E","#C68F7D","#EBCDC0"] },
        { colorName: "Electric Blue",    hex: "#0D98BA", material: "Neon Reflective Polyester",     variants: ["#0D98BA","#00BFFF","#40C4E0","#0277BD","#B3DEEC"] },
        { colorName: "Mustard",          hex: "#FFDB58", material: "Cotton/Wool 70/30",             variants: ["#FFDB58","#E8C547","#FDE68A","#D4A017","#F9E79F"] },
        { colorName: "Cherry Red",       hex: "#D2042D", material: "Heavy-Duty Nylon 66",           variants: ["#D2042D","#B00020","#E63946","#7B1E20","#F08080"] },
        { colorName: "Steel Blue",       hex: "#4682B4", material: "Kevlar Aramid Technical",       variants: ["#4682B4","#1F618D","#7FB3D5","#154360","#AED6F1"] },
        { colorName: "Pumpkin",          hex: "#FF7518", material: "Ring-Spun Combed Cotton",       variants: ["#FF7518","#E67E22","#FFA75C","#D35400","#FDBA74"] },
        { colorName: "Lilac",            hex: "#C8A2C8", material: "Tencel Lyocell Blend",          variants: ["#C8A2C8","#B088AB","#E0BBE4","#9B7FA0","#F2D7F5"] },
        { colorName: "Emerald Shine",    hex: "#50C878", material: "Glossy Filament Silk",          variants: ["#50C878","#2ECC71","#82E0AA","#1E8449","#D4EFDF"] },
        { colorName: "Apricot",          hex: "#FBCEB1", material: "Pima Cotton Premium",           variants: ["#FBCEB1","#FDB97C","#FFDAB9","#E8A87C","#FCE5CD"] },
        { colorName: "Sapphire",         hex: "#0F52BA", material: "High-Tenacity Polyester",       variants: ["#0F52BA","#1E3A8A","#3B82F6","#0A2D6B","#7FABE4"] },
        { colorName: "Lime",             hex: "#BFFF00", material: "Fluorescent Core-Spun",         variants: ["#BFFF00","#A4D62A","#DEFF72","#7CB518","#E1F76A"] },
        { colorName: "Mauve",            hex: "#E0B0FF", material: "Bamboo Modal Blend",            variants: ["#E0B0FF","#C5A3D0","#F0CFFF","#A875B8","#EED5F7"] },
        { colorName: "Copper",           hex: "#B87333", material: "Jute/Cotton Rustic",            variants: ["#B87333","#A0522D","#CD7F32","#8B4513","#D7A66B"] },
        { colorName: "Bone White",       hex: "#F9F6EE", material: "Unbleached Cotton Slub",        variants: ["#F9F6EE","#EDEAE0","#FFFEF7","#D6D3C8","#FDFDF7"] },
        { colorName: "Hot Pink",         hex: "#FF1493", material: "Embroidery Rayon",              variants: ["#FF1493","#E91E63","#FF69B4","#C2185B","#FFC0CB"] },
        { colorName: "Moss Green",       hex: "#8A9A5B", material: "Recycled Cotton Yarn",          variants: ["#8A9A5B","#6B7839","#A5B57E","#4E5D25","#C4CFA0"] },
        { colorName: "Cobalt",           hex: "#0047AB", material: "Technical Nylon 6",             variants: ["#0047AB","#002D72","#3C6CE8","#001F5C","#7FA3E0"] },
        { colorName: "Amber",            hex: "#FFBF00", material: "Monofilament Polyamide",        variants: ["#FFBF00","#E6A500","#FFD700","#BF8F00","#FFE066"] },
        { colorName: "Periwinkle",       hex: "#CCCCFF", material: "Silk-Viscose Blend",            variants: ["#CCCCFF","#AAAAFF","#E0E0FF","#8888FF","#EDEDFF"] },
        { colorName: "Terracotta",       hex: "#E2725B", material: "Hand-Woven Wool",               variants: ["#E2725B","#C65038","#F39070","#A03D2C","#F4B29F"] },
        { colorName: "Obsidian",         hex: "#1C1C1C", material: "Para-Aramid Fire Retardant",    variants: ["#1C1C1C","#000000","#3A3A3A","#101010","#5A5A5A"] },
        { colorName: "Baby Blue",        hex: "#89CFF0", material: "Soft-Touch Cotton Jersey",      variants: ["#89CFF0","#A3D8F4","#B3E0F7","#5CB0D8","#D4EEFA"] },
        { colorName: "Spring Green",     hex: "#00FA9A", material: "Bright Fluorescent Nylon",      variants: ["#00FA9A","#00C878","#7FFFD4","#008B4D","#C6F8DB"] },
        { colorName: "Wine",             hex: "#722F37", material: "Cashmere Wool Blend",           variants: ["#722F37","#4A1820","#9B4B55","#3B1317","#B57780"] },
        { colorName: "Goldenrod",        hex: "#DAA520", material: "Heavyweight Upholstery Thread", variants: ["#DAA520","#B8860B","#F4C542","#8B6914","#F8D060"] },
        { colorName: "Sea Foam",         hex: "#93E9BE", material: "Organic Hemp Yarn",             variants: ["#93E9BE","#7DD3A0","#B8F0D4","#5BBE8B","#D0F5E3"] },
        { colorName: "Maroon",           hex: "#800000", material: "Heritage Cotton Drill",         variants: ["#800000","#5C0010","#A0303A","#3B0005","#B3505C"] },
        { colorName: "Cerulean",         hex: "#007BA7", material: "Water-Repellent Polyester",     variants: ["#007BA7","#006080","#2E9BBE","#003D52","#6EBBD4"] },
    ];

    // Manufacturer names pool for random assignment
    const mfgNames = [
        "Coats Group PLC", "A&E (American & Efird)", "Madeira Garnfabrik", "Amann Group",
        "Raj Silk Mills", "Fujix Ltd.", "Nantong Xinhua Thread Co.", "Brildor S.L.",
        "SilCon Thread Works", "Nylon Fibers Corp.", "ThreadSol Africa", "Phong Phu Thread",
        "Suraj Polycot Industries", "Guttermann Textil GmbH", "Xinhua Silk Thread Co.",
        "Tamura Thread Co.", "Segussa Fili S.p.A.", "Noor Textile Mills", "Pacific Thread Corp.",
        "Hemkunt Yarns Pvt. Ltd.", "Bavaria Faden GmbH", "Golden Spool Ltd.", "Atlas Thread Co.",
        "Nakamura Fibers Inc.", "Andean Thread Works", "Sahara Filaments", "Nordic Thread AB",
        "Orion Industrial Threads", "Kerala Silk Threads", "Majestic Yarn Co."
    ];
    function randomMfg() { return mfgNames[Math.floor(Math.random() * mfgNames.length)]; }

    let threads = [];
    let mouse = { x: -9999, y: -9999 };
    let hoveredThread = null;
    let hoverTimer = null;
    let tooltipVisible = false;

    // Pre-computed RGB cache for performance
    const rgbCache = {};

    // ===== COLOR UTILS (optimized) =====
    function hexToRgb(hex) {
        if (rgbCache[hex]) return rgbCache[hex];
        const h = hex.replace('#','');
        const result = { r: parseInt(h.substring(0,2),16), g: parseInt(h.substring(2,4),16), b: parseInt(h.substring(4,6),16) };
        rgbCache[hex] = result;
        return result;
    }
    function rgbToHex(r,g,b) {
        return '#' + ((1<<24)+(Math.max(0,Math.min(255,r|0))<<16)+(Math.max(0,Math.min(255,g|0))<<8)+Math.max(0,Math.min(255,b|0))).toString(16).slice(1);
    }
    function lightenHex(hex, amt) { const c = hexToRgb(hex); return rgbToHex(c.r+amt, c.g+amt, c.b+amt); }
    function darkenHex(hex, amt) { const c = hexToRgb(hex); return rgbToHex(c.r-amt, c.g-amt, c.b-amt); }
    function lerpColor(hA, hB, t) {
        const a = hexToRgb(hA), b = hexToRgb(hB);
        return rgbToHex(a.r+(b.r-a.r)*t, a.g+(b.g-a.g)*t, a.b+(b.b-a.b)*t);
    }

    // Build a thread `data` object from a yarn image (color, name, variants, material)
    function dataFromYarn(yarnImage) {
        return {
            colorName: yarnImage.colorName || 'Natural',
            hex: yarnImage.dominantHex || '#888888',
            material: randomMaterial(),
            variants: yarnImage.variants || ['#888888']
        };
    }

    // ===== THREAD CLASS =====
    class Thread {
        constructor(paletteEntry, index) {
            this.yarnImage = randomYarnImage();
            const data = dataFromYarn(this.yarnImage);
            this.data = data;
            this.currentColor = data.hex;
            this.displayColor = data.hex;
            this.angle = 30;
            this.angleRad = this.angle * Math.PI / 180;
            this.cosA = Math.cos(this.angleRad);
            this.sinA = Math.sin(this.angleRad);

            // Depth: 0 = far (small, slow, faint), 1 = near (big, fast, vivid)
            // Non-linear distribution so most threads feel mid-distance
            this.depth = Math.pow(Math.random(), 0.6);

            // Near threads are thicker, farther ones thinner
            this.baseWidth = 2 + this.depth * 14;
            this.width = this.baseWidth;

            this.x = 0;
            this.y = 0;
            this.baseX = 0;
            this.baseY = 0;
            this.length = 0;
            this.scale = 1;
            this.targetScale = 1;
            // Draw nearer threads in front of farther ones
            this.zIndex = this.depth * 10;
            this.targetZIndex = this.zIndex;

            // Farther threads fade out like haze, nearer ones stay vivid
            this.opacity = 0.25 + this.depth * 0.75;
            this.baseOpacity = this.opacity;
            this.targetOpacity = this.opacity;

            this.bobOffset = Math.random() * Math.PI * 2;
            this.bobSpeed = 0.2 + Math.random() * 0.3;
            this.bobAmt = 1 + Math.random() * 2;

            // Camera-flight effect: near threads whoosh by fast, far threads drift slowly
            this.scrollSpeed = 3 + this.depth * 15;

            this.manufacturer = randomMfg();
            this.index = index;
            this.picked = false;
        }

        place(w, h, fromInflow) {
            this.length = h * 3.5;
            if (fromInflow) {
                // Threads flow up-left (local axis), so the inflow side is bottom + right.
                // Pick an edge weighted by the respective velocity component magnitudes.
                const vx = Math.abs(this.sinA);
                const vy = Math.abs(this.cosA);
                const bottomChance = vy / (vx + vy);
                if (Math.random() < bottomChance) {
                    // Spawn anchor just below the bottom edge
                    this.baseX = -this.length * this.sinA + Math.random() * (w + this.length * this.sinA * 1.4);
                    this.baseY = h + Math.random() * 120;
                } else {
                    // Spawn anchor just past the right edge
                    this.baseX = w + Math.random() * 120;
                    this.baseY = -this.length * this.cosA * 0.3 + Math.random() * h;
                }
            } else {
                // Initial placement: spread anchors across a region larger than viewport
                this.baseX = -this.length * this.sinA + Math.random() * (w + this.length * this.sinA * 1.4);
                this.baseY = -this.length * this.cosA * 0.3 + Math.random() * (h + this.length * this.cosA * 0.6);
            }
            this.x = this.baseX;
            this.y = this.baseY;
        }

        // Recycle: new random props, spawn from below
        recycle(w, h) {
            this.yarnImage = randomYarnImage();
            this.data = dataFromYarn(this.yarnImage);
            this.currentColor = this.data.hex;
            this.displayColor = this.data.hex;

            // Re-roll depth and dependent properties
            this.depth = Math.pow(Math.random(), 0.6);
            this.baseWidth = 2 + this.depth * 14;
            this.width = this.baseWidth;

            this.angle = 30;
            this.angleRad = this.angle * Math.PI / 180;
            this.cosA = Math.cos(this.angleRad);
            this.sinA = Math.sin(this.angleRad);

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
            this.manufacturer = randomMfg();
            this.place(w, h, true);
        }

        containsPoint(px, py) {
            // Inverse-transform mouse into thread's local coordinate space
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
            const topExtend = h * 0.7; // matches the visual extension above the anchor
            return localX > -r - 4 && localX < r + 4
                && localY > -topExtend - 4 && localY < h + r + 4;
        }

        update(time, dt) {
            // Scroll along local axis (up along the thread's own length) when not picked
            if (!this.picked) {
                this.baseX -= this.sinA * this.scrollSpeed * dt;
                this.baseY -= this.cosA * this.scrollSpeed * dt;
            }
            // Bob perpendicular to the thread for a side-to-side sway
            const bob = Math.sin(time * this.bobSpeed + this.bobOffset) * this.bobAmt;
            this.x = this.baseX + this.cosA * bob;
            this.y = this.baseY - this.sinA * bob;

            this.scale += (this.targetScale - this.scale) * 0.1;
            this.opacity += (this.targetOpacity - this.opacity) * 0.1;
            this.zIndex += (this.targetZIndex - this.zIndex) * 0.12;
            if (this.displayColor !== this.currentColor) {
                this.displayColor = lerpColor(this.displayColor, this.currentColor, 0.08);
            }
        }

        // Check if the thread has fully left the viewport on the upstream side (top-left)
        isOffScreen() {
            // The bottom tip of the thread in world coords
            const tipX = this.x + this.length * this.sinA;
            const tipY = this.y + this.length * this.cosA;
            return tipX < -80 || tipY < -80;
        }

        draw() {
            const img = this.yarnImage;
            // Wait until the image is loaded before drawing
            if (!img || !img.complete || img.naturalWidth === 0) return;

            const s = this.scale;
            // Use image's natural height as base thickness, scaled by depth + hover
            const thickness = (8 + this.depth * 28) * s;
            const length = this.length * s;

            ctx.save();
            ctx.translate(this.x, this.y);
            ctx.rotate(this.angleRad);
            ctx.globalAlpha = Math.min(this.opacity, 1);

            // The yarn images are horizontal strands. Our thread axis is vertical
            // (drawn from y=0 going down to y=length). Draw the image rotated 90deg
            // so the long axis of the image aligns with the thread's length.
            // We also tile the image along the length so it repeats naturally.
            const imgW = img.naturalWidth;   // image's "long" dimension
            const imgH = img.naturalHeight;  // image's "short" dimension (cross-section)

            // After our 90deg rotation: image width spans the thread's length axis.
            // We want the image's height (cross-section) to render at our `thickness`.
            const tileLen = imgW * (thickness / imgH);

            // Apply 90deg rotation: image's long axis goes down (positive Y in local)
            ctx.rotate(Math.PI / 2);
            // After this rotate, drawImage(x, y, w, h) maps:
            //   x along the thread's length (down originally), y across the thread's width
            // Tile along the length, extending past both the top end and bottom end.
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

        changeColor(hex) {
            this.currentColor = hex;
        }
    }

    // ===== SPATIAL GRID for fast hit detection =====
    const GRID_SIZE = 80;
    let gridCols, gridRows, grid;

    function buildGrid() {
        gridCols = Math.ceil(canvas.width / GRID_SIZE) + 1;
        gridRows = Math.ceil(canvas.height / GRID_SIZE) + 1;
        grid = new Array(gridCols * gridRows);
        for (let i = 0; i < grid.length; i++) grid[i] = [];

        for (const t of threads) {
            // Compute bounding box of the rotated thread
            const cx = t.x;
            const cy = t.y + t.length / 2;
            const hw = t.width / 2 + t.length * Math.abs(t.sinA) / 2;
            const hh = t.length * Math.abs(t.cosA) / 2 + t.width / 2;
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
        // Check in reverse (higher zIndex first)
        for (let i = cell.length - 1; i >= 0; i--) {
            if (cell[i].containsPoint(px, py)) return cell[i];
        }
        return null;
    }

    // ===== SETUP =====
    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        createThreads();
    }

    function createThreads() {
        const w = canvas.width;
        const h = canvas.height;
        threads = [];
        for (let i = 0; i < THREAD_COUNT; i++) {
            const pal = threadPalette[i % threadPalette.length];
            const t = new Thread(pal, i);
            t.place(w, h, false); // initial: spread across viewport
            threads.push(t);
        }
        buildGrid();
    }

    // ===== TOOLTIP =====
    const tooltipMfg = document.getElementById('tooltipMfg');

    function showTooltip(thread) {
        // If the yarn image has finished loading since this thread was created,
        // sync the latest color name + variants so we show the actual yarn color.
        const img = thread.yarnImage;
        if (img && img._sampled && thread.data.hex !== img.dominantHex) {
            thread.data.colorName = img.colorName;
            thread.data.hex = img.dominantHex;
            thread.data.variants = img.variants;
            thread.currentColor = img.dominantHex;
            thread.displayColor = img.dominantHex;
        }
        const d = thread.data;
        tooltipPreview.style.background = thread.displayColor;
        tooltipName.textContent = d.colorName;
        tooltipMfg.textContent = thread.manufacturer;
        tooltipMaterial.textContent = d.material;

        tooltipColors.innerHTML = '';
        d.variants.forEach(v => {
            const dot = document.createElement('div');
            dot.className = 'tooltip-color-dot' + (v === thread.currentColor ? ' active' : '');
            dot.style.background = v;
            dot.addEventListener('click', (e) => {
                e.stopPropagation();
                thread.changeColor(v);
                tooltipColors.querySelectorAll('.tooltip-color-dot').forEach(el => el.classList.remove('active'));
                dot.classList.add('active');
                tooltipPreview.style.background = v;
            });
            tooltipColors.appendChild(dot);
        });

        positionTooltip();
        tooltip.classList.add('visible');
        tooltipVisible = true;
    }

    function positionTooltip() {
        // Measure actual tooltip size (offsetWidth/Height ignores the scale transform)
        const tw = tooltip.offsetWidth || 240;
        const th = tooltip.offsetHeight || 180;
        const gap = 16;
        const margin = 12;
        const mx = mouse.x;
        const my = mouse.y;
        const vw = window.innerWidth;
        const vh = window.innerHeight;

        // Default: to the right and below the pointer
        let left = mx + gap;
        let top = my + gap;

        // Flip horizontally if it would overflow the right edge
        if (left + tw + margin > vw) {
            left = mx - tw - gap;
        }
        // Flip vertically if it would overflow the bottom edge
        if (top + th + margin > vh) {
            top = my - th - gap;
        }

        // Final clamp so it never goes off-screen (handles pointer in corners)
        left = Math.max(margin, Math.min(left, vw - tw - margin));
        top = Math.max(margin, Math.min(top, vh - th - margin));

        tooltip.style.left = left + 'px';
        tooltip.style.top = top + 'px';
    }

    function hideTooltip() {
        tooltip.classList.remove('visible');
        tooltipVisible = false;
    }

    // ===== MOUSE =====
    canvas.addEventListener('mousemove', (e) => {
        mouse.x = e.clientX;
        mouse.y = e.clientY;

        const found = findThreadAt(mouse.x, mouse.y);

        if (found !== hoveredThread) {
            if (hoveredThread) hoveredThread.setHovered(false);
            hoveredThread = found;
            if (hoveredThread) hoveredThread.setHovered(true);
            clearTimeout(hoverTimer);
            hideTooltip();
            if (hoveredThread) {
                hoverTimer = setTimeout(() => {
                    if (hoveredThread) showTooltip(hoveredThread);
                }, 1200);
            }
        }
    });

    canvas.addEventListener('mouseleave', () => {
        mouse.x = -9999;
        mouse.y = -9999;
        if (hoveredThread) hoveredThread.setHovered(false);
        hoveredThread = null;
        clearTimeout(hoverTimer);
        hideTooltip();
    });

    // Click any floating yarn thread to open the picker.
    canvas.style.cursor = 'pointer';
    canvas.addEventListener('click', (e) => {
        const found = findThreadAt(e.clientX, e.clientY) || hoveredThread;
        if (found && typeof window.openYarnPicker === 'function') {
            window.openYarnPicker(found);
        } else if (!found) {
            openFabricStudio();
        }
    });

    tooltip.addEventListener('mouseenter', () => clearTimeout(hoverTimer));
    tooltip.addEventListener('mouseleave', () => {
        hideTooltip();
        if (hoveredThread) { hoveredThread.setHovered(false); hoveredThread = null; }
    });

    // ===== ANIMATION LOOP =====
    let frameCount = 0;
    let lastTime = 0;

    function animate(timestamp) {
        const time = timestamp / 1000;
        const dt = Math.min(time - lastTime, 0.1); // cap delta to avoid jumps
        lastTime = time;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const w = canvas.width;
        const h = canvas.height;

        // Update all threads, recycle any that scrolled off the top
        for (let i = 0; i < threads.length; i++) {
            threads[i].update(time, dt);
            if (threads[i].isOffScreen() && threads[i] !== hoveredThread) {
                threads[i].recycle(w, h);
            }
        }

        // Rebuild spatial grid every 15 frames (threads are moving now)
        if (frameCount++ % 15 === 0) buildGrid();

        // Sort by zIndex for draw order
        threads.sort((a, b) => a.zIndex - b.zIndex);
        for (let i = 0; i < threads.length; i++) threads[i].draw();

        if (tooltipVisible && hoveredThread) {
            tooltipPreview.style.background = hoveredThread.displayColor;
        }

        requestAnimationFrame(animate);
    }

    // ===== START =====
    window.addEventListener('resize', () => {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        // Don't recreate threads on resize, just rebuild the grid
        buildGrid();
    });
    resize();
    animate(0);
})();

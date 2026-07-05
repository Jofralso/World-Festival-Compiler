/* FestivalWorld Builder v2 — Geo-powered wizard UI */

const state = {
  festivalName: 'My Festival',
  selectedPlace: null,       // {name, lat, lng, bounds}
  diameterKm: 10,
  terrainData: null,         // result from /gui/terrain
  rawImageData: null,        // Uint8Array for 3D elevation lookups
  settings: {
    style: 'electronic festival',
    worldName: 'festival_world',
    srtmRes: 'SRTMGL3',
  },
};

let editMap = null;           // Leaflet map (screen 2)
let editCircle = null;        // Diameter circle on edit map
let world3d = null;           // WorldPreview3D instance

// ─────────────────────────────────────────────
// WorldPreview3D — Three.js terrain viewer
// ─────────────────────────────────────────────

class WorldPreview3D {
  constructor() {
    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.terrain = null;
    this.water = null;
    this.markers = [];
    this.animId = null;
    this.visible = false;
    this.container = null;
  }

  init(containerId) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;
    const w = this.container.clientWidth || 800;
    const h = this.container.clientHeight || 500;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x87CEEB); // sky blue
    this.scene.fog = new THREE.Fog(0x87CEEB, 800, 2000);

    this.camera = new THREE.PerspectiveCamera(55, w / h, 0.1, 5000);
    this.camera.position.set(150, 180, 200);

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(w, h);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.container.innerHTML = '';
    this.container.appendChild(this.renderer.domElement);

    this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.target.set(0, 60, 0);
    this.controls.maxPolarAngle = Math.PI / 2.1;
    this.controls.minDistance = 10;
    this.controls.maxDistance = 3000;

    // Sun
    const sun = new THREE.DirectionalLight(0xffeedd, 1.6);
    sun.position.set(200, 300, 100);
    sun.castShadow = true;
    sun.shadow.mapSize.width = 1024;
    sun.shadow.mapSize.height = 1024;
    this.scene.add(sun);

    const hemi = new THREE.HemisphereLight(0x87CEEB, 0x556b2f, 0.6);
    this.scene.add(hemi);

    const fill = new THREE.DirectionalLight(0xccddff, 0.3);
    fill.position.set(-100, 50, -80);
    this.scene.add(fill);

    window.addEventListener('resize', () => this._onResize());
  }

  dispose() {
    if (this.animId) cancelAnimationFrame(this.animId);
    if (this.renderer) this.renderer.dispose();
    if (this.container) this.container.innerHTML = '';
    this.visible = false;
    this.scene = null;
  }

  show() {
    if (this.container) this.container.style.display = 'block';
    this.visible = true;
    this._animate();
  }

  hide() {
    if (this.container) this.container.style.display = 'none';
    this.visible = false;
    if (this.animId) { cancelAnimationFrame(this.animId); this.animId = null; }
  }

  _animate() {
    if (!this.visible) return;
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.animId = requestAnimationFrame(() => this._animate());
  }

  _onResize() {
    if (!this.container || !this.renderer) return;
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }

  buildTerrain(heightmapData, plan) {
    if (!this.scene) return;
    this._clearScene();

    const data = heightmapData;
    const cols = data.width;
    const rows = data.height;
    const pixels = data.pixels;

    // Build geometry
    const geo = new THREE.BufferGeometry();
    const vertexCount = (cols - 1) * (rows - 1) * 6;
    const positions = new Float32Array(vertexCount * 3);
    const colors = new Float32Array(vertexCount * 3);

    let idx = 0;
    for (let z = 0; z < rows - 1; z++) {
      for (let x = 0; x < cols - 1; x++) {
        const h00 = pixels[(z) * cols + x];
        const h10 = pixels[(z) * cols + (x + 1)];
        const h01 = pixels[(z + 1) * cols + x];
        const h11 = pixels[(z + 1) * cols + (x + 1)];
        // Two triangles per quad
        const verts = [
          [x, h00, z], [x + 1, h10, z], [x, h01, z + 1],
          [x + 1, h10, z], [x + 1, h11, z + 1], [x, h01, z + 1],
        ];
        for (const v of verts) {
          positions[idx * 3] = v[0];
          positions[idx * 3 + 1] = v[1];
          positions[idx * 3 + 2] = v[2];
          const c = this._elevationColor(v[1], h00, h10, h01, h11);
          colors[idx * 3] = c.r;
          colors[idx * 3 + 1] = c.g;
          colors[idx * 3 + 2] = c.b;
          idx++;
        }
      }
    }

    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();

    const mat = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.7,
      metalness: 0.1,
      flatShading: false,
      side: THREE.DoubleSide,
    });
    this.terrain = new THREE.Mesh(geo, mat);
    this.scene.add(this.terrain);

    // Water plane
    const seaLevel = this._estimateSeaLevel(pixels);
    const waterGeo = new THREE.PlaneGeometry(cols, rows);
    const waterMat = new THREE.MeshStandardMaterial({
      color: 0x1a4a8a,
      transparent: true,
      opacity: 0.45,
      side: THREE.DoubleSide,
      roughness: 0.1,
      metalness: 0.3,
    });
    this.water = new THREE.Mesh(waterGeo, waterMat);
    this.water.rotation.x = -Math.PI / 2;
    this.water.position.set(cols / 2 - 0.5, seaLevel, rows / 2 - 0.5);
    this.scene.add(this.water);

    // Add markers from plan
    if (plan) this._addMarkers(plan, seaLevel);

    // Center camera
    const cx = cols / 2;
    const cz = rows / 2;
    const maxH = Math.max(...pixels);
    const dist = Math.max(cols, rows) * 0.7;
    this.camera.position.set(cx + dist * 0.5, maxH + dist * 0.4, cz + dist * 0.6);
    this.controls.target.set(cx, seaLevel + 5, cz);
    this.controls.update();
  }

  buildStructures(structures, seaLevel) {
    if (!this.scene || !structures) return;
    const blockColors = {
      0: 0x000000, 1: 0x808080, 2: 0x5d8a3c, 3: 0x8b5e3c,
      5: 0xc8a06e, 20: 0xadd8e6, 35: 0xcccccc, 41: 0xffd700,
      42: 0xc0c0c0, 44: 0xaaaaaa, 45: 0xb85c3c, 50: 0xffaa00,
      53: 0xc8a06e, 57: 0x00ffff, 76: 0xff4444, 85: 0x8b5e3c,
      89: 0xffff88, 98: 0x999999, 123: 0xff6600, 134: 0x6b4c2a,
      169: 0x88ffff, 172: 0xcc8855, 179: 0xd4853a, 251: 0xdddddd,
      16: 0x333333, 24: 0xd4b87a,
    };
    for (const s of structures) {
      const size = 0.8;
      const geo = new THREE.BoxGeometry(size, size, size);
      const col = blockColors[s.block_id] || 0xcccccc;
      const mat = new THREE.MeshStandardMaterial({ color: col, roughness: 0.6 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(s.x + 0.5, s.y + 0.5, s.z + 0.5);
      this.scene.add(mesh);
      this.markers.push(mesh);
    }
  }

  _clearScene() {
    if (this.terrain) { this.scene.remove(this.terrain); this.terrain = null; }
    if (this.water) { this.scene.remove(this.water); this.water = null; }
    this.markers.forEach(m => this.scene.remove(m));
    this.markers = [];
  }

  _elevationColor(h, ...neighbors) {
    const all = [h, ...neighbors];
    const mn = Math.min(...all);
    const mx = Math.max(...all);
    const range = mx - mn || 1;
    const t = (h - mn) / range;
    const color = new THREE.Color();
    // Minecraft-like biomes: water → sand → grass → forest → stone → snow
    if (t < 0.05) color.setHex(0x3c7fbd);
    else if (t < 0.12) color.lerpColors(new THREE.Color(0x3c7fbd), new THREE.Color(0xdbc07f), (t - 0.05) / 0.07);
    else if (t < 0.30) color.lerpColors(new THREE.Color(0xdbc07f), new THREE.Color(0x7ebe5a), (t - 0.12) / 0.18);
    else if (t < 0.55) color.lerpColors(new THREE.Color(0x7ebe5a), new THREE.Color(0x5a9e3f), (t - 0.30) / 0.25);
    else if (t < 0.75) color.lerpColors(new THREE.Color(0x5a9e3f), new THREE.Color(0x8b7d6b), (t - 0.55) / 0.20);
    else if (t < 0.90) color.lerpColors(new THREE.Color(0x8b7d6b), new THREE.Color(0x9e9e9e), (t - 0.75) / 0.15);
    else color.lerpColors(new THREE.Color(0x9e9e9e), new THREE.Color(0xffffff), (t - 0.90) / 0.10);
    return color;
  }

  _estimateSeaLevel(pixels) {
    const sorted = [...pixels].sort((a, b) => a - b);
    return sorted[Math.floor(sorted.length * 0.08)];
  }

  _addMarkers(plan, seaLevel) {
    const addMarker = (x, z, color, label, radius) => {
      const group = new THREE.Group();
      const sphere = new THREE.Mesh(
        new THREE.SphereGeometry(radius * 0.12, 12, 12),
        new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.3 })
      );
      sphere.position.y = seaLevel + radius * 0.3;
      group.add(sphere);
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(radius * 0.12, radius * 0.16, 24),
        new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.2, side: THREE.DoubleSide, transparent: true, opacity: 0.4 })
      );
      ring.rotation.x = -Math.PI / 2;
      ring.position.y = seaLevel + 0.5;
      group.add(ring);
      group.position.set(x, 0, z);
      this.scene.add(group);
      this.markers.push(group);
    };

    if (plan.main_stage) {
      addMarker(plan.main_stage.x, plan.main_stage.z, 0xff3333, 'Main', plan.main_stage.radius);
    }
    (plan.secondary_stages || []).forEach(s => {
      addMarker(s.x, s.z, 0xff8833, s.name, s.radius);
    });
    (plan.camping || []).forEach(c => {
      addMarker(c.x + c.width / 2, c.z + c.depth / 2, 0xffdd44, 'Camp', Math.min(c.width, c.depth) / 2);
    });
    if (plan.entrance) {
      addMarker(plan.entrance[0], plan.entrance[1], 0x44ff44, 'Entrance', 12);
    }
    if (plan.spawn) {
      addMarker(plan.spawn[0], plan.spawn[1], 0x44aaff, 'Spawn', 8);
    }
  }
}

// ─────────────────────────────────────────────
// Screen management
// ─────────────────────────────────────────────

// ─────────────────────────────────────────────
// 1. SCREEN MANAGEMENT
// ─────────────────────────────────────────────

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

function setStatus(msg) {
  document.getElementById('status-text').textContent = msg;
}

// ─────────────────────────────────────────────
// 2. SEARCH SCREEN
// ─────────────────────────────────────────────

let searchMap = null;
let searchMarker = null;

function initSearchScreen() {
  // Init map with default world view
  searchMap = L.map('search-map', { zoomControl: true, attributionControl: false, zoom: 3 });
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
  }).addTo(searchMap);
  searchMap.setView([20, 0], 3); // default world view

  // Try geolocation
  if ('geolocation' in navigator) {
    navigator.geolocation.getCurrentPosition(
      pos => {
        const { latitude, longitude } = pos.coords;
        searchMap.setView([latitude, longitude], 12);
        if (searchMarker) {
          searchMarker.setLatLng([latitude, longitude]);
        } else {
          searchMarker = L.marker([latitude, longitude]).addTo(searchMap);
        }
      },
      () => {} // silently ignore if denied
    );
  }

  // Search
  document.getElementById('search-btn').addEventListener('click', doSearch);
  document.getElementById('search-query').addEventListener('keydown', e => {
    if (e.key === 'Enter') doSearch();
  });

  // Diameter slider
  document.getElementById('diameter-slider').addEventListener('input', e => {
    state.diameterKm = parseInt(e.target.value);
    document.getElementById('diameter-label').textContent = state.diameterKm + ' km';
  });

  document.getElementById('step1-next').addEventListener('click', () => {
    if (!state.selectedPlace) return;
    state.festivalName = document.getElementById('festival-name').value.trim() || 'My Festival';
    goToEditScreen();
  });

  // Festival name
  document.getElementById('festival-name').addEventListener('input', e => {
    state.festivalName = e.target.value.trim() || 'My Festival';
  });
}

async function doSearch() {
  const query = document.getElementById('search-query').value.trim();
  if (!query) return;

  const btn = document.getElementById('search-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>';
  setStatus('Searching...');

  try {
    const form = new FormData();
    form.append('query', query);
    form.append('limit', '6');
    const r = await fetch('/gui/search', { method: 'POST', body: form });
    const data = await r.json();
    showSearchResults(data.results || []);
  } catch (e) {
    document.getElementById('search-results').innerHTML =
      `<p style="color:var(--red);font-size:13px;">Search failed: ${e.message}</p>`;
    setStatus('Error');
  } finally {
    btn.disabled = false; btn.innerHTML = '<i class="fas fa-search"></i>';
    setStatus('Ready');
  }
}

function showSearchResults(results) {
  const container = document.getElementById('search-results');
  container.innerHTML = '';

  if (!results.length) {
    container.innerHTML = '<p style="color:var(--text3);font-size:13px;">No results found. Try a different query.</p>';
    return;
  }

  results.forEach((place, i) => {
    const div = document.createElement('div');
    div.className = 'search-result-item' + (i === 0 ? ' selected' : '');
    div.innerHTML = `
      <div class="sri-icon"><i class="fas fa-map-marker-alt"></i></div>
      <div class="sri-info">
        <div class="sri-name">${place.name}</div>
        <div class="sri-coords">${place.lat.toFixed(4)}, ${place.lng.toFixed(4)} &middot; ${place.type}</div>
      </div>
      <div class="sri-check"><i class="fas fa-check-circle"></i></div>
    `;
    div.addEventListener('click', () => {
      document.querySelectorAll('.search-result-item').forEach(el => el.classList.remove('selected'));
      div.classList.add('selected');
      selectPlace(place);
    });
    container.appendChild(div);
  });

  // Auto-select first
  selectPlace(results[0]);
}

function selectPlace(place) {
  state.selectedPlace = place;

  if (!searchMarker) {
    searchMarker = L.marker([place.lat, place.lng]).addTo(searchMap);
  } else {
    searchMarker.setLatLng([place.lat, place.lng]);
  }
  searchMap.setView([place.lat, place.lng], 12);

  // Enable next button
  document.getElementById('step1-next').disabled = false;
}

// ─────────────────────────────────────────────
// 3. EDIT SCREEN
// ─────────────────────────────────────────────

async function goToEditScreen() {
  showScreen('screen-edit');
  document.getElementById('edit-content').style.display = 'none';
  document.getElementById('terrain-loading').style.display = 'block';
  setStatus('Fetching terrain...');

  // Set config from search
  document.getElementById('edit-style').value = state.settings.style;
  document.getElementById('edit-world-name').value = state.settings.worldName;

  try {
    // Fetch terrain
    const form = new FormData();
    form.append('lat', state.selectedPlace.lat);
    form.append('lng', state.selectedPlace.lng);
    form.append('diameter_km', state.diameterKm);
    form.append('srtm_resolution', state.settings.srtmRes);

    const r = await fetch('/gui/terrain', { method: 'POST', body: form });
    if (!r.ok) {
      const e = await r.json();
      throw new Error(e.detail || r.statusText);
    }
    state.terrainData = await r.json();

    document.getElementById('terrain-loading').style.display = 'none';
    document.getElementById('edit-content').style.display = 'block';
    setStatus('Terrain loaded');

    // Show info
    const info = state.terrainData;
    document.getElementById('edit-terrain-info').innerHTML = `
      <div><strong>Terrain:</strong> ${info.terrain}</div>
      <div><strong>Flat zones:</strong> ${info.flat_zones_count}</div>
      <div><strong>Size:</strong> ${(info.diameter_km * 1000).toFixed(0)}&times;${(info.diameter_km * 1000).toFixed(0)} blocks</div>
    `;
    document.getElementById('edit-feature-info').innerHTML = `
      <div><i class="fas fa-road" style="width:16px;color:var(--text2)"></i> ${info.feature_counts.roads} roads</div>
      <div><i class="fas fa-building" style="width:16px;color:var(--text2)"></i> ${info.feature_counts.buildings} buildings</div>
      <div><i class="fas fa-water" style="width:16px;color:var(--text2)"></i> ${info.feature_counts.water_bodies} water bodies</div>
      <div><i class="fas fa-tree" style="width:16px;color:var(--text2)"></i> ${info.feature_counts.parks} parks</div>
    `;

    // Init edit map
    initEditMap();

    // Init 3D preview from heightmap raw data
    init3DPreview(info);

    // Show preview images
    const strip = document.getElementById('edit-preview-strip');
    strip.style.display = 'flex';
    strip.innerHTML = '';
    for (const [key, val] of Object.entries(info.images || {})) {
      if (key === 'raw') continue; // skip raw in strip
      const img = document.createElement('img');
      img.src = val;
      img.title = key;
      img.style.width = '180px';
      img.style.height = '120px';
      img.style.objectFit = 'cover';
      img.style.borderRadius = '6px';
      img.style.cursor = 'pointer';
      img.addEventListener('click', () => openLightbox(val, key));
      strip.appendChild(img);
    }

  } catch (e) {
    document.getElementById('terrain-loading').innerHTML =
      `<p style="color:var(--red)">Failed to load terrain: ${e.message}</p>
       <button class="btn btn-secondary" onclick="goToEditScreen()" style="margin-top:12px">Retry</button>`;
    setStatus('Error');
  }

  // Bind edit screen buttons
  document.getElementById('step2-back').addEventListener('click', () => {
    showScreen('screen-search');
    setStatus('Ready');
  });
  document.getElementById('step2-build').addEventListener('click', startBuild);

  // Config changes
  document.getElementById('edit-style').addEventListener('change', e => {
    state.settings.style = e.target.value;
  });
  document.getElementById('edit-world-name').addEventListener('change', e => {
    state.settings.worldName = e.target.value.trim() || 'festival_world';
  });
  document.getElementById('edit-res').addEventListener('change', e => {
    state.settings.srtmRes = e.target.value;
  });

  // Festival image search
  document.getElementById('festival-image-btn').addEventListener('click', doFestivalImageSearch);
  document.getElementById('festival-image-query').addEventListener('keydown', e => {
    if (e.key === 'Enter') doFestivalImageSearch();
  });
}

function initEditMap() {
  if (editMap) {
    editMap.remove();
    editMap = null;
  }

  const info = state.terrainData;
  const b = info.bounds;
  const lat = state.selectedPlace.lat;
  const lng = state.selectedPlace.lng;

  editMap = L.map('edit-map', {
    zoomControl: true,
    attributionControl: false,
    center: [lat, lng],
    zoom: 13,
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
  }).addTo(editMap);

  // Diameter circle
  if (editCircle) editMap.removeLayer(editCircle);
  editCircle = L.circle([lat, lng], {
    radius: state.diameterKm * 500,
    color: '#7c5cfc',
    fillColor: '#7c5cfc',
    fillOpacity: 0.06,
    weight: 2,
    dashArray: '6 6',
  }).addTo(editMap);

  editMap.fitBounds(editCircle.getBounds().pad(0.2));
}

function init3DPreview(info) {
  const rawUrl = info.images && info.images.raw;
  if (!rawUrl) return;

  const img = new Image();
  img.onload = () => {
    try {
      const w = info.heightmap_size.width;
      const h = info.heightmap_size.height;
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, w, h);
      const imageData = ctx.getImageData(0, 0, w, h);
      const pixels = new Float32Array(w * h);
      for (let i = 0; i < w * h; i++) pixels[i] = imageData.data[i * 4];
      state.rawImageData = pixels;

      const ds = downsampleHeightmap(pixels, w, h, 300);
      setTimeout(() => {
        if (world3d) world3d.dispose();
        world3d = new WorldPreview3D();
        world3d.init('three-container');
        world3d.buildTerrain(ds, null);
      }, 50);
    } catch (e) {
      console.error('3D preview error:', e);
    }
  };
  img.src = rawUrl;
}

// ─────────────────────────────────────────────
// 3b. VIEW TOGGLE (2D / 3D)
// ─────────────────────────────────────────────

function initViewToggle() {
  const pills = document.querySelectorAll('#view-pills .pill');
  pills.forEach(p => {
    p.addEventListener('click', () => {
      pills.forEach(p2 => p2.classList.remove('active'));
      p.classList.add('active');
      const view = p.dataset.view;
      if (view === '3d') {
        show3DView();
      } else {
        show2DView();
      }
    });
  });
}

function show3DView() {
  const mapEl = document.getElementById('edit-map');
  // Hide Leaflet tiles (Leaflet needs resize handling if hidden)
  if (editMap) editMap._container.style.display = 'none';
  const threeC = document.getElementById('three-container');
  threeC.style.display = 'block';
  document.getElementById('three-hint').style.display = 'inline';
  if (world3d) world3d.show();
}

function show2DView() {
  const threeC = document.getElementById('three-container');
  threeC.style.display = 'none';
  document.getElementById('three-hint').style.display = 'none';
  if (editMap) editMap._container.style.display = 'block';
  if (world3d) world3d.hide();
  // Refresh Leaflet size after showing
  setTimeout(() => { if (editMap) editMap.invalidateSize(); }, 100);
}

// ─────────────────────────────────────────────
// 4. PROCESS SCREEN
// ─────────────────────────────────────────────

async function startBuild() {
  showScreen('screen-process');
  document.getElementById('process-result').style.display = 'none';
  document.getElementById('process-error').style.display = 'none';
  document.getElementById('process-log').innerHTML = '';
  setStatus('Building...');

  // Reset progress steps
  document.querySelectorAll('.progress-step').forEach(el => {
    el.classList.remove('active', 'done', 'error');
  });

  const worldName = state.settings.worldName;

  try {
    const form = new FormData();
    form.append('lat', state.selectedPlace.lat);
    form.append('lng', state.selectedPlace.lng);
    form.append('diameter_km', state.diameterKm);
    form.append('style', state.settings.style);
    form.append('world_name', worldName);
    form.append('srtm_resolution', state.settings.srtmRes);

    // Send festival name + images for AI stage generation
    if (state.festivalName && state.festivalName !== 'My Festival') {
      form.append('festival_name', state.festivalName);
      // Collect image URLs from the festival images container
      const imgContainer = document.getElementById('festival-images');
      if (imgContainer) {
        const urls = [];
        imgContainer.querySelectorAll('img').forEach(img => {
          if (img.src) urls.push(img.src);
        });
        if (urls.length) form.append('festival_images', urls.join(','));
      }
    }

    // Show the user the analysis and discovery steps live
    advanceStep('bounds');
    logProcess('Preparing world bounds and festival context...');
    await sleep(250);
    advanceStep('srtm');
    logProcess('Downloading SRTM elevation data...');
    await sleep(400);
    advanceStep('osm');
    logProcess('Downloading OSM features (roads, buildings, water)...');
    await sleep(400);
    logProcess('Scanning for terrain references and festival imagery...');
    await sleep(300);

    const r = await fetch('/gui/build-geo', { method: 'POST', body: form });

    advanceStep('terrain');
    logProcess('Building terrain and integrating features...');
    await sleep(250);
    advanceStep('plan');
    logProcess('Planning festival layout from terrain and context...');
    await sleep(250);
    advanceStep('export');
    logProcess('Exporting Minecraft world files...');
    await sleep(250);

    if (!r.ok) {
      const e = await r.json();
      throw new Error(e.detail || r.statusText);
    }

    const data = await r.json();

    if (data && data.ai_structures && data.ai_structures.length) {
      logProcess(`AI stage design generated with ${data.ai_structures.length} structure blocks.`);
    }

    advanceStep('done');
    logProcess('World generation complete!');
    setStatus('Complete');

    // Store heightmap for 3D viewer
    state.buildHeightmap = data.heightmap_b64 || null;
    state.buildHeightmapSize = data.heightmap_size || null;
    state.aiStructures = data.ai_structures || [];

    document.getElementById('process-result').style.display = 'block';
    document.getElementById('process-message').textContent = data.message;

    // Show output tree
    const treeEl = document.getElementById('process-output-tree');
    treeEl.innerHTML = '';
    if (data.output_tree && data.output_tree.length) {
      const heading = document.createElement('div');
      heading.style.cssText = 'font-weight:600;color:var(--text2);margin-bottom:6px';
      heading.textContent = `Output: ${data.output_path}/`;
      treeEl.appendChild(heading);
      data.output_tree.forEach(f => {
        const item = document.createElement('div');
        item.style.cssText = 'padding:2px 0 2px 16px;font-family:var(--mono)';
        item.innerHTML = `<i class="fas fa-file"></i> ${f}`;
        treeEl.appendChild(item);
      });
    }

  } catch (e) {
    document.getElementById('process-error').style.display = 'block';
    document.getElementById('process-error-msg').textContent = 'Build failed: ' + e.message;
    setStatus('Error');
    logProcess(`ERROR: ${e.message}`);
  }

  // Auto-search festival images if name is set
  if (state.festivalName && state.festivalName !== 'My Festival') {
    document.getElementById('festival-image-query').value = state.festivalName;
    setTimeout(doFestivalImageSearch, 100);
  }

  // Bind process screen buttons
  document.getElementById('process-new').addEventListener('click', () => {
    showScreen('screen-search');
    setStatus('Ready');
  });
  document.getElementById('process-retry').addEventListener('click', startBuild);
  document.getElementById('process-open-output').addEventListener('click', () => {
    logProcess('Output path recorded in build log.');
  });
  document.getElementById('process-view-3d').addEventListener('click', showProcess3D);
  document.getElementById('process-3d-close').addEventListener('click', closeProcess3D);
}

function downsampleHeightmap(pixels, w, h, maxSize) {
  if (w <= maxSize && h <= maxSize) return { pixels, width: w, height: h };
  const scale = maxSize / Math.max(w, h);
  const nw = Math.max(1, Math.round(w * scale));
  const nh = Math.max(1, Math.round(h * scale));
  const out = new Float32Array(nw * nh);
  for (let y = 0; y < nh; y++) {
    for (let x = 0; x < nw; x++) {
      const sx = x / scale;
      const sy = y / scale;
      const ix = Math.min(Math.floor(sx), w - 2);
      const iy = Math.min(Math.floor(sy), h - 2);
      const fx = sx - ix, fy = sy - iy;
      const a = pixels[iy * w + ix], b = pixels[iy * w + ix + 1];
      const c = pixels[(iy + 1) * w + ix], d = pixels[(iy + 1) * w + ix + 1];
      out[y * nw + x] = (1-fy)*((1-fx)*a + fx*b) + fy*((1-fx)*c + fx*d);
    }
  }
  return { pixels: out, width: nw, height: nh };
}

let processWorld3D = null;

async function showProcess3D() {
  const b64 = state.buildHeightmap;
  if (!b64) { logProcess('No heightmap available for 3D view.'); return; }

  const viewer = document.getElementById('process-3d-viewer');
  viewer.style.display = 'block';
  document.getElementById('process-view-3d').disabled = true;
  logProcess('Loading 3D view...');

  const img = new Image();
  img.onload = () => {
    try {
      const w = state.buildHeightmapSize.width;
      const h = state.buildHeightmapSize.height;
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0, w, h);
      const imageData = ctx.getImageData(0, 0, w, h);
      const pixels = new Float32Array(w * h);
      for (let i = 0; i < w * h; i++) pixels[i] = imageData.data[i * 4];

      // Downsample to max 300px for reasonable mesh size
      const ds = downsampleHeightmap(pixels, w, h, 300);

      // Init Three.js after layout settles
      setTimeout(() => {
        if (processWorld3D) processWorld3D.dispose();
        processWorld3D = new WorldPreview3D();
        processWorld3D.init('process-3d-container');
        processWorld3D.buildTerrain(ds, null);
        if (state.aiStructures && state.aiStructures.length) {
          const seaLevel = 63;
          processWorld3D.buildStructures(state.aiStructures, seaLevel);
          logProcess(`AI structures: ${state.aiStructures.length} blocks`);
        }
        processWorld3D.show();
        logProcess('3D view ready — drag to orbit, scroll to zoom');
        document.getElementById('process-view-3d').disabled = false;
      }, 50);
    } catch (e) {
      logProcess('3D view error: ' + e.message);
      document.getElementById('process-view-3d').disabled = false;
    }
  };
  img.onerror = () => {
    logProcess('Failed to load heightmap for 3D view.');
    document.getElementById('process-view-3d').disabled = false;
  };
  img.src = 'data:image/png;base64,' + b64;
}

function closeProcess3D() {
  if (processWorld3D) { processWorld3D.dispose(); processWorld3D = null; }
  document.getElementById('process-3d-viewer').style.display = 'none';
  document.getElementById('process-view-3d').disabled = false;
}

function advanceStep(id) {
  const el = document.querySelector(`.progress-step[data-step="${id}"]`);
  if (!el) return;
  // Deactivate all previous
  document.querySelectorAll('.progress-step').forEach(s => s.classList.remove('active'));
  el.classList.add('active');
  el.classList.remove('done');
  // Mark all before as done
  let prev = el.previousElementSibling;
  while (prev) {
    if (prev.classList.contains('progress-step')) {
      prev.classList.add('done');
      prev.classList.remove('active');
    }
    prev = prev.previousElementSibling;
  }
}

function logProcess(msg) {
  const log = document.getElementById('process-log');
  const line = document.createElement('div');
  line.innerHTML = `<span style="color:var(--text3)">></span> ${msg}`;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function doFestivalImageSearch() {
  const query = document.getElementById('festival-image-query').value.trim();
  if (!query) return;
  const btn = document.getElementById('festival-image-btn');
  btn.disabled = true; btn.innerHTML = '<span class="spinner" style="font-size:10px"></span>';
  try {
    const form = new FormData();
    form.append('name', query);
    form.append('limit', '8');
    const r = await fetch('/gui/festival-images', { method: 'POST', body: form });
    const data = await r.json();
    const container = document.getElementById('festival-images');
    container.innerHTML = '';
    (data.images || []).forEach(url => {
      const img = document.createElement('img');
      img.src = url;
      img.style.cssText = 'width:60px;height:60px;object-fit:cover;border-radius:4px;cursor:pointer;border:1px solid var(--border)';
      img.title = url;
      img.addEventListener('click', () => openLightbox(url, query));
      img.addEventListener('error', () => img.remove());
      container.appendChild(img);
    });
    if (!data.images || !data.images.length) {
      container.innerHTML = '<span style="font-size:10px;color:var(--text3)">No images found</span>';
    }
  } catch (e) {
    document.getElementById('festival-images').innerHTML =
      '<span style="font-size:10px;color:var(--red)">Search failed</span>';
  } finally {
    btn.disabled = false; btn.innerHTML = '<i class="fas fa-search" style="font-size:10px"></i>';
  }
}

// ─────────────────────────────────────────────
// 5. LIGHTBOX
// ─────────────────────────────────────────────

function openLightbox(url, caption) {
  const lb = document.getElementById('lightbox');
  document.getElementById('lightbox-img').src = url;
  document.getElementById('lightbox-caption').textContent = caption || '';
  lb.style.display = 'flex';
}
function closeLightbox() {
  document.getElementById('lightbox').style.display = 'none';
}
document.getElementById('lightbox').addEventListener('click', closeLightbox);
document.getElementById('lightbox-close').addEventListener('click', closeLightbox);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });

// ─────────────────────────────────────────────
// 6. INIT
// ─────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initSearchScreen();
  initViewToggle();
  showScreen('screen-search');

  // Process screen buttons
  document.getElementById('process-new').addEventListener('click', () => {
    showScreen('screen-search');
    setStatus('Ready');
  });
});

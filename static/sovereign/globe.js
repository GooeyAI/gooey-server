(function () {
  const GRID_URL = "globe-grid.bin";
  const GRID_WIDTH = 360;
  const GRID_HEIGHT = 180;
  const ROTATION_SPEED = 0.0018;
  const LED_COLS = 58;
  const LED_GAP = 0.34;
  const COLORS = [
    "rgb(198, 221, 239)", // ocean
    "rgb(184, 181, 173)", // land grey
    "rgb(0, 153, 138)", // middle-power teal
  ];

  function normalizeLon(lon) {
    let value = lon;
    while (value > 180) value -= 360;
    while (value < -180) value += 360;
    return value;
  }

  function sampleGrid(grid, lon, lat) {
    const clampedLat = Math.max(-89.9, Math.min(89.9, lat));
    const i = Math.round(normalizeLon(lon) + 179.5);
    const j = Math.round(89.5 - clampedLat);
    if (i < 0 || i >= GRID_WIDTH || j < 0 || j >= GRID_HEIGHT) return 0;
    const value = grid[j * GRID_WIDTH + i];
    if (value === 2) return 2;
    if (value === 1) return 1;
    return 0;
  }

  function renderFrame(ctx, size, grid, rotation) {
    ctx.clearRect(0, 0, size, size);

    const center = size / 2;
    const radius = center * 0.985;
    const pitch = (radius * 2) / LED_COLS;
    const ledSize = pitch * (1 - LED_GAP);
    const inset = (size - pitch * LED_COLS) / 2;
    const cosR = Math.cos(rotation);
    const sinR = Math.sin(rotation);

    for (let row = 0; row < LED_COLS; row++) {
      for (let col = 0; col < LED_COLS; col++) {
        const px = inset + (col + 0.5) * pitch;
        const py = inset + (row + 0.5) * pitch;
        const dx = (px - center) / radius;
        const dy = (center - py) / radius;
        const dist2 = dx * dx + dy * dy;
        if (dist2 > 1) continue;

        const z = Math.sqrt(1 - dist2);
        const xWorld = dx * cosR + z * sinR;
        const zWorld = -dx * sinR + z * cosR;
        const yWorld = dy;
        const lon = (Math.atan2(xWorld, zWorld) * 180) / Math.PI;
        const lat = (Math.asin(yWorld) * 180) / Math.PI;
        ctx.fillStyle = COLORS[sampleGrid(grid, lon, lat)];
        ctx.fillRect(
          inset + col * pitch + (pitch - ledSize) / 2,
          inset + row * pitch + (pitch - ledSize) / 2,
          ledSize,
          ledSize
        );
      }
    }
  }

  function resizeCanvas(canvas) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const size = Math.max(1, Math.round(Math.min(rect.width, rect.height)));
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);
    return canvas.width;
  }

  window.initGlobe = function initGlobe(canvas) {
    if (!canvas) return null;

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return null;

    let grid = null;
    let rotation = 0.35;
    let frameId = 0;
    let visible = true;
    let reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches;

    canvas.classList.add("globe-float");

    function draw() {
      if (!grid || !visible) return;
      const size = resizeCanvas(canvas);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      renderFrame(ctx, size, grid, rotation);
      if (!reduceMotion) rotation += ROTATION_SPEED;
    }

    function tick() {
      draw();
      frameId = window.requestAnimationFrame(tick);
    }

    function setLayout(rect) {
      canvas.style.left = rect.left + "px";
      canvas.style.top = rect.top + "px";
      canvas.style.width = rect.width + "px";
      canvas.style.height = rect.height + "px";
      draw();
    }

    function setVisible(nextVisible) {
      visible = nextVisible;
      canvas.style.opacity = nextVisible ? "1" : "0";
      canvas.style.visibility = nextVisible ? "visible" : "hidden";
    }

    fetch(GRID_URL)
      .then((response) => {
        if (!response.ok) throw new Error("Failed to load globe grid");
        return response.arrayBuffer();
      })
      .then((buffer) => {
        grid = new Uint8Array(buffer);
        draw();
        frameId = window.requestAnimationFrame(tick);
        if (window.sovereignGlobeReady) window.sovereignGlobeReady();
      })
      .catch((error) => {
        console.error(error);
      });

    window.addEventListener("resize", draw);

    return {
      draw,
      isReady() {
        return !!grid;
      },
      setLayout,
      setVisible,
      destroy() {
        window.cancelAnimationFrame(frameId);
        window.removeEventListener("resize", draw);
      },
    };
  };
})();

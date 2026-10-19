// Measurements are kept per mounted component, never shared across charts.
const instances = new WeakMap();

export default function mount({data, parentElement, setStateValue}) {
  instances.get(parentElement)?.dispose();
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) return;

  let active = true;
  let timer;
  let observedPanel;
  let observedBounds;
  let lastSignature = JSON.stringify(data.previous ?? null);
  const rounded = value => Math.round(value * 2) / 2;
  const schedule = () => {
    if (!active) return;
    clearTimeout(timer);
    timer = setTimeout(measure, 150);
  };
  const resizeObserver = new ResizeObserver(schedule);
  const mutationObserver = new MutationObserver(schedule);

  function measure() {
    if (!active) return;
    const bounds = document.querySelector(data.selector);
    const panel = bounds?.closest('[data-testid="stVegaLiteChart"]');
    if (panel && panel !== observedPanel) {
      mutationObserver.disconnect();
      mutationObserver.observe(panel, {
        childList: true, subtree: true, attributes: true,
        attributeFilter: ["d", "transform", "width", "height", "viewBox", "class", "style"],
      });
      resizeObserver.disconnect();
      resizeObserver.observe(panel);
      observedPanel = panel;
      observedBounds = null;
    }
    if (!bounds || !bounds.getBBox || !bounds.isConnected) return;
    if (bounds !== observedBounds) {
      if (observedBounds) resizeObserver.unobserve(observedBounds);
      resizeObserver.observe(bounds);
      observedBounds = bounds;
    }
    const box = bounds.getBBox();
    // Flooring keeps the font breakpoint identical to Vega's width >= 800.
    const width = Math.floor(box.width);
    const height = rounded(box.height);
    if (!(width >= 16 && height >= 16 && width <= 20000 && height <= 20000)) return;
    const fontSize = width >= 800 ? 18 : 14;
    context.font = `600 ${fontSize}px sans-serif`;
    let textHalfHeight = 0;
    const players = data.players.map(player => {
      const text = context.measureText(player.name);
      const inkWidth = Math.abs(text.actualBoundingBoxLeft || 0) +
        Math.abs(text.actualBoundingBoxRight || 0);
      // Right alignment anchors at the advance width. A leading glyph such as
      // "j" can extend farther left even when the total ink span is narrower.
      const rightAlignedWidth = text.width + Math.max(0, text.actualBoundingBoxLeft || 0);
      // Vega implements middle alignment by shifting the alphabetic baseline.
      // Font bounds include accents and descenders of the complete name.
      const ascent = Math.max(text.fontBoundingBoxAscent ?? 0, text.actualBoundingBoxAscent ?? 0);
      const descent = Math.max(text.fontBoundingBoxDescent ?? 0, text.actualBoundingBoxDescent ?? 0);
      const baseline = Math.round(fontSize * 0.3);
      const hasFontBounds = Number.isFinite(text.fontBoundingBoxAscent) &&
        Number.isFinite(text.fontBoundingBoxDescent) && ascent > 0;
      const measuredHalf = hasFontBounds
        ? Math.max(ascent - baseline, descent + baseline) + 0.5
        : Math.max(fontSize * 0.75, ascent - baseline + 0.5, descent + baseline + 0.5);
      textHalfHeight = Math.max(textHalfHeight, measuredHalf);
      return {
        id: player.id, name: player.name,
        width: Math.max(0.5, Math.ceil(Math.max(text.width, inkWidth, rightAlignedWidth) * 2) / 2),
      };
    });
    const metrics = {width, height, font_size: fontSize,
      text_half_height: Math.ceil(textHalfHeight * 2) / 2, players};
    const signature = JSON.stringify(metrics);
    if (signature === lastSignature) return;
    lastSignature = signature;
    setStateValue("metrics", metrics);
  }

  // The chart may finish mounting after this zero-height companion does.
  const main = document.querySelector('[data-testid="stMainBlockContainer"]');
  if (main) mutationObserver.observe(main, {childList: true, subtree: true});
  window.addEventListener("resize", schedule);
  document.fonts?.addEventListener("loadingdone", schedule);
  document.fonts?.ready.then(schedule);
  schedule();

  const dispose = () => {
    active = false;
    clearTimeout(timer);
    mutationObserver.disconnect();
    resizeObserver.disconnect();
    window.removeEventListener("resize", schedule);
    document.fonts?.removeEventListener("loadingdone", schedule);
  };
  const instance = {dispose};
  instances.set(parentElement, instance);
  return () => {
    dispose();
    if (instances.get(parentElement) === instance) instances.delete(parentElement);
  };
}

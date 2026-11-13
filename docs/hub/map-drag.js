// Drag the nodes and groups of a map (`svg`, `D` and `POSITIONS` come from its page). Shift+C copies the offsets from the
// generated layout, as JSON to save as the page's POSITIONS.
(() => {
  const DRAG_THRESHOLD = 3;
  const VIEW_PADDING = 20;
  const offsets = {};
  const nodes = {};
  svg.querySelectorAll(".node").forEach((el) => {
    nodes[el.dataset.id] = { el, rect: el.querySelector("rect") };
    offsets[el.dataset.id] = [0, 0];
  });
  const edges = [...svg.querySelectorAll(".edge")].map((el) => {
    const [x1, y1, cx, cy, x2, y2] = el.getAttribute("d").match(/-?[\d.]+/g).map(Number);
    return { el, s: el.dataset.s, d: el.dataset.d, x1, y1, cx, cy, x2, y2 };
  });
  const box = ({ rect }, [dx, dy]) => {
    const [x, y] = [+rect.getAttribute("x") + dx, +rect.getAttribute("y") + dy];
    return [x, y, x + +rect.getAttribute("width"), y + +rect.getAttribute("height")];
  };
  const bounds = (ids) => {
    const boxes = ids.map((id) => box(nodes[id], offsets[id]));
    return [0, 1].map((i) => Math.min(...boxes.map((b) => b[i]))).concat([2, 3].map((i) => Math.max(...boxes.map((b) => b[i]))));
  };
  const hulls = [...svg.querySelectorAll(".hull")].flatMap((el) => {
    const domains = D.super[el.dataset.dom] || [el.dataset.dom];
    const ids = Object.keys(nodes).filter((id) => D.nodes[id] && domains.includes(D.nodes[id].domain));
    if (!ids.length) return [];
    const rect = el.querySelector("rect");
    const label = el.querySelector("text");
    const [x, y, w, h] = ["x", "y", "width", "height"].map((a) => +rect.getAttribute(a));
    const [x0, y0, x1, y1] = bounds(ids);
    // a hull keeps its margins around its nodes, whichever of them moves
    return [{ el, rect, label, ids, pad: [x0 - x, y0 - y, x + w - x1, y + h - y1], labelAt: [+label.getAttribute("x") - x, +label.getAttribute("y") - y] }];
  });

  function draw() {
    for (const [id, [dx, dy]] of Object.entries(offsets)) nodes[id].el.setAttribute("transform", `translate(${dx} ${dy})`);
    for (const e of edges) {
      const [sx, sy] = offsets[e.s] || [0, 0];
      const [dx, dy] = offsets[e.d] || [0, 0];
      e.el.setAttribute("d", `M${e.x1 + sx} ${e.y1 + sy} Q${e.cx + (sx + dx) / 2} ${e.cy + (sy + dy) / 2} ${e.x2 + dx} ${e.y2 + dy}`);
    }
    for (const h of hulls) {
      const [x0, y0, x1, y1] = bounds(h.ids);
      const [x, y] = [x0 - h.pad[0], y0 - h.pad[1]];
      h.rect.setAttribute("x", x);
      h.rect.setAttribute("y", y);
      h.rect.setAttribute("width", x1 + h.pad[2] - x);
      h.rect.setAttribute("height", y1 + h.pad[3] - y);
      h.label.setAttribute("x", x + h.labelAt[0]);
      h.label.setAttribute("y", y + h.labelAt[1]);
    }
  }

  // only once dropped: rescaling under the pointer would throw the drag off
  function fitView() {
    const b = svg.getBBox();
    svg.setAttribute("viewBox", `${b.x - VIEW_PADDING} ${b.y - VIEW_PADDING} ${b.width + 2 * VIEW_PADDING} ${b.height + 2 * VIEW_PADDING}`);
  }

  const point = (ev) => new DOMPoint(ev.clientX, ev.clientY).matrixTransform(svg.getScreenCTM().inverse());
  let drag = null;
  let wasDragged = false;

  svg.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    const node = ev.target.closest(".node");
    const hull = !node && hulls.find((h) => h.el.contains(ev.target));
    if (!node && !hull) return;
    const ids = node ? [node.dataset.id] : hull.ids;
    drag = { ids, start: point(ev), from: ids.map((id) => [...offsets[id]]), moved: false, x: ev.clientX, y: ev.clientY };
  });
  window.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    drag.moved ||= Math.hypot(ev.clientX - drag.x, ev.clientY - drag.y) > DRAG_THRESHOLD;
    if (!drag.moved) return;
    const p = point(ev);
    drag.ids.forEach((id, i) => {
      offsets[id] = [Math.round(drag.from[i][0] + p.x - drag.start.x), Math.round(drag.from[i][1] + p.y - drag.start.y)];
    });
    draw();
  });
  window.addEventListener("pointerup", () => {
    if (drag?.moved) {
      wasDragged = true;
      fitView();
      setTimeout(() => (wasDragged = false)); // no click follows a drop outside the element
    }
    drag = null;
  });
  svg.addEventListener("click", (ev) => wasDragged && ev.stopPropagation(), true); // a drag isn't a click on the node

  function toast(text) {
    const el = Object.assign(document.createElement("div"), { textContent: text });
    el.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);padding:8px 14px;border-radius:8px;background:var(--ink);color:var(--bg);font:13px var(--mono,monospace);z-index:99";
    document.body.append(el);
    setTimeout(() => el.remove(), 2000);
  }

  // file:// pages and embedding frames may have no navigator.clipboard
  function copyFallback(text) {
    const area = Object.assign(document.createElement("textarea"), { value: text });
    document.body.append(area);
    area.select();
    const isCopied = document.execCommand("copy");
    area.remove();
    return isCopied;
  }

  document.addEventListener("keydown", async (ev) => {
    if (ev.key !== "C" || !ev.shiftKey || ev.metaKey || ev.ctrlKey || document.activeElement?.matches("input,textarea")) return;
    const moved = Object.fromEntries(Object.entries(offsets).filter(([, [x, y]]) => x || y));
    const text = JSON.stringify(moved);
    let isCopied;
    try {
      await navigator.clipboard.writeText(text);
      isCopied = true;
    } catch {
      isCopied = copyFallback(text);
    }
    toast(isCopied ? `Copied the positions of ${Object.keys(moved).length} nodes` : "Could not copy the positions");
  });

  svg.style.userSelect = "none";
  svg.style.touchAction = "none";
  hulls.forEach((h) => (h.rect.style.cursor = "move"));
  for (const [id, offset] of Object.entries(POSITIONS)) if (offsets[id]) offsets[id] = offset;
  if (Object.keys(POSITIONS).length) {
    draw();
    fitView();
  }
})();

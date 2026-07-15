/* Sprint 16.1 — Interactive tools:
 *  1. Draggable TP/SL + pending-order price lines → drag end posts
 *     {type:"lineDragged", id, kind, price} so the app PUTs the backend.
 *  2. Drawing objects (trend/hline/vline/rect/fib/text) on an overlay canvas,
 *     stored in (time, price) space and persisted per user via the app
 *     ({type:"objectsChanged", objects}). */
(function () {
  "use strict";
  var C = window.__chart;
  var chart = C.chart, series = C.candleSeries, state = C.state, post = C.post;
  var chartEl = document.getElementById("chart");

  // ================= draggable price lines =================
  var dragItems = [];   // {id, kind, price, color, title, line}
  var dragging = null;

  function clearDraggable() {
    dragItems.forEach(function (it) { try { series.removePriceLine(it.line); } catch (e) {} });
    dragItems = [];
  }
  C.extraHandlers.setDraggable = function (m) {
    clearDraggable();
    (m.items || []).forEach(function (it) {
      var line = series.createPriceLine({
        price: it.price,
        color: it.color || (it.kind === "tp" ? "#26a69a" : it.kind === "sl" ? "#ef5350" : "#f0b90b"),
        lineWidth: 1, lineStyle: 2, axisLabelVisible: true,
        title: (it.title || it.kind.toUpperCase()) + " ⇕",
      });
      dragItems.push({ id: it.id, kind: it.kind, price: it.price, title: it.title, line: line });
    });
  };

  function hitDraggable(y) {
    var best = null, bestD = 16;
    dragItems.forEach(function (it) {
      var ly = series.priceToCoordinate(it.price);
      if (ly == null) return;
      var d = Math.abs(ly - y);
      if (d < bestD) { bestD = d; best = it; }
    });
    return best;
  }

  function setChartInteraction(on) {
    chart.applyOptions({
      handleScroll: on ? { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false } : false,
      handleScale: on ? { mouseWheel: true, pinch: true, axisPressedMouseMove: true } : false,
    });
  }

  // ================= drawing objects =================
  var canvas = document.createElement("canvas");
  canvas.style.cssText = "position:absolute;inset:0;z-index:5;pointer-events:none;";
  chartEl.appendChild(canvas);
  var ctx = canvas.getContext("2d");
  var objects = [];         // persisted per user+symbol
  var activeTool = null;    // trend|hline|vline|rect|fib|text|erase
  var toolText = "";
  var draft = null;         // in-progress two-point object

  function xOf(t) { return chart.timeScale().timeToCoordinate(t); }
  function yOf(p) { return series.priceToCoordinate(p); }
  function tAt(x) {
    var t = chart.timeScale().coordinateToTime(x);
    if (t != null) return t;
    return state.candles.length ? state.candles[state.candles.length - 1].t : 0;
  }
  function pAt(y) { return series.coordinateToPrice(y); }

  var FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

  function drawObj(o, preview) {
    var col = o.color || "#f0b90b";
    ctx.strokeStyle = col; ctx.fillStyle = col;
    ctx.lineWidth = 1.2; ctx.setLineDash(preview ? [4, 4] : []);
    var x1, y1, x2, y2;
    if (o.type === "hline") {
      y1 = yOf(o.price); if (y1 == null) return;
      ctx.beginPath(); ctx.moveTo(0, y1); ctx.lineTo(canvas.width, y1); ctx.stroke();
      ctx.font = "9px sans-serif";
      ctx.fillText(Number(o.price).toFixed(state.decimals), 4, y1 - 3);
      return;
    }
    if (o.type === "vline") {
      x1 = xOf(o.t); if (x1 == null) return;
      ctx.beginPath(); ctx.moveTo(x1, 0); ctx.lineTo(x1, canvas.height); ctx.stroke();
      return;
    }
    if (o.type === "text") {
      x1 = xOf(o.t); y1 = yOf(o.price);
      if (x1 == null || y1 == null) return;
      ctx.font = "11px sans-serif";
      ctx.fillText(o.text || "text", x1, y1);
      return;
    }
    x1 = xOf(o.p1.t); y1 = yOf(o.p1.price);
    x2 = xOf(o.p2.t); y2 = yOf(o.p2.price);
    if (x1 == null || x2 == null || y1 == null || y2 == null) return;
    if (o.type === "trend") {
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    } else if (o.type === "rect") {
      ctx.globalAlpha = 0.12; ctx.fillRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
      ctx.globalAlpha = 1; ctx.strokeRect(Math.min(x1, x2), Math.min(y1, y2), Math.abs(x2 - x1), Math.abs(y2 - y1));
    } else if (o.type === "fib") {
      var lo = Math.min(x1, x2), hi = Math.max(x1, x2);
      ctx.font = "9px sans-serif";
      FIB_LEVELS.forEach(function (lv) {
        var price = o.p1.price + (o.p2.price - o.p1.price) * lv;
        var y = yOf(price); if (y == null) return;
        ctx.beginPath(); ctx.moveTo(lo, y); ctx.lineTo(hi, y); ctx.stroke();
        ctx.fillText(lv.toFixed(3) + "  " + Number(price).toFixed(state.decimals), hi + 3, y + 3);
      });
    }
  }

  function render() {
    var w = chartEl.clientWidth, h = chartEl.clientHeight;
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    ctx.clearRect(0, 0, w, h);
    objects.forEach(function (o) { drawObj(o, false); });
    if (draft) drawObj(draft, true);
  }
  chart.timeScale().subscribeVisibleLogicalRangeChange(render);
  chart.subscribeCrosshairMove(function () { if (draft) render(); });
  window.addEventListener("resize", render);
  setInterval(render, 900); // keep in sync with live candle shifts

  function persist() { post({ type: "objectsChanged", objects: objects }); }

  C.extraHandlers.setObjects = function (m) { objects = m.objects || []; render(); };
  C.extraHandlers.setTool = function (m) {
    activeTool = m.tool || null;
    toolText = m.text || "";
    draft = null;
    render();
  };

  function nearestObjIdx(x, y) {
    var best = -1, bestD = 18;
    objects.forEach(function (o, i) {
      var d = 1e9;
      if (o.type === "hline") { var yy = yOf(o.price); if (yy != null) d = Math.abs(yy - y); }
      else if (o.type === "vline") { var xx = xOf(o.t); if (xx != null) d = Math.abs(xx - x); }
      else if (o.type === "text") {
        var tx = xOf(o.t), ty = yOf(o.price);
        if (tx != null && ty != null) d = Math.hypot(tx - x, ty - y);
      } else {
        var x1 = xOf(o.p1.t), y1 = yOf(o.p1.price), x2 = xOf(o.p2.t), y2 = yOf(o.p2.price);
        if (x1 != null && y1 != null && x2 != null && y2 != null) {
          // distance to segment
          var dx = x2 - x1, dy = y2 - y1, L2 = dx * dx + dy * dy;
          var t = L2 ? Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / L2)) : 0;
          d = Math.hypot(x - (x1 + t * dx), y - (y1 + t * dy));
          if (o.type === "rect" || o.type === "fib") {
            var inX = x >= Math.min(x1, x2) - 6 && x <= Math.max(x1, x2) + 6;
            var inY = y >= Math.min(y1, y2) - 6 && y <= Math.max(y1, y2) + 6;
            if (inX && inY) d = Math.min(d, 10);
          }
        }
      }
      if (d < bestD) { bestD = d; best = i; }
    });
    return best;
  }

  // ================= unified pointer handling =================
  function localXY(e) {
    var r = chartEl.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  chartEl.addEventListener("pointerdown", function (e) {
    var p = localXY(e);
    // 1) drawing tool active?
    if (activeTool) {
      e.preventDefault(); e.stopPropagation();
      if (activeTool === "erase") {
        var idx = nearestObjIdx(p.x, p.y);
        if (idx >= 0) { objects.splice(idx, 1); render(); persist(); }
        return;
      }
      var t = tAt(p.x), price = pAt(p.y);
      if (price == null) return;
      if (activeTool === "hline") {
        objects.push({ id: "o" + Date.now(), type: "hline", price: price, color: "#f0b90b" });
        render(); persist(); return;
      }
      if (activeTool === "vline") {
        objects.push({ id: "o" + Date.now(), type: "vline", t: t, color: "#f0b90b" });
        render(); persist(); return;
      }
      if (activeTool === "text") {
        objects.push({ id: "o" + Date.now(), type: "text", t: t, price: price, text: toolText || "note", color: "#d1d4dc" });
        render(); persist(); return;
      }
      // two-point tools
      setChartInteraction(false);
      draft = { id: "o" + Date.now(), type: activeTool, p1: { t: t, price: price }, p2: { t: t, price: price }, color: "#f0b90b" };
      render();
      return;
    }
    // 2) draggable TP/SL/pending line?
    var hit = hitDraggable(p.y);
    if (hit) {
      e.preventDefault(); e.stopPropagation();
      dragging = hit;
      setChartInteraction(false);
    }
  }, true);

  chartEl.addEventListener("pointermove", function (e) {
    var p = localXY(e);
    if (draft) {
      e.preventDefault();
      draft.p2 = { t: tAt(p.x), price: pAt(p.y) || draft.p2.price };
      render();
      return;
    }
    if (dragging) {
      e.preventDefault();
      var price = pAt(p.y);
      if (price != null && price > 0) {
        dragging.price = price;
        dragging.line.applyOptions({ price: price, title: (dragging.kind.toUpperCase()) + " " + Number(price).toFixed(state.decimals) + " ⇕" });
      }
    }
  }, true);

  function finish(e) {
    if (draft) {
      objects.push(draft);
      draft = null;
      setChartInteraction(true);
      render(); persist();
      post({ type: "toolUsed" });
      return;
    }
    if (dragging) {
      setChartInteraction(true);
      post({ type: "lineDragged", id: dragging.id, kind: dragging.kind, price: dragging.price });
      dragging = null;
    }
  }
  chartEl.addEventListener("pointerup", finish, true);
  chartEl.addEventListener("pointercancel", finish, true);
})();

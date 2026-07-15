/* Sprint 16.1/16.2 — Indicator engine.
 * Computes ALL indicators locally from the unified candle engine data
 * (never fetched from Finnhub). Overlays render on the main chart; oscillators
 * render in a synchronized sub-pane (TradingView mobile style).
 * Architecture: register(id, spec) — new indicators need zero engine changes. */
(function () {
  "use strict";
  var C = window.__chart;
  var mainChart = C.chart, candleSeries = C.candleSeries, state = C.state;

  // ---------------- math (accuracy-verified in regression tests) ----------
  function src(cs, s) {
    s = s || "close";
    return cs.map(function (c) {
      if (s === "open") return c.o;
      if (s === "high") return c.h;
      if (s === "low") return c.l;
      if (s === "hlc3") return (c.h + c.l + c.c) / 3;
      if (s === "ohlc4") return (c.o + c.h + c.l + c.c) / 4;
      return c.c;
    });
  }
  function smaArr(v, n) {
    var out = new Array(v.length).fill(null), sum = 0;
    for (var i = 0; i < v.length; i++) {
      sum += v[i];
      if (i >= n) sum -= v[i - n];
      if (i >= n - 1) out[i] = sum / n;
    }
    return out;
  }
  function emaArr(v, n) {
    var out = new Array(v.length).fill(null), k = 2 / (n + 1), prev = null, seed = 0;
    for (var i = 0; i < v.length; i++) {
      if (i < n - 1) { seed += v[i]; continue; }
      if (i === n - 1) { seed += v[i]; prev = seed / n; out[i] = prev; continue; }
      prev = v[i] * k + prev * (1 - k);
      out[i] = prev;
    }
    return out;
  }
  function stdevArr(v, n, means) {
    var out = new Array(v.length).fill(null);
    for (var i = n - 1; i < v.length; i++) {
      var m = means[i], s = 0;
      for (var j = i - n + 1; j <= i; j++) s += (v[j] - m) * (v[j] - m);
      out[i] = Math.sqrt(s / n);
    }
    return out;
  }
  function rsiArr(cs, n) {
    var out = new Array(cs.length).fill(null);
    if (cs.length < n + 1) return out;
    var g = 0, l = 0, i, d;
    for (i = 1; i <= n; i++) { d = cs[i].c - cs[i - 1].c; if (d > 0) g += d; else l -= d; }
    var ag = g / n, al = l / n;
    out[n] = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
    for (i = n + 1; i < cs.length; i++) {
      d = cs[i].c - cs[i - 1].c;
      ag = (ag * (n - 1) + Math.max(d, 0)) / n;
      al = (al * (n - 1) + Math.max(-d, 0)) / n;
      out[i] = al === 0 ? 100 : 100 - 100 / (1 + ag / al);
    }
    return out;
  }
  function atrArr(cs, n) {
    var out = new Array(cs.length).fill(null);
    if (cs.length < n + 1) return out;
    var trs = [0], i;
    for (i = 1; i < cs.length; i++) {
      trs.push(Math.max(cs[i].h - cs[i].l,
        Math.abs(cs[i].h - cs[i - 1].c), Math.abs(cs[i].l - cs[i - 1].c)));
    }
    var a = 0;
    for (i = 1; i <= n; i++) a += trs[i];
    a /= n;
    out[n] = a;
    for (i = n + 1; i < cs.length; i++) { a = (a * (n - 1) + trs[i]) / n; out[i] = a; }
    return out;
  }
  function vwapArr(cs) {
    var out = new Array(cs.length).fill(null), day = null, pv = 0, vv = 0;
    for (var i = 0; i < cs.length; i++) {
      var d = Math.floor(cs[i].t / 86400);
      if (d !== day) { day = d; pv = 0; vv = 0; }
      var vol = cs[i].v || 1, tp = (cs[i].h + cs[i].l + cs[i].c) / 3;
      pv += tp * vol; vv += vol;
      out[i] = pv / vv;
    }
    return out;
  }
  function pts(cs, arr) {
    var out = [];
    for (var i = 0; i < cs.length; i++) if (arr[i] != null) out.push({ time: cs[i].t, value: arr[i] });
    return out;
  }

  // ---------------- oscillator sub-pane (synced) ---------------------------
  var oscChart = null, oscEl = document.getElementById("osc");
  var syncing = false;
  function ensureOsc() {
    if (oscChart) return oscChart;
    oscChart = LightweightCharts.createChart(oscEl, {
      layout: { background: { type: "solid", color: "#0e1117" }, textColor: "#9aa0aa", fontSize: 9 },
      grid: { vertLines: { color: "#161b26" }, horzLines: { color: "#161b26" } },
      rightPriceScale: { borderColor: "#1c2230" },
      timeScale: { visible: false },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: "#4c5566", width: 1, style: 3, labelVisible: false },
        horzLine: { visible: false, labelVisible: false },
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { mouseWheel: true, pinch: true },
      localization: { locale: "en-US" },
    });
    // Two-way zoom/pan/time-axis sync with the main chart
    mainChart.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
      if (syncing || !r) return;
      syncing = true; oscChart.timeScale().setVisibleLogicalRange(r); syncing = false;
    });
    oscChart.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
      if (syncing || !r) return;
      syncing = true; mainChart.timeScale().setVisibleLogicalRange(r); syncing = false;
    });
    // Crosshair sync (main → pane and pane → main)
    mainChart.subscribeCrosshairMove(function (p) {
      if (!oscChart) return;
      var s = firstOscSeries();
      if (p && p.time && s) oscChart.setCrosshairPosition(0, p.time, s);
      else oscChart.clearCrosshairPosition();
    });
    return oscChart;
  }
  function firstOscSeries() {
    for (var id in Ind.active) {
      var a = Ind.active[id];
      if (!a.spec.overlay && a.series.length) return a.series[0];
    }
    return null;
  }
  function layoutOsc() {
    var anyOsc = Object.keys(Ind.active).some(function (id) { return !Ind.active[id].spec.overlay; });
    oscEl.classList.toggle("visible", anyOsc);
    C.resize();
    if (oscChart) oscChart.applyOptions({ width: oscEl.clientWidth, height: oscEl.clientHeight });
    updateOscLegend();
  }
  function updateOscLegend() {
    var names = Object.keys(Ind.active).filter(function (id) { return !Ind.active[id].spec.overlay; })
      .map(function (id) { return id.toUpperCase() + "(" + (Ind.active[id].params.period || "") + ")"; });
    document.getElementById("osc-legend").textContent = names.join("  ");
  }
  C.onResize = function () {
    if (oscChart) oscChart.applyOptions({ width: oscEl.clientWidth, height: oscEl.clientHeight });
  };

  // ---------------- registry --------------------------------------------
  var Ind = window.Indicators;
  function lineOn(chartObj, color, width, scaleId) {
    return chartObj.addLineSeries({
      color: color, lineWidth: width || 1.5, priceLineVisible: false,
      lastValueVisible: false, crosshairMarkerVisible: false,
      priceScaleId: scaleId || "right",
    });
  }

  function reg(id, overlay, createSeries, compute) {
    Ind.registry[id] = { overlay: overlay, createSeries: createSeries, compute: compute };
  }

  reg("ema", true, function (_, p) {
    return [lineOn(mainChart, p.color || "#f0b90b", p.width)];
  }, function (cs, p) { return [pts(cs, emaArr(src(cs, p.source), p.period || 20))]; });

  reg("sma", true, function (_, p) {
    return [lineOn(mainChart, p.color || "#2962ff", p.width)];
  }, function (cs, p) { return [pts(cs, smaArr(src(cs, p.source), p.period || 50))]; });

  reg("bb", true, function (_, p) {
    var c = p.color || "#7e57c2";
    return [lineOn(mainChart, c, 1), lineOn(mainChart, c, 1), lineOn(mainChart, c, 1)];
  }, function (cs, p) {
    var n = p.period || 20, k = p.mult || 2, v = src(cs, p.source);
    var mid = smaArr(v, n), sd = stdevArr(v, n, mid);
    var up = mid.map(function (m, i) { return m == null ? null : m + k * sd[i]; });
    var lo = mid.map(function (m, i) { return m == null ? null : m - k * sd[i]; });
    return [pts(cs, up), pts(cs, mid), pts(cs, lo)];
  });

  reg("vwap", true, function (_, p) {
    return [lineOn(mainChart, p.color || "#26c6da", p.width)];
  }, function (cs) { return [pts(cs, vwapArr(cs))]; });

  reg("rsi", false, function (_, p) {
    var s = lineOn(ensureOsc(), p.color || "#ab47bc", p.width, "rsi");
    ensureOsc().priceScale("rsi").applyOptions({ visible: true });
    s.createPriceLine({ price: 70, color: "#55606e", lineWidth: 1, lineStyle: 3, axisLabelVisible: false });
    s.createPriceLine({ price: 30, color: "#55606e", lineWidth: 1, lineStyle: 3, axisLabelVisible: false });
    return [s];
  }, function (cs, p) { return [pts(cs, rsiArr(cs, p.period || 14))]; });

  reg("macd", false, function (_, p) {
    var o = ensureOsc();
    var hist = o.addHistogramSeries({ priceScaleId: "macd", priceLineVisible: false, lastValueVisible: false });
    var m = lineOn(o, p.color || "#2962ff", 1.5, "macd");
    var s = lineOn(o, "#ff6d00", 1, "macd");
    return [m, s, hist];
  }, function (cs, p) {
    var v = src(cs, p.source), f = p.fast || 12, s = p.slow || 26, g = p.signal || 9;
    var ef = emaArr(v, f), es = emaArr(v, s);
    var macd = v.map(function (_, i) { return (ef[i] == null || es[i] == null) ? null : ef[i] - es[i]; });
    var valid = macd.map(function (x) { return x == null ? 0 : x; });
    var sig = emaArr(valid, g).map(function (x, i) { return macd[i] == null ? null : x; });
    var histPts = [];
    for (var i = 0; i < cs.length; i++) {
      if (macd[i] != null && sig[i] != null) {
        var h = macd[i] - sig[i];
        histPts.push({ time: cs[i].t, value: h, color: h >= 0 ? "rgba(38,166,154,0.6)" : "rgba(239,83,80,0.6)" });
      }
    }
    return [pts(cs, macd), pts(cs, sig), histPts];
  });

  reg("atr", false, function (_, p) {
    return [lineOn(ensureOsc(), p.color || "#8d6e63", p.width, "atr")];
  }, function (cs, p) { return [pts(cs, atrArr(cs, p.period || 14))]; });

  // Route add/remove through pane layout
  var _add = Ind.add.bind(Ind), _remove = Ind.remove.bind(Ind);
  Ind.add = function (id, params) {
    if (this.active[id]) _remove(id);
    var spec = this.registry[id];
    if (!spec) return false;
    var inst = { params: params || {}, spec: spec, series: spec.createSeries(null, params || {}) };
    this.active[id] = inst;
    this.refresh(id);
    layoutOsc();
    return true;
  };
  Ind.remove = function (id) {
    var inst = this.active[id];
    if (!inst) return;
    inst.series.forEach(function (s) {
      try { (inst.spec.overlay ? mainChart : oscChart).removeSeries(s); } catch (e) {}
    });
    delete this.active[id];
    layoutOsc();
  };

  C.extraHandlers.setIndicator = function (m) {
    if (m.enabled) Ind.add(m.id, m.params || {});
    else Ind.remove(m.id);
    C.post({ type: "indicatorsActive", ids: Object.keys(Ind.active) });
  };
})();

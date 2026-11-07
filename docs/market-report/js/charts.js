/* SVG 차트: 스파크라인 / 캔들 / 수급 막대 / 실적 막대 */
(function () {
  const MR = (window.MR = window.MR || {});
  const UP = '#d1243c', DOWN = '#2b57d8', UP_L = '#f1a1ad', DOWN_L = '#9db3f1';
  const fmt = function (n) { return Number(n).toLocaleString('ko-KR'); };
  MR.fmt = fmt;
  MR.colors = { UP: UP, DOWN: DOWN };

  MR.sparkline = function (vals, up, w, h) {
    w = w || 96; h = h || 32;
    const min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    const span = max - min || 1;
    const pts = vals.map(function (v, i) {
      return (i / (vals.length - 1) * (w - 2) + 1).toFixed(1) + ',' + ((1 - (v - min) / span) * (h - 4) + 2).toFixed(1);
    }).join(' ');
    return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h + '" aria-hidden="true">' +
      '<polyline fill="none" stroke="' + (up ? UP : DOWN) + '" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" points="' + pts + '"/></svg>';
  };

  MR.candleChart = function (el, bars, mas, o) {
    // 거래량 패널: 봉에 거래량(v)이 하나라도 있으면 가격 차트 아래에 붙인다 (샘플·구버전 데이터는 생략)
    const hasVol = bars.some(function (b) { return b.v > 0; });
    const VH = hasVol ? 54 : 0, VG = hasVol ? 10 : 0;
    const W = Math.max(el.clientWidth, 280), H = 300 + VH + VG, pl = 6, pr = 62, pt = 12, pb = 26;
    const PH = H - pt - pb - VH - VG; // 가격 영역 높이
    const dec = o.dec || 0; // 미국 주식은 소수점 2자리
    const fv = function (v) { return v >= 1e8 ? (v / 1e8).toFixed(1) + '억' : v >= 1e4 ? Math.round(v / 1e4).toLocaleString('ko-KR') + '만' : fmt(v); };
    const fp = function (v) { return Number(v).toLocaleString('ko-KR', { minimumFractionDigits: dec, maximumFractionDigits: dec }); };
    const n = bars.length, step = (W - pl - pr) / n, bw = Math.max(1.4, Math.min(14, step * 0.62));
    let lo = Infinity, hi = -Infinity;
    bars.forEach(function (b) { if (b.l < lo) lo = b.l; if (b.h > hi) hi = b.h; });
    mas.forEach(function (m) { m.values.forEach(function (v) { if (v != null) { if (v < lo) lo = v; if (v > hi) hi = v; } }); });
    const padv = (hi - lo) * 0.05; lo -= padv; hi += padv;
    const y = function (v) { return pt + (hi - v) / (hi - lo) * PH; };
    let vmax = 0;
    if (hasVol) bars.forEach(function (b) { if (b.v > vmax) vmax = b.v; });
    const x = function (i) { return pl + step * (i + 0.5); };

    let s = '<svg class="candle-svg" viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="캔들 차트">';
    for (let g = 0; g <= 4; g++) {
      const v = lo + (hi - lo) * g / 4, yy = y(v).toFixed(1);
      s += '<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + yy + '" y2="' + yy + '"/>' +
        '<text class="axis" x="' + (W - pr + 6) + '" y="' + (+yy + 4) + '">' + fp(v) + '</text>';
    }
    bars.forEach(function (b, i) {
      const col = b.c >= b.o ? UP : DOWN, xx = x(i).toFixed(1);
      s += '<line x1="' + xx + '" x2="' + xx + '" y1="' + y(b.h).toFixed(1) + '" y2="' + y(b.l).toFixed(1) + '" stroke="' + col + '"/>' +
        '<rect x="' + (x(i) - bw / 2).toFixed(1) + '" y="' + y(Math.max(b.o, b.c)).toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + Math.max(1, Math.abs(y(b.o) - y(b.c))).toFixed(1) + '" fill="' + col + '"/>';
    });
    if (hasVol) {
      const vb = H - pb, vt = vb - VH;
      s += '<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + vb + '" y2="' + vb + '"/>' +
        '<text class="axis" x="' + (W - pr + 6) + '" y="' + (vt + 10) + '">' + fv(vmax) + '</text>' +
        '<text class="axis" x="' + (W - pr + 6) + '" y="' + (vb - 2) + '">거래량</text>';
      bars.forEach(function (b, i) {
        if (!(b.v > 0)) return;
        const h = Math.max(1, b.v / vmax * VH);
        s += '<rect x="' + (x(i) - bw / 2).toFixed(1) + '" y="' + (vb - h).toFixed(1) + '" width="' + bw.toFixed(1) +
          '" height="' + h.toFixed(1) + '" fill="' + (b.c >= b.o ? UP_L : DOWN_L) + '"/>';
      });
    }
    mas.forEach(function (m) {
      let d = '', pen = false;
      m.values.forEach(function (v, i) {
        if (v == null) { pen = false; return; }
        d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1);
        pen = true;
      });
      s += '<path d="' + d + '" fill="none" stroke="' + m.color + '" stroke-width="1.4" stroke-linejoin="round"/>';
    });
    // 골든/데드 크로스 (20일선 vs 60일선)
    const m20 = mas.filter(function (m) { return m.n === 20; })[0], m60 = mas.filter(function (m) { return m.n === 60; })[0];
    if (m20 && m60) {
      for (let i = 1; i < n; i++) {
        const a = m20.values[i - 1], b = m60.values[i - 1], c = m20.values[i], d2 = m60.values[i];
        if (a == null || b == null || c == null || d2 == null) continue;
        if ((a - b) * (c - d2) < 0) {
          const golden = c > d2;
          s += '<g transform="translate(' + x(i).toFixed(1) + ',' + y(c).toFixed(1) + ')"><circle r="8" fill="' + (golden ? '#b7791f' : '#374151') +
            '"/><text class="cross" y="3.5">' + (golden ? '골' : '데') + '</text></g>';
        }
      }
    }
    s += '<text class="axis" x="' + pl + '" y="' + (H - 6) + '">' + o.leftLabel + '</text>' +
      '<text class="axis" x="' + (W - pr) + '" y="' + (H - 6) + '" text-anchor="end">' + o.rightLabel + '</text>' +
      '<line class="xhair" id="xh" y1="' + pt + '" y2="' + (H - pb) + '" style="display:none"/>' +
      '<rect class="hit" x="0" y="0" width="' + W + '" height="' + H + '"/></svg><div class="tip" hidden></div>';
    el.innerHTML = s;

    const svg = el.querySelector('svg'), tip = el.querySelector('.tip'), xh = el.querySelector('#xh');
    function hide() { tip.hidden = true; xh.style.display = 'none'; }
    svg.addEventListener('pointerleave', hide);
    svg.addEventListener('pointermove', function (e) {
      const r = svg.getBoundingClientRect(), k = W / r.width;
      const i = Math.floor(((e.clientX - r.left) * k - pl) / step);
      if (i < 0 || i >= n) return hide();
      const b = bars[i], prev = i > 0 ? bars[i - 1].c : null;
      const pct = prev ? (b.c - prev) / prev * 100 : null;
      xh.setAttribute('x1', x(i)); xh.setAttribute('x2', x(i)); xh.style.display = '';
      tip.innerHTML = '<b>' + b.d + '</b><span>시 ' + fp(b.o) + '</span><span>고 ' + fp(b.h) + '</span><span>저 ' + fp(b.l) + '</span><span>종 ' + fp(b.c) + '</span>' + (b.v > 0 ? '<span>거래량 ' + fmt(b.v) + '</span>' : '') +
        (pct == null ? '' : '<span class="' + (pct >= 0 ? 'up' : 'down') + '">' + (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%</span>');
      tip.hidden = false;
      const px = x(i) / k;
      tip.style.left = (px > r.width / 2 ? px - tip.offsetWidth - 12 : px + 12) + 'px';
    });
  };

  // days: [{d:'10.28', f:1240, i:-320}]
  MR.flowChart = function (el, days) {
    const W = Math.max(el.clientWidth, 260), H = 170, pt = 10, pb = 26, n = days.length;
    let mx = 0, mn = 0;
    days.forEach(function (d) { mx = Math.max(mx, d.f, d.i); mn = Math.min(mn, d.f, d.i); });
    const span = mx - mn || 1, y = function (v) { return pt + (mx - v) / span * (H - pt - pb); }, y0 = y(0);
    const gw = W / n, bw = Math.min(18, gw / 4);
    let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="외국인·기관 순매수 막대 차트">' +
      '<line class="grid" x1="0" x2="' + W + '" y1="' + y0 + '" y2="' + y0 + '"/>';
    days.forEach(function (d, i) {
      const cx = gw * (i + 0.5);
      [[d.f, -bw - 1.5, '외국인', UP, DOWN], [d.i, 1.5, '기관', UP_L, DOWN_L]].forEach(function (b) {
        const v = b[0], top = Math.min(y(v), y0), h = Math.max(1, Math.abs(y(v) - y0));
        s += '<rect x="' + (cx + b[1]).toFixed(1) + '" y="' + top.toFixed(1) + '" width="' + bw + '" height="' + h.toFixed(1) + '" rx="2" fill="' + (v >= 0 ? b[3] : b[4]) +
          '"><title>' + d.d + ' ' + b[2] + ' ' + (v > 0 ? '+' : '') + fmt(v) + '억</title></rect>';
      });
      s += '<text class="axis" x="' + cx + '" y="' + (H - 6) + '" text-anchor="middle">' + d.d + '</text>';
    });
    el.innerHTML = s + '</svg>';
  };

  MR.barChart = function (el, labels, values) {
    const W = Math.max(el.clientWidth, 260), H = 170, pt = 24, pb = 26, n = values.length;
    const known = values.filter(function (v) { return v != null; });
    const mx = Math.max(0, Math.max.apply(null, known)), mn = Math.min(0, Math.min.apply(null, known));
    const span = mx - mn || 1, y = function (v) { return pt + (mx - v) / span * (H - pt - pb); }, y0 = y(0);
    const gw = W / n, bw = Math.min(30, gw * 0.5);
    let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="영업이익 막대 차트">';
    values.forEach(function (v, i) {
      if (v == null) { s += '<text class="axis" x="' + gw * (i + 0.5) + '" y="' + (H - 6) + '" text-anchor="middle">' + labels[i] + '</text>'; return; }
      const cx = gw * (i + 0.5), est = /E$/.test(labels[i]), top = Math.min(y(v), y0), h = Math.max(2, Math.abs(y(v) - y0));
      s += '<rect x="' + (cx - bw / 2).toFixed(1) + '" y="' + top.toFixed(1) + '" width="' + bw + '" height="' + h.toFixed(1) + '" rx="3" fill="' + (est ? '#9ca3af' : '#111827') + '"/>' +
        '<text class="val" x="' + cx + '" y="' + (v >= 0 ? top - 6 : top + h + 14).toFixed(1) + '" text-anchor="middle">' + fmt(v) + '</text>' +
        '<text class="axis" x="' + cx + '" y="' + (H - 6) + '" text-anchor="middle">' + labels[i] + '</text>';
    });
    el.innerHTML = s + '</svg>';
  };
})();

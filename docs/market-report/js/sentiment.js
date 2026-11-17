/* 시장 심리 지표 4종 (QQQ 사이클 탭 하단): CNN · 반도체 · 크립토 공포탐욕지수 + VIX
 * 데이터: data/sentiment.json (tools/market_report/export_sentiment.py 가 수집 때마다 갱신)
 * 색: 한국식 관례 — 공포(하락 쪽)는 파랑, 탐욕(상승 쪽)은 빨강 */
(function () {
  const MR = (window.MR = window.MR || {});
  const SRC = '../data/sentiment.json';
  const Z = [ // CNN 구간
    { k: 'extreme_fear', t: '극단적 공포', a: 0, b: 25, c: '#2b3fa8' },
    { k: 'fear', t: '공포', a: 25, b: 45, c: '#5c7cfa' },
    { k: 'neutral', t: '중립', a: 45, b: 55, c: '#adb5bd' },
    { k: 'greed', t: '탐욕', a: 55, b: 75, c: '#f06a6a' },
    { k: 'extreme_greed', t: '극단적 탐욕', a: 75, b: 100, c: '#b4202f' }
  ];
  const zone = function (v) { for (let i = 0; i < Z.length; i++) if (v < Z[i].b) return Z[i]; return Z[Z.length - 1]; };
  const ymd = function (s) { return s.slice(0, 4) + '.' + s.slice(4, 6) + '.' + s.slice(6, 8); };
  const f1 = function (v) { return v == null ? '-' : Number(v).toFixed(1); };
  const sgn = function (v, d) { return (v > 0 ? '+' : '') + v.toFixed(d); };
  const cls = function (n) { return n > 0 ? 'up' : n < 0 ? 'down' : 'flat'; };

  MR.loadSentiment = function () {
    return fetch(SRC, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  };

  /* ---------- 반원 게이지 (0~100) ---------- */
  function gauge(score) {
    const cx = 100, cy = 100, R = 78, W = 14;
    const pt = function (s, r) { const a = Math.PI * (1 - s / 100); return [cx + r * Math.cos(a), cy - r * Math.sin(a)]; };
    let g = '<svg class="sm-gauge" viewBox="0 0 200 120" role="img" aria-label="공포탐욕 게이지 ' + f1(score) + '">';
    Z.forEach(function (z) {
      const p1 = pt(z.a + 0.4, R), p2 = pt(z.b - 0.4, R);
      g += '<path d="M' + p1[0].toFixed(1) + ' ' + p1[1].toFixed(1) + ' A' + R + ' ' + R + ' 0 0 1 ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1) +
        '" fill="none" stroke="' + z.c + '" stroke-width="' + W + '"/>';
    });
    [0, 25, 50, 75, 100].forEach(function (s) {
      const p = pt(s, R + 14);
      g += '<text class="sm-tick" x="' + p[0].toFixed(1) + '" y="' + (p[1] + 3).toFixed(1) + '" text-anchor="middle">' + s + '</text>';
    });
    const m = pt(score, R);
    g += '<circle cx="' + m[0].toFixed(1) + '" cy="' + m[1].toFixed(1) + '" r="9" fill="#fff" stroke="var(--ink)" stroke-width="3"/>' +
      '<text class="sm-gnum" x="' + cx + '" y="' + (cy - 6) + '" text-anchor="middle">' + Math.round(score) + '</text></svg>';
    return g;
  }

  /* ---------- 추이 차트 (hover 시 값 표시) ---------- */
  function trend(hist, o) {
    const W = 320, H = 110, pl = 4, pr = 26, pt = 6, pb = 6;
    const vals = hist.map(function (h) { return h[1]; });
    const lo = o.lo != null ? o.lo : Math.floor(Math.min.apply(null, vals) / 5) * 5, hi = o.hi != null ? o.hi : Math.ceil(Math.max.apply(null, vals) / 5) * 5;
    const x = function (i) { return pl + i / (hist.length - 1) * (W - pl - pr); };
    const y = function (v) { return pt + (hi - v) / (hi - lo) * (H - pt - pb); };
    let s = '<svg class="sm-trend" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + o.label + ' 1년 추이">';
    (o.bands || []).forEach(function (b) {
      s += '<rect x="' + pl + '" width="' + (W - pl - pr) + '" y="' + y(Math.min(b.b, hi)).toFixed(1) + '" height="' + Math.max(0, y(Math.max(b.a, lo)) - y(Math.min(b.b, hi))).toFixed(1) +
        '" fill="' + b.c + '" opacity=".13"/>';
    });
    (o.lines || []).forEach(function (v) {
      s += '<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(v).toFixed(1) + '" y2="' + y(v).toFixed(1) + '" stroke="#9ca3af" stroke-dasharray="3 3" stroke-width=".8"/>' +
        '<text class="sm-tick" x="' + (W - pr + 3) + '" y="' + (y(v) + 3).toFixed(1) + '">' + v + '</text>';
    });
    let d = '';
    hist.forEach(function (h, i) { d += (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(h[1]).toFixed(1); });
    s += '<path d="' + d + '" fill="none" stroke="var(--ink)" stroke-width="1.6" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>' +
      '<line class="sm-xh" y1="' + pt + '" y2="' + (H - pb) + '" style="display:none" vector-effect="non-scaling-stroke"/>' +
      '<rect class="sm-hit" x="0" y="0" width="' + W + '" height="' + H + '"/></svg>';
    return '<div class="sm-tw"><div class="sm-readout" data-last="' + ymd(hist[hist.length - 1][0]) + ' · ' + f1(vals[vals.length - 1]) + '">' +
      ymd(hist[hist.length - 1][0]) + ' · ' + f1(vals[vals.length - 1]) + '</div>' + s + '<div class="sm-range"><span>' + ymd(hist[0][0]) + '</span><span>1년 추이</span><span>' + ymd(hist[hist.length - 1][0]) + '</span></div></div>';
  }
  function wireTrend(card, hist, o) {
    const svg = card.querySelector('.sm-trend'), ro = card.querySelector('.sm-readout'), xh = card.querySelector('.sm-xh');
    if (!svg) return;
    const W = 320, pl = 4, pr = 26;
    const back = function () { ro.textContent = ro.dataset.last; xh.style.display = 'none'; };
    svg.addEventListener('pointerleave', back);
    svg.addEventListener('pointermove', function (e) {
      const r = svg.getBoundingClientRect(), k = W / r.width;
      const i = Math.round(((e.clientX - r.left) * k - pl) / ((W - pl - pr) / (hist.length - 1)));
      if (i < 0 || i >= hist.length) return back();
      const xx = pl + i / (hist.length - 1) * (W - pl - pr);
      xh.setAttribute('x1', xx); xh.setAttribute('x2', xx); xh.style.display = '';
      const v = hist[i][1], z = o.zone ? ' · ' + zone(v).t : '';
      ro.textContent = ymd(hist[i][0]) + ' · ' + f1(v) + z;
    });
  }

  /* ---------- 카드 ---------- */
  const PREV = [['day', '전일'], ['week', '1주 전'], ['month', '1개월 전'], ['year', '1년 전']];
  function prevRow(p, valFn) {
    return '<div class="sm-prev">' + PREV.map(function (q) {
      const v = p[q[0]];
      return '<div><small>' + q[1] + '</small>' + (v == null ? '<b>-</b>' : valFn(v)) + '</div>';
    }).join('') + '</div>';
  }
  function fgCard(id, title, sub, d, extra) {
    if (!d) return '<section class="card sm-card"><h3>' + title + '</h3><p class="empty">데이터를 불러오지 못했습니다.</p></section>';
    const z = zone(d.score), chg = d.prev && d.prev.day != null ? d.score - d.prev.day : null;
    return '<section class="card sm-card" id="' + id + '"><div class="sm-h"><h3>' + title + '</h3><small>' + sub + (d.stale ? ' · 이전 값' : '') + '</small></div>' +
      gauge(d.score) +
      '<div class="sm-state"><b style="color:' + z.c + '">' + z.t + '</b>' +
      (chg == null ? '' : '<span class="' + cls(chg) + '">전일 대비 ' + sgn(chg, 1) + '</span>') + '</div>' +
      prevRow(d.prev || {}, function (v) { return '<b><i style="background:' + zone(v).c + '"></i>' + f1(v) + '</b>'; }) +
      (extra || '') + trend(d.hist, { lo: 0, hi: 100, bands: Z, lines: [25, 50, 75], label: title }) + '</section>';
  }
  function semiParts(d) {
    if (!d.parts) return '';
    return '<div class="sm-parts">' + d.parts.map(function (p) {
      const z = zone(p.score);
      return '<div class="sm-part"><span title="' + p.desc + '">' + p.name + '</span><div class="sm-bar"><i style="width:' + Math.max(2, p.score) + '%;background:' + z.c + '"></i></div>' +
        '<b>' + Math.round(p.score) + '</b><em>' + p.raw + '</em></div>';
    }).join('') + '</div>';
  }
  const VZ = [ // VIX 구간 (높을수록 공포)
    { t: '안정', a: 0, b: 15, c: '#f06a6a' }, { t: '보통', a: 15, b: 20, c: '#adb5bd' },
    { t: '경계', a: 20, b: 30, c: '#5c7cfa' }, { t: '공포', a: 30, b: 100, c: '#2b3fa8' }
  ];
  function vixCard(d) {
    if (!d) return '<section class="card sm-card"><h3>VIX 변동성지수</h3><p class="empty">데이터를 불러오지 못했습니다.</p></section>';
    const lv = VZ.filter(function (z) { return d.value >= z.a && d.value < z.b; })[0] || VZ[3];
    const MAX = 45, pos = function (v) { return Math.min(100, v / MAX * 100); };
    const bar = '<div class="sm-vscale">' + VZ.map(function (z) { return '<i style="left:' + pos(z.a) + '%;width:' + (pos(Math.min(z.b, MAX)) - pos(z.a)) + '%;background:' + z.c + '"></i>'; }).join('') +
      '<u style="left:' + pos(d.value) + '%"></u></div>' +
      '<div class="sm-vlab"><span>0</span><span style="left:' + pos(15) + '%">15</span><span style="left:' + pos(20) + '%">20</span><span style="left:' + pos(30) + '%">30</span><span style="left:100%">45+</span></div>';
    const range = '<div class="sm-prev sm-prev3"><div><small>52주 최저</small><b>' + f1(d.lo52) + '</b></div><div><small>52주 최고</small><b>' + f1(d.hi52) + '</b></div>' +
      '<div><small>1개월 전</small><b>' + f1(d.month) + '</b></div></div>';
    return '<section class="card sm-card" id="smVix"><div class="sm-h"><h3>VIX 변동성지수</h3><small>' + ymd(d.asOf) + ' 종가' + (d.stale ? ' · 이전 값' : '') + '</small></div>' +
      '<div class="sm-vnum"><strong>' + f1(d.value) + '</strong><span class="' + cls(d.chg) + '">' + sgn(d.chg, 1) + ' (' + sgn(d.pct, 1) + '%)</span></div>' +
      '<div class="sm-state"><b style="color:' + lv.c + '">' + lv.t + ' 구간</b><span class="flat">20 이상 불안 · 30 이상 공포</span></div>' +
      bar + range + trend(d.hist, { lines: [20, 30], bands: VZ, label: 'VIX' }) + '</section>';
  }

  MR.sentiment = {
    html: function () {
      return '<div id="smWrap"><section class="card sm-intro"><h2>시장 심리 지표</h2><p class="note" style="margin-top:6px">불러오는 중…</p></section></div>';
    },
    mount: function (root, ctx) {
      const alive = function () { return root.isConnected && ctx.route().name === 'cycle'; };
      MR.loadSentiment().then(function (d) {
        if (!alive()) return;
        root.innerHTML = '<div class="sm-title"><h2>시장 심리 지표</h2><small>' + (d.generatedAt || '').slice(5, 16).replace('T', ' ') + ' 수집 · CNN · alternative.me · yfinance</small></div>' +
          '<div class="sm-grid">' +
          fgCard('smCnn', 'CNN 공포·탐욕지수', '미국 주식시장', d.cnn) +
          fgCard('smSemi', '반도체 공포·탐욕지수', '필라델피아 반도체지수(SOX) 기반 · 자체 산출', d.semi, d.semi ? semiParts(d.semi) : '') +
          fgCard('smCrypto', '크립토 공포·탐욕지수', '비트코인 중심 · 24시간', d.crypto) +
          vixCard(d.vix) + '</div>' +
          '<p class="note">공포·탐욕지수는 0(극단적 공포)~100(극단적 탐욕)입니다. 공포가 클수록 시장이 움츠러든 상태로, 역발상 지표로 참고하지만 매수·매도 신호가 아닙니다. ' +
          '반도체 지수는 공식 지표가 없어 SOX의 125일선 대비 모멘텀·52주 범위 내 위치·RSI(14)·20일 변동성·QQQ 대비 20일 상대강도를 각각 최근 1년 내 백분위로 환산해 평균한 자체 산출값입니다(CNN 지수와 방식이 다릅니다).</p>';
        [['smCnn', d.cnn, true], ['smSemi', d.semi, true], ['smCrypto', d.crypto, true], ['smVix', d.vix, false]].forEach(function (c) {
          const el = root.querySelector('#' + c[0]);
          if (el && c[1] && c[1].hist) wireTrend(el, c[1].hist, { zone: c[2] });
        });
      }).catch(function () {
        if (alive()) root.innerHTML = '<section class="card"><h2>시장 심리 지표</h2><p class="empty">지표 데이터를 불러오지 못했습니다. 다음 갱신 후 다시 확인해 주세요.</p></section>';
      });
    }
  };
})();

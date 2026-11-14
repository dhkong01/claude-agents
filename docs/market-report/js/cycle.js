/* QQQ 사이클 탭: 2018년 하반기 경로와 2026~27 경로를 "고점 이후 거래일" 기준으로 겹쳐 그린다.
 * 데이터: data/cycle_qqq.json (tools/market_report/export_cycle_qqq.py 가 수집 때마다 갱신) */
(function () {
  const MR = (window.MR = window.MR || {});
  const SRC = '../data/cycle_qqq.json';
  const C_REF = '#4a6cf0', C_CUR = '#e8590c';
  const EARLY = 60; // "초반 확대" 보기에서 보여 줄 마지막 일차
  const ui = { zoom: 'all', proj: false }; // 보기 옵션(화면을 떠났다 와도 유지)
  const md = function (iso) { return (+iso.slice(5, 7)) + '/' + (+iso.slice(8, 10)); };
  const ymd = function (iso) { return iso.replace(/-/g, '.'); };
  const f1 = function (v) { return Number(v).toFixed(1); };
  const sg = function (v, d) { return (v > 0 ? '+' : '') + v.toFixed(d); };
  const cls = function (n) { return n > 0 ? 'up' : n < 0 ? 'down' : 'flat'; };
  const usd = function (v) { return '$' + Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };

  MR.loadCycle = function () {
    return fetch(SRC, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  };

  /* 예상선 3종 (얕은 · 중간 · 깊은 조정). 오늘 값에서 출발하고, 하락 폭이 클수록 "처음부터 끝까지" 더 아래에 있다.
   *  1) 단기: 최근 15거래일 로그 회귀 기울기(m = 현재 추세)를 따라간다 — 비중 w = exp(-k/TAU), k = 오늘로부터 거래일 수
   *  2) 장기: 시나리오 목표 경로로 수렴한다. 목표 경로의 "모양(등락 질감·저점 시기·회복 속도)"은 2018 경로에서 빌리고,
   *     "수준"은 시나리오가 정한다:
   *       저점  = 얕음: 지금까지 저점을 소폭 재시험 / 깊음: 2018 같은 하락률(오늘 값에 환산) / 중간: 둘의 중간
   *       종료값 = 저점 + rho × (100 − 저점)   (rho: 회복 비율 0.85 / 0.6 / 0.4)
   *  경로(t) = (1−w)·목표(t) + w·추세선(t)  → 추세선이 같으므로 시나리오 간 순서(얕음 ≥ 중간 ≥ 깊음)는 항상 유지된다 */
  const TAU = 15;
  const SCEN = [
    { key: 'shallow', name: '얕은 조정', short: '얕음', rho: 0.85, color: '#d9a400' },
    { key: 'mid', name: '중간 조정', short: '중간', rho: 0.6, color: '#e8590c' },
    { key: 'deep', name: '깊은 조정', short: '깊음', rho: 0.4, color: '#a61e4d' }
  ];
  const clamp01 = function (v) { return Math.max(0, Math.min(1, v)); }; // 비율을 0~1로 제한 → 하락이 클수록 항상 더 아래
  function projections(d) {
    const cv = d.cur.v, rv = d.ref.v, now = cv.length - 1, last = rv.length - 1, base = cv[now];
    const blank = function () { return rv.map(function () { return null; }); };
    // 최근 추세: 최근 15거래일 ln(가격) 선형회귀 기울기 (하루 수익률), 과도한 값은 제한
    const n0 = Math.min(15, now + 1);
    let m = 0;
    if (n0 >= 5) {
      let sx = 0, sy = 0, sxx = 0, sxy = 0;
      for (let j = 0; j < n0; j++) { const yv = Math.log(cv[now - n0 + 1 + j]); sx += j; sy += yv; sxx += j * j; sxy += j * yv; }
      m = (n0 * sxy - sx * sy) / (n0 * sxx - sx * sx);
      m = Math.max(-0.012, Math.min(0.006, m));
    }
    // 2018 경로에서 빌리는 모양: 저점 시기(T)와 오늘·저점·종료 값
    let T = 0;
    rv.forEach(function (v, i) { if (v < rv[T]) T = i; });
    const rNow = rv[now], rTr = rv[T], rEnd = rv[last];
    const curLow = Math.min.apply(null, cv);
    // 저점 수준 (얕음 ≥ 중간 ≥ 깊음, 모두 오늘 값보다 아래)
    const tS = Math.min(curLow * 0.985, base * 0.97);
    const tD = Math.min(base * rTr / rNow, tS - 2);
    const tM = (tS + tD) / 2;
    const troughs = [tS, tM, tD];
    return SCEN.map(function (sc, si) {
      const out = blank();
      out[now] = base;
      const tr = troughs[si];
      const end = now < T ? tr + sc.rho * (100 - tr) : base * Math.pow(rEnd / rNow, 1 - 0.35 * si); // 2018 저점 이후면 회복 강도만 달리
      for (let i = now + 1; i <= last; i++) {
        let tgt;
        if (now < T) {
          tgt = i <= T ? base + (tr - base) * clamp01((rNow - rv[i]) / (rNow - rTr)) : tr + (end - tr) * clamp01((rv[i] - rTr) / (rEnd - rTr));
        } else {
          tgt = base + (end - base) * ((rv[i] - rNow) / (rEnd - rNow || 1));
        }
        const w = Math.exp(-(i - now) / TAU);
        out[i] = (1 - w) * tgt + w * base * Math.exp(m * (i - now));
      }
      return { sc: sc, v: out };
    });
  }

  /* ---------- 차트 ---------- */
  // o: { xmax: 보여 줄 마지막 일차(기본 endDay), proj: 예상선 표시 }
  MR.cycleChart = function (el, d, o) {
    o = o || {};
    const END = d.endDay, X = Math.min(o.xmax || END, END), cur = d.cur, ref = d.ref, now = cur.v.length - 1;
    const projs = o.proj ? projections(d) : null;
    const W = Math.max(el.clientWidth, 300), H = W < 520 ? 340 : 400;
    const pl = 38, pr = 16, pt = 34, pb = 46;
    const vis = [];
    for (let i = 0; i <= X; i++) {
      vis.push(ref.v[i]);
      if (i < cur.v.length) vis.push(cur.v[i]);
      if (projs) projs.forEach(function (p) { if (p.v[i] != null) vis.push(p.v[i]); });
    }
    const lo = Math.floor((Math.min.apply(null, vis) - 3.5) / 5) * 5; // 저점 아래에 라벨을 둘 여유
    const hi = Math.ceil((Math.max.apply(null, vis) + 1) / 5) * 5;
    const x = function (day) { return pl + day / X * (W - pl - pr); };
    const y = function (v) { return pt + (hi - v) / (hi - lo) * (H - pt - pb); };
    const poly = function (vals) {
      let p = '', pen = false;
      vals.slice(0, X + 1).forEach(function (v, i) {
        if (v == null) { pen = false; return; }
        p += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); pen = true;
      });
      return p;
    };

    let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="QQQ 2018년 사이클 비교 차트">';
    for (let g = lo; g <= hi; g += 5) {
      s += '<line class="cy-grid' + (g === 100 ? ' base' : '') + '" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(g).toFixed(1) + '" y2="' + y(g).toFixed(1) + '"/>' +
        '<text class="cy-axis" x="' + (pl - 6) + '" y="' + (y(g) + 4).toFixed(1) + '" text-anchor="end">' + g + '</text>';
    }
    (X <= EARLY ? [0, 10, 20, 30, 40, 50, 60] : [0, 20, 40, 60, 80, 100, 120, END]).filter(function (t) { return t <= X; }).forEach(function (t) {
      s += '<text class="cy-axis" x="' + x(t).toFixed(1) + '" y="' + (H - pb + 16) + '" text-anchor="middle">' + t + '</text>' +
        '<text class="cy-axis dim" x="' + x(t).toFixed(1) + '" y="' + (H - pb + 31) + '" text-anchor="middle">' + md(d.cal[t]) + '</text>';
    });
    d.fomc.cur.filter(function (f) { return f.day <= X; }).forEach(function (f) {
      s += '<line class="cy-fomc" x1="' + x(f.day).toFixed(1) + '" x2="' + x(f.day).toFixed(1) + '" y1="' + (pt - 6) + '" y2="' + (H - pb) + '"/>' +
        '<text class="cy-axis cy-fomc-t" x="' + (x(f.day) - 5).toFixed(1) + '" y="' + (pt - 12) + '" text-anchor="end">' + (W < 520 ? "'26 FOMC" : '2026 FOMC ' + md(f.date)) + '</text>';
    });
    d.fomc.ref.filter(function (f) { return f.day <= X; }).forEach(function (f) {
      s += '<line class="cy-fomc" x1="' + x(f.day).toFixed(1) + '" x2="' + x(f.day).toFixed(1) + '" y1="' + (pt - 6) + '" y2="' + (H - pb) + '"/>' +
        '<text class="cy-axis cy-fomc-t" x="' + (x(f.day) + 5).toFixed(1) + '" y="' + (pt - 12) + '">' + (W < 520 ? "'18 FOMC" : '2018 FOMC ' + md(f.date)) + '</text>';
    });
    if (projs) projs.forEach(function (p) {
      s += '<path d="' + poly(p.v) + '" fill="none" stroke="' + p.sc.color + '" stroke-width="2" stroke-dasharray="5 4" stroke-linejoin="round" opacity=".85"/>';
    });
    s += '<path d="' + poly(ref.v) + '" fill="none" stroke="' + C_REF + '" stroke-width="2" stroke-linejoin="round"/>' +
      '<path d="' + poly(cur.v) + '" fill="none" stroke="' + C_CUR + '" stroke-width="2.4" stroke-linejoin="round"/>';
    if (cur.v.length <= 80) {
      cur.v.forEach(function (v, i) { if (i <= X) s += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) + '" r="2.6" fill="' + C_CUR + '"/>'; });
    }
    const marks = d.marks.filter(function (m) { return m.day <= X; });
    if (projs) projs.forEach(function (p) { // 시나리오별 예상 저점
      let mi = -1;
      p.v.forEach(function (v, i) { if (v != null && i > now && i <= X && (mi < 0 || v < p.v[mi])) mi = i; });
      if (mi > 0 && p.v[mi] < cur.v[now]) marks.push({ s: p.sc.key, color: p.sc.color, day: mi, v: p.v[mi], label: p.sc.short + ' ' + f1(p.v[mi]), pos: p.sc.key === 'deep' ? 'left' : 'below' });
    });
    const off = { above: [0, -11, 'middle'], below: [0, 18, 'middle'], right: [9, 4, 'start'], left: [-9, 4, 'end'] };
    marks.forEach(function (m) {
      const o2 = off[m.pos] || off.above, col = m.color || (m.s === 'cur' ? C_CUR : C_REF);
      s += '<circle cx="' + x(m.day).toFixed(1) + '" cy="' + y(m.v).toFixed(1) + '" r="4.4" fill="' + col + '" stroke="#fff" stroke-width="1.5"/>' +
        '<text class="cy-mark" data-mx="' + x(m.day).toFixed(1) + '" data-pos="' + m.pos + '" x="' + (x(m.day) + o2[0]).toFixed(1) + '" y="' + (y(m.v) + o2[1]).toFixed(1) + '" text-anchor="' + o2[2] + '">' + m.label + '</text>';
    });
    s += '<line class="cy-xh" id="cyxh" y1="' + pt + '" y2="' + (H - pb) + '" style="display:none"/>' +
      '<rect class="cy-hit" x="0" y="0" width="' + W + '" height="' + H + '"/></svg><div class="tip" hidden></div>';
    el.innerHTML = s;

    // 끝에서 라벨이 잘리면: 좌우 라벨은 점 반대편으로 뒤집고, 그래도 넘치면 안쪽으로 밀어 준다
    Array.prototype.forEach.call(el.querySelectorAll('text.cy-mark, text.cy-fomc-t'), function (t) {
      let b = t.getBBox();
      const mx = +t.dataset.mx;
      if (t.dataset.pos === 'right' && b.x + b.width > W - 4) { t.setAttribute('text-anchor', 'end'); t.setAttribute('x', (mx - 9).toFixed(1)); b = t.getBBox(); }
      else if (t.dataset.pos === 'left' && b.x < 4) { t.setAttribute('text-anchor', 'start'); t.setAttribute('x', (mx + 9).toFixed(1)); b = t.getBBox(); }
      let dx = 0;
      if (b.x < 4) dx = 4 - b.x; else if (b.x + b.width > W - 4) dx = W - 4 - (b.x + b.width);
      if (dx) t.setAttribute('x', (+t.getAttribute('x') + dx).toFixed(1));
    });

    const svg = el.querySelector('svg'), tip = el.querySelector('.tip'), xh = el.querySelector('#cyxh');
    function hide() { tip.hidden = true; xh.style.display = 'none'; }
    svg.addEventListener('pointerleave', hide);
    svg.addEventListener('pointermove', function (e) {
      const r = svg.getBoundingClientRect(), k = W / r.width;
      const day = Math.round(((e.clientX - r.left) * k - pl) / ((W - pl - pr) / X));
      if (day < 0 || day > X) return hide();
      xh.setAttribute('x1', x(day)); xh.setAttribute('x2', x(day)); xh.style.display = '';
      const has = day < cur.v.length, rv = ref.v[day];
      tip.innerHTML = '<b>' + day + '일차 · ' + ymd(d.cal[day]) + '</b>' +
        '<span style="color:#aab8ff">2018 ' + md(ref.dates[day]) + ' · ' + f1(rv) + '</span>' +
        (has ? '<span style="color:#ffb085">2026 · ' + f1(cur.v[day]) + '</span><span>2018 대비 ' + sg(cur.v[day] - rv, 1) + '%p</span>'
          : projs ? projs.map(function (p) { return '<span style="color:' + p.sc.color + '">' + p.sc.short + ' ' + f1(p.v[day]) + '</span>'; }).join('') : '<span>2026 · 아직 오지 않은 날</span>');
      tip.hidden = false;
      const px = x(day) / k;
      tip.style.left = (px > r.width / 2 ? px - tip.offsetWidth - 12 : px + 12) + 'px';
    });
  };

  /* ---------- 화면 조각 ---------- */
  // 2018 경로와의 유사도: 일간 등락률 상관계수 + 평균 격차(%p). 표본이 적으면(5일 미만) 계산하지 않는다
  function similarity(d) {
    const n = d.cur.v.length - 1;
    if (n < 5) return null;
    const a = [], b = [];
    let gap = 0;
    for (let i = 1; i <= n; i++) {
      a.push(d.cur.v[i] / d.cur.v[i - 1] - 1); b.push(d.ref.v[i] / d.ref.v[i - 1] - 1);
      gap += d.cur.v[i] - d.ref.v[i];
    }
    const mean = function (z) { return z.reduce(function (p, q) { return p + q; }, 0) / z.length; };
    const ma = mean(a), mb = mean(b);
    let sab = 0, saa = 0, sbb = 0;
    a.forEach(function (v, i) { sab += (v - ma) * (b[i] - mb); saa += (v - ma) * (v - ma); sbb += (b[i] - mb) * (b[i] - mb); });
    return { r: saa && sbb ? sab / Math.sqrt(saa * sbb) : 0, gap: gap / n, n: n };
  }
  function kpis(d) {
    const cur = d.cur, ref = d.ref, day = cur.v.length - 1, v = cur.v[day], rv = ref.v[day];
    const lo = cur.v.reduce(function (a, b, i) { return b < cur.v[a] ? i : a; }, 0);
    const gap = v - rv, left = d.endDay - day, sim = similarity(d);
    const tile = function (label, value, sub) { return '<div class="cy-kpi"><small>' + label + '</small><strong>' + value + '</strong><span>' + sub + '</span></div>'; };
    return '<div class="cy-kpis">' +
      tile('현재 (고점=100)', f1(v), 'QQQ ' + usd(cur.close[day]) + ' · ' + md(cur.dates[day])) +
      tile('고점 대비', '<b class="' + cls(v - 100) + '">' + sg(v - 100, 1) + '%</b>', md(cur.peak) + ' 고점 ' + usd(cur.peakClose)) +
      tile('2018년 같은 시점', f1(rv), '<b class="' + cls(gap) + '">' + sg(gap, 1) + '%p</b> (' + ymd(ref.dates[day]) + ')') +
      tile('지금까지 저점', f1(cur.v[lo]), md(cur.dates[lo]) + ' · 고점 대비 ' + sg(cur.v[lo] - 100, 1) + '%') +
      tile('2018 경로와 유사도', sim ? '상관 ' + sim.r.toFixed(2) : '집계 중', sim ? '평균 격차 ' + sg(sim.gap, 1) + '%p · 일간 등락 ' + sim.n + '일' : '5거래일 이상 쌓이면 표시') +
      tile('추적 진행', day + ' / ' + d.endDay + '일', left > 0 ? '~' + ymd(d.endDate) + ' · ' + left + '거래일 남음' : '추적 기간 종료 (' + ymd(d.endDate) + ')') +
      '</div>';
  }
  function milestones(d) {
    const cur = d.cur, ref = d.ref, rows = [{ day: 0, name: '0일차 (고점 직후 조정 시작)', v: ref.v[0], date: ref.dates[0] }];
    d.marks.forEach(function (m) {
      if (m.s === 'ref') rows.push({ day: m.day, name: m.label.indexOf('저점') >= 0 ? '저점 (고점 대비 ' + sg(m.v - 100, 0) + '%)' : m.label, v: m.v, date: m.date });
    });
    d.fomc.ref.forEach(function (f) { rows.push({ day: f.day, name: 'FOMC 결정', v: ref.v[f.day], date: f.date }); });
    rows.sort(function (a, b) { return a.day - b.day; });
    const body = rows.map(function (r) {
      const real = r.day < cur.v.length ? f1(cur.v[r.day]) : '<span class="flat">예정</span>';
      return '<tr><td>' + r.name + '</td><td class="num">' + ymd(r.date) + '</td><td class="num">' + r.day + '</td><td class="num">' + f1(r.v) + '</td>' +
        '<td class="num"><b>' + ymd(d.cal[r.day]) + '</b></td><td class="num">' + real + '</td></tr>';
    }).join('');
    return '<section class="card"><h2>2018 사이클 지도</h2><div class="tbl-wrap"><table class="tbl"><thead><tr><th>시점</th><th class="num">2018 날짜</th><th class="num">거래일</th>' +
      '<th class="num">2018 지수</th><th class="num">2026~27 대응일</th><th class="num">2026 실제</th></tr></thead><tbody>' + body + '</tbody></table></div>' +
      '<p class="note">2018년의 각 변곡점이 2026~27년의 어느 날에 해당하는지 보여 줍니다(고점 후 거래일 기준, 미국 휴장일 반영). 같은 경로를 반복한다는 뜻이 아니라 비교용 기준선입니다.</p></section>';
  }
  function controls() {
    const z = function (k, t) { return '<button type="button" data-zoom="' + k + '" class="' + (ui.zoom === k ? 'active' : '') + '">' + t + '</button>'; };
    return '<div class="cy-ctl"><div class="seg" id="cyZoom">' + z('all', '전체') + z('early', '초반 확대') + '</div>' +
      '<button type="button" class="btn-line cy-proj' + (ui.proj ? ' on' : '') + '" data-proj aria-pressed="' + ui.proj + '">예상선</button></div>';
  }
  function bodyHtml(d, ctx) {
    const cur = d.cur, last = cur.dates[cur.dates.length - 1];
    const legend = '<div class="ma-legend">' +
      '<span class="ma-chip"><i style="background:' + C_REF + '"></i>2018~19 (' + md(d.ref.peak) + ' 고점=100, ' + md(d.ref.start) + '부터)</span>' +
      '<span class="ma-chip"><i style="background:' + C_CUR + '"></i>2026 (' + md(cur.peak) + ' 고점=100)</span>' +
      '<span class="ma-chip"><i class="cy-dash"></i>FOMC</span>' +
      '<span class="ma-chip cy-proj-chip"' + (ui.proj ? '' : ' hidden') + '>예상(참고용) ' + SCEN.map(function (sc) { return '<i class="cy-dash" style="border-top-color:' + sc.color + '"></i>' + sc.name; }).join(' ') + '</span></div>';
    return ctx.pageHead('QQQ 사이클 추적 · 2018년 하반기 비교', ymd(last) + ' 종가 기준 · ' + d.generatedAt.slice(5, 16).replace('T', ' ') + ' 수집 · yfinance') +
      kpis(d) +
      '<section class="card"><div class="card-head"><h2>고점 이후 경로 비교</h2>' + controls() + '</div>' + legend + '<div class="cycle" id="cycleChart"></div>' +
      '<p class="note">QQQ 종가를 고점=100으로 지수화했습니다. 가로축은 고점 이후 거래일 수(위)와 2026~27년 대응 날짜(아래)이고, 2018년 선은 ' + md(d.ref.start) +
      '(2018년 8/29 고점 직후 조정이 시작된 날 = 2026 고점일과 같은 0일차)부터 실제 일별 종가로 겹쳤습니다. 2026년 선은 ' + ymd(d.endDate) + '(' + d.endDay + '일차)까지 수집 때마다 이어 그려집니다.</p>' +
      '<p class="note cy-proj-note"' + (ui.proj ? '' : ' hidden') + '>예상선은 오늘 값에서 출발해 최근 15거래일 추세를 따라가다가(약 15거래일 만에 영향 감소) 시나리오별 경로로 수렴합니다. 경로의 모양(저점 시기·회복 속도)은 2018년에서 빌리고 수준은 하락 폭으로 나눴습니다 — 얕은 조정: 지금까지 저점을 소폭 재시험 후 대부분 회복 · 중간 조정: 그 중간 · 깊은 조정: 2018과 같은 하락률 후 더딘 회복. 하락이 클수록 전 구간에서 더 아래에 놓이며, 예측이 아니라 가정입니다.</p></section>' +
      milestones(d);
  }

  /* ---------- 뷰 (app.js 라우터가 호출) ---------- */
  MR.cycle = {
    view: function (ctx) {
      const head = ctx.pageHead('QQQ 사이클 추적 · 2018년 하반기 비교', '2018년 하반기 경로와 비교');
      return { html: head + '<section class="card"><p class="empty">사이클 데이터를 불러오는 중…</p></section>', mount: function () {
        MR.loadCycle().then(function (d) {
          if (ctx.route().name !== 'cycle') return; // 그 사이 다른 화면으로 이동했으면 무시
          ctx.view.innerHTML = bodyHtml(d, ctx);
          const draw = function () {
            const el = ctx.view.querySelector('#cycleChart');
            if (el) MR.cycleChart(el, d, { xmax: ui.zoom === 'early' ? EARLY : d.endDay, proj: ui.proj });
          };
          const ctl = ctx.view.querySelector('.cy-ctl');
          ctl.addEventListener('click', function (e) {
            const b = e.target.closest('button');
            if (!b) return;
            if (b.dataset.zoom) {
              ui.zoom = b.dataset.zoom;
              Array.prototype.forEach.call(ctl.querySelectorAll('#cyZoom button'), function (x) { x.classList.toggle('active', x.dataset.zoom === ui.zoom); });
            } else if ('proj' in b.dataset) {
              ui.proj = !ui.proj;
              b.classList.toggle('on', ui.proj); b.setAttribute('aria-pressed', ui.proj);
              ctx.view.querySelector('.cy-proj-chip').hidden = !ui.proj;
              ctx.view.querySelector('.cy-proj-note').hidden = !ui.proj;
            } else return;
            draw();
          });
          draw(); ctx.setRedraw(draw);
          requestAnimationFrame(draw); // 폰트·레이아웃 확정 후 한 번 더
        }).catch(function () {
          if (ctx.route().name === 'cycle') ctx.view.innerHTML = head + '<section class="card"><p class="empty">사이클 데이터를 불러오지 못했습니다. 다음 갱신 후 다시 확인해 주세요.</p></section>';
        });
      } };
    },
  };
})();

/* QQQ 사이클 탭: 2018년 하반기 경로와 2026~27 경로를 "고점 이후 거래일" 기준으로 겹쳐 그린다.
 * 데이터: data/cycle_qqq.json (tools/market_report/export_cycle_qqq.py 가 수집 때마다 갱신) */
(function () {
  const MR = (window.MR = window.MR || {});
  const SRC = '../data/cycle_qqq.json';
  const C_REF = '#4a6cf0', C_CUR = '#e8590c';
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

  /* ---------- 차트 ---------- */
  MR.cycleChart = function (el, d) {
    const END = d.endDay, cur = d.cur, ref = d.ref;
    const W = Math.max(el.clientWidth, 300), H = W < 520 ? 340 : 400;
    const pl = 38, pr = 16, pt = 34, pb = 46;
    const all = cur.v.concat(ref.v);
    const lo = Math.floor((Math.min.apply(null, all) - 1.5) / 5) * 5;
    const hi = Math.ceil((Math.max.apply(null, all) + 1) / 5) * 5;
    const x = function (day) { return pl + day / END * (W - pl - pr); };
    const y = function (v) { return pt + (hi - v) / (hi - lo) * (H - pt - pb); };
    const poly = function (vals) {
      return vals.map(function (v, i) { return (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1); }).join('');
    };

    let s = '<svg viewBox="0 0 ' + W + ' ' + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="QQQ 2018년 사이클 비교 차트">';
    for (let g = lo; g <= hi; g += 5) {
      s += '<line class="cy-grid' + (g === 100 ? ' base' : '') + '" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(g).toFixed(1) + '" y2="' + y(g).toFixed(1) + '"/>' +
        '<text class="cy-axis" x="' + (pl - 6) + '" y="' + (y(g) + 4).toFixed(1) + '" text-anchor="end">' + g + '</text>';
    }
    [0, 20, 40, 60, 80, 100, 120, END].forEach(function (t) {
      s += '<text class="cy-axis" x="' + x(t).toFixed(1) + '" y="' + (H - pb + 16) + '" text-anchor="middle">' + t + '</text>' +
        '<text class="cy-axis dim" x="' + x(t).toFixed(1) + '" y="' + (H - pb + 31) + '" text-anchor="middle">' + md(d.cal[t]) + '</text>';
    });
    d.fomc.cur.forEach(function (f) {
      s += '<line class="cy-fomc" x1="' + x(f.day).toFixed(1) + '" x2="' + x(f.day).toFixed(1) + '" y1="' + (pt - 6) + '" y2="' + (H - pb) + '"/>' +
        '<text class="cy-axis" x="' + (x(f.day) - 5).toFixed(1) + '" y="' + (pt - 12) + '" text-anchor="end">2026 FOMC ' + md(f.date) + '</text>';
    });
    d.fomc.ref.forEach(function (f) {
      s += '<line class="cy-fomc" x1="' + x(f.day).toFixed(1) + '" x2="' + x(f.day).toFixed(1) + '" y1="' + (pt - 6) + '" y2="' + (H - pb) + '"/>' +
        '<text class="cy-axis" x="' + (x(f.day) + 5).toFixed(1) + '" y="' + (pt - 12) + '">2018 FOMC ' + md(f.date) + '</text>';
    });
    s += '<path d="' + poly(ref.v) + '" fill="none" stroke="' + C_REF + '" stroke-width="2" stroke-linejoin="round"/>' +
      '<path d="' + poly(cur.v) + '" fill="none" stroke="' + C_CUR + '" stroke-width="2.4" stroke-linejoin="round"/>';
    if (cur.v.length <= 80) {
      cur.v.forEach(function (v, i) { s += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(v).toFixed(1) + '" r="2.6" fill="' + C_CUR + '"/>'; });
    }
    const off = { above: [0, -11, 'middle'], below: [0, 18, 'middle'], right: [9, 4, 'start'], left: [-9, 4, 'end'] };
    d.marks.forEach(function (m) {
      const o = off[m.pos] || off.above, col = m.s === 'cur' ? C_CUR : C_REF;
      s += '<circle cx="' + x(m.day).toFixed(1) + '" cy="' + y(m.v).toFixed(1) + '" r="4.4" fill="' + col + '" stroke="#fff" stroke-width="1.5"/>' +
        '<text class="cy-mark" x="' + (x(m.day) + o[0]).toFixed(1) + '" y="' + (y(m.v) + o[1]).toFixed(1) + '" text-anchor="' + o[2] + '">' + m.label + '</text>';
    });
    s += '<line class="cy-xh" id="cyxh" y1="' + pt + '" y2="' + (H - pb) + '" style="display:none"/>' +
      '<rect class="cy-hit" x="0" y="0" width="' + W + '" height="' + H + '"/></svg><div class="tip" hidden></div>';
    el.innerHTML = s;

    // 오른쪽·왼쪽 끝에서 라벨이 잘리지 않게 안쪽으로 밀어 준다
    Array.prototype.forEach.call(el.querySelectorAll('text.cy-mark'), function (t) {
      const b = t.getBBox();
      let dx = 0;
      if (b.x < 4) dx = 4 - b.x; else if (b.x + b.width > W - 4) dx = W - 4 - (b.x + b.width);
      if (dx) t.setAttribute('x', (+t.getAttribute('x') + dx).toFixed(1));
    });

    const svg = el.querySelector('svg'), tip = el.querySelector('.tip'), xh = el.querySelector('#cyxh');
    function hide() { tip.hidden = true; xh.style.display = 'none'; }
    svg.addEventListener('pointerleave', hide);
    svg.addEventListener('pointermove', function (e) {
      const r = svg.getBoundingClientRect(), k = W / r.width;
      const day = Math.round(((e.clientX - r.left) * k - pl) / ((W - pl - pr) / END));
      if (day < 0 || day > END) return hide();
      xh.setAttribute('x1', x(day)); xh.setAttribute('x2', x(day)); xh.style.display = '';
      const has = day < cur.v.length, rv = ref.v[day];
      tip.innerHTML = '<b>' + day + '일차 · ' + ymd(d.cal[day]) + '</b>' +
        '<span style="color:#aab8ff">2018 ' + md(ref.dates[day]) + ' · ' + f1(rv) + '</span>' +
        (has ? '<span style="color:#ffb085">2026 · ' + f1(cur.v[day]) + '</span><span>2018 대비 ' + sg(cur.v[day] - rv, 1) + '%p</span>' : '<span>2026 · 아직 오지 않은 날</span>');
      tip.hidden = false;
      const px = x(day) / k;
      tip.style.left = (px > r.width / 2 ? px - tip.offsetWidth - 12 : px + 12) + 'px';
    });
  };

  /* ---------- 화면 조각 ---------- */
  function kpis(d) {
    const cur = d.cur, ref = d.ref, day = cur.v.length - 1, v = cur.v[day], rv = ref.v[day];
    const lo = cur.v.reduce(function (a, b, i) { return b < cur.v[a] ? i : a; }, 0);
    const gap = v - rv, left = d.endDay - day;
    const tile = function (label, value, sub) { return '<div class="cy-kpi"><small>' + label + '</small><strong>' + value + '</strong><span>' + sub + '</span></div>'; };
    return '<div class="cy-kpis">' +
      tile('현재 (고점=100)', f1(v), 'QQQ ' + usd(cur.close[day]) + ' · ' + md(cur.dates[day])) +
      tile('고점 대비', '<b class="' + cls(v - 100) + '">' + sg(v - 100, 1) + '%</b>', md(cur.peak) + ' 고점 ' + usd(cur.peakClose)) +
      tile('2018년 같은 시점', f1(rv), '<b class="' + cls(gap) + '">' + sg(gap, 1) + '%p</b> (' + ymd(ref.dates[day]) + ')') +
      tile('지금까지 저점', f1(cur.v[lo]), md(cur.dates[lo]) + ' · 고점 대비 ' + sg(cur.v[lo] - 100, 1) + '%') +
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
  function bodyHtml(d, ctx) {
    const cur = d.cur, last = cur.dates[cur.dates.length - 1];
    const legend = '<div class="ma-legend">' +
      '<span class="ma-chip"><i style="background:' + C_REF + '"></i>2018~19 (' + md(d.ref.peak) + ' 고점=100, ' + md(d.ref.start) + '부터)</span>' +
      '<span class="ma-chip"><i style="background:' + C_CUR + '"></i>2026 (' + md(cur.peak) + ' 고점=100)</span>' +
      '<span class="ma-chip"><i class="cy-dash"></i>FOMC</span></div>';
    return ctx.pageHead('QQQ 사이클 추적 · 2018년 하반기 비교', ymd(last) + ' 종가 기준 · ' + d.generatedAt.slice(5, 16).replace('T', ' ') + ' 수집 · yfinance') +
      kpis(d) +
      '<section class="card"><div class="card-head"><h2>고점 이후 경로 비교</h2></div>' + legend + '<div class="cycle" id="cycleChart"></div>' +
      '<p class="note">QQQ 종가를 고점=100으로 지수화했습니다. 가로축은 고점 이후 거래일 수(위)와 2026~27년 대응 날짜(아래)이고, 2018년 선은 ' + md(d.ref.start) +
      '(2026 고점일과 같은 0일차)부터 겹쳤습니다. 2026년 선은 ' + ymd(d.endDate) + '(' + d.endDay + '일차)까지 수집 때마다 이어 그려집니다.</p></section>' +
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
          const draw = function () { const el = ctx.view.querySelector('#cycleChart'); if (el) MR.cycleChart(el, d); };
          draw(); ctx.setRedraw(draw);
          requestAnimationFrame(draw); // 폰트·레이아웃 확정 후 한 번 더
        }).catch(function () {
          if (ctx.route().name === 'cycle') ctx.view.innerHTML = head + '<section class="card"><p class="empty">사이클 데이터를 불러오지 못했습니다. 다음 갱신 후 다시 확인해 주세요.</p></section>';
        });
      } };
    },
  };
})();

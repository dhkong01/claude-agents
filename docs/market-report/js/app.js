/* 라우터 + 화면 렌더링 (해시 라우팅: #/ , #/stock/:code , #/report , #/ranking) */
(function () {
  const MR = window.MR;
  const fmt = MR.fmt;
  const $ = function (s, r) { return (r || document).querySelector(s); };
  const $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  const cls = function (n) { return n > 0 ? 'up' : n < 0 ? 'down' : 'flat'; };
  const arrow = function (n) { return n > 0 ? '▲' : n < 0 ? '▼' : ''; };
  const sgn = function (n) { return (n > 0 ? '+' : n < 0 ? '-' : '') + fmt(Math.abs(n)); };
  const pctTxt = function (p) { return '<span class="' + cls(p) + '"><i class="ar">' + arrow(p) + '</i> ' + (p > 0 ? '+' : '') + p.toFixed(2) + '%</span>'; };
  const WATCH_KEY = 'mr.watch';
  const RANGES = { '1m': { n: 22, label: '1개월 전', text: '1개월' }, '3m': { n: 66, label: '3개월 전', text: '3개월' }, '6m': { n: 130, label: '6개월 전', text: '6개월' }, '1y': { n: 250, label: '1년 전', text: '1년' } };
  const MA_DEFS = [
    { n: 10, color: '#f59e0b' }, { n: 20, color: '#8b5cf6' }, { n: 60, color: '#14a3a3' }, { n: 120, color: '#6b7280' }, { n: 200, color: '#111827' },
  ];
  const FIN_ROWS = [
    { section: '손익' },
    { key: 'rev', label: '매출액', unit: '억원' }, { key: 'op', label: '영업이익', unit: '억원' }, { key: 'ni', label: '당기순이익', unit: '억원' },
    { section: '주당 지표' },
    { key: 'eps', label: '주당순이익 (EPS)', unit: '원' },
    { section: '수익성' },
    { key: 'roe', label: 'ROE', unit: '%', dec: 1 }, { key: 'opm', label: '영업이익률', unit: '%', dec: 1 },
    { section: '현금흐름' },
    { key: 'cfo', label: '영업활동 현금흐름', unit: '억원' }, { key: 'cfi', label: '투자활동 현금흐름', unit: '억원' }, { key: 'fcf', label: 'FCF (잉여현금흐름)', unit: '억원' },
  ];

  const esc = function (v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (ch) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]; });
  };
  const state = { country: 'KR', range: '6m', rank: 'volume', fin: 'annual', watch: [] };
  let redraw = null, globe = null;

  function loadWatch() {
    try {
      const v = JSON.parse(localStorage.getItem(WATCH_KEY));
      if (Array.isArray(v)) {
        const ok = v.filter(function (c) { return MR.stockByCode[c]; });
        // 저장된 종목이 모두 유니버스에서 사라졌다면(데이터 소스 교체 등) 기본 목록으로 되돌린다.
        if (ok.length || !v.length) return ok;
      }
    } catch (e) { /* 저장소 사용 불가 시 기본값 */ }
    return MR.defaultWatch.filter(function (c) { return MR.stockByCode[c]; });
  }
  function saveWatch() { try { localStorage.setItem(WATCH_KEY, JSON.stringify(state.watch)); } catch (e) { /* 무시 */ } }
  function watchStocks() { return state.watch.map(function (c) { return MR.stockByCode[c]; }); }

  // 종목명(한글·영문)·티커·코드로 검색. 정확히 일치 > 앞부분 일치 > 부분 일치 순
  function findStock(q) {
    q = (q || '').trim().toLowerCase().replace(/\s+/g, '');
    if (!q) return [];
    const hits = [];
    MR.stocks.forEach(function (s, i) {
      const name = s.name.toLowerCase().replace(/\s+/g, ''), sym = (s.sym || s.code).toLowerCase(), code = s.code.toLowerCase();
      let sc = -1;
      if (sym === q || code === q || name === q) sc = 0;
      else if (name.indexOf(q) === 0 || sym.indexOf(q) === 0 || code.indexOf(q) === 0) sc = 1;
      else if ((s.key || name + code).indexOf(q) >= 0) sc = 2;
      if (sc >= 0) hits.push([sc, i, s]);
    });
    hits.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
    return hits.map(function (h) { return h[2]; });
  }
  // 미국 주식은 소수점 2자리(USD), 한국 주식은 정수(원)
  const px = function (s, v) {
    return s && s.cur === 'USD' ? Number(v).toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : fmt(Math.round(v));
  };
  const flowTd = function (v) { return v == null ? '<td class="num flat">-</td>' : '<td class="num ' + cls(v) + '">' + sgn(v) + '</td>'; };
  // 관심종목 일부의 상세(이슈)를 미리 받아 둔다. 끝나면 done() 호출
  function preloadWatch(n, done) {
    const list = watchStocks().slice(0, n).filter(function (s) { return s && !s.loaded; });
    if (!list.length) return;
    Promise.all(list.map(function (s) { return s.load().catch(function () { return null; }); })).then(done);
  }
  let toastTimer = null;
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg; t.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.classList.remove('show'); }, 2200);
  }

  /* ---------- 공통 조각 ---------- */
  function pageHead(title, extra) {
    return '<div class="page-head"><h1>' + title + '</h1><span class="meta">' + (extra || dataMeta()) + '</span></div>';
  }
  function flowBars(flows) {
    const max = Math.max.apply(null, flows.map(function (f) { return Math.abs(f.val); })) * 1.6;
    return flows.map(function (f) {
      return '<div class="bar-row"><div class="bar-top"><span>' + f.label + '</span><b class="' + cls(f.val) + '">' + sgn(f.val) + '</b></div>' +
        '<div class="bar-track"><i class="' + (f.val >= 0 ? 'bg-up' : 'bg-down') + '" style="width:' + (Math.abs(f.val) / max * 100).toFixed(1) + '%"></i></div></div>';
    }).join('');
  }
  function stockName(s) { return '<a class="sname" href="#/stock/' + esc(s.code) + '"><b>' + esc(s.name) + '</b><small>' + esc(s.sym || s.code) + '</small></a>'; }
  function extLink(url, text) {
    return /^https:\/\/n\.news\.naver\.com\//.test(url || '') ? '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(text) + '</a>' : esc(text);
  }

  /* ---------- 시황 홈 ---------- */
  let BADGE = '<em class="badge">샘플</em>'; // 실데이터 로드에 성공하면 start()에서 비운다
  const badge = function (live) { return live ? '' : BADGE; };
  function dataMeta() {
    if (MR.reportLive) return MR.asOf + ' ' + MR.sessionWord + ' 기준 · ' + MR.generatedAt + ' 수집 · 네이버 증권·yfinance';
    if (MR.live) return MR.asOf + ' 기준 · 지수만 실데이터' + (MR.ageDays >= 2 ? ' (' + MR.ageDays + '일 전)' : '') + ' · 나머지는 샘플';
    return MR.asOf + ' 기준 · 샘플 데이터';
  }
  function marketHtml(c) {
    if (!c.indices.length && !c.tiles.length) return '<div class="mk-head"><h2>' + c.name + '</h2></div><p class="empty">이 시장의 데이터를 가져오지 못했습니다.</p>';
    const idx = c.indices.map(function (i) {
      const right = i.spark
        ? MR.sparkline(i.spark, i.pct >= 0)
        : '<span class="chg ' + cls(i.change) + '">' + sgn(+i.change.toFixed(2)) + '</span>';
      return '<div class="idx"><div><small>' + esc(i.name) + badge(i.live) + '</small><strong>' + i.value.toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '</strong></div>' +
        '<div class="idx-r">' + pctTxt(i.pct) + right + '</div></div>';
    }).join('');
    const tiles = c.tiles.map(function (t) {
      const d = t.dir;
      return '<div class="tile"><small>' + t.label + badge(t.live) + '</small><strong>' + t.value + '</strong>' +
        (t.delta ? '<span class="' + (d > 0 ? 'up' : 'down') + '"><i class="ar">' + (d > 0 ? '▲' : '▼') + '</i> ' + t.delta + '</span>' : '') +
        (t.sub ? '<em>' + t.sub + '</em>' : '') + '</div>';
    }).join('');
    return '<div class="mk-head"><h2>' + c.name + '</h2><span>주요 지수 · 빨강 상승 / 파랑 하락</span></div>' + idx + '<div class="tiles">' + tiles + '</div>';
  }
  function breadthCard() {
    const list = MR.breadthKR;
    if (!list || !list.length) return '';
    const rows = list.map(function (b) {
      const total = b.up + b.flat + b.down, pc = function (n) { return (n / total * 100).toFixed(1) + '%'; };
      return '<div class="breadth-row"><div class="bar-top"><span>' + b.name + '</span><span>상승 비율 <b>' + pc(b.up) + '</b> · 전체 ' + fmt(total) + '종목</span></div>' +
        '<div class="breadth" role="img" aria-label="' + b.name + ' 상승 ' + b.up + ', 하락 ' + b.down + ', 보합 ' + b.flat + '"><i class="bg-up" style="width:' + pc(b.up) + '"></i><i class="bg-flat" style="width:' + pc(b.flat) + '"></i><i class="bg-down" style="width:' + pc(b.down) + '"></i></div>' +
        '<div class="breadth-l"><span class="up">상승 <b>' + fmt(b.up) + '</b></span><span>보합 <b>' + fmt(b.flat) + '</b></span><span class="down">하락 <b>' + fmt(b.down) + '</b></span></div></div>';
    }).join('');
    return '<section class="card"><h2>시장 체감도</h2><p class="sub">등락 종목 수 · 상·하한가 포함</p>' + rows + '</section>';
  }
  function macroCard() {
    const rows = [];
    (MR.macroLive || []).forEach(function (m) { rows.push([m.label, m.value + ' <span class="' + cls(m.pct) + '">' + (m.pct > 0 ? '+' : '') + m.pct.toFixed(2) + '%</span>']); });
    (MR.pulseRows || []).forEach(function (r) { rows.push(r); });
    if (!rows.length) return '';
    return '<section class="card"><h2>시장 환경</h2><dl class="metrics">' + rows.map(function (r) {
      return '<div><dt>' + r[0] + '</dt><dd>' + r[1] + '</dd></div>';
    }).join('') + '</dl></section>';
  }
  function watchTableHtml() {
    const rows = watchStocks().map(function (s) {
      const ft = s.flowToday;
      return '<tr data-href="#/stock/' + esc(s.code) + '"><td>' + stockName(s) + '</td><td class="num"><b>' + px(s, s.price) + '</b></td><td class="num">' + pctTxt(s.pct) + '</td>' +
        flowTd(ft && ft.foreign) + flowTd(ft && ft.inst) +
        '<td class="rm"><button type="button" data-remove="' + esc(s.code) + '" aria-label="' + esc(s.name) + ' 관심종목 삭제" title="삭제">×</button></td></tr>';
    }).join('');
    if (!rows) return '<p class="empty">관심종목이 없습니다. 위 입력창에서 종목명이나 코드를 추가해 보세요.</p>';
    return '<table class="tbl"><thead><tr><th>종목</th><th class="num">현재가</th><th class="num">등락률</th><th class="num">외국인 순매수</th><th class="num">기관 순매수</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>';
  }
  function headIssue(s) {
    const n = s.issues.filter(function (i) { return i.tag === '뉴스'; })[0];
    return n || s.issues[0] || null;
  }
  function issuesHtml() {
    const items = watchStocks().slice(0, 4).map(function (s) {
      const is = headIssue(s);
      if (!is) return s.loaded ? '' : '<li><span class="tag-name">' + esc(s.name) + '</span><small>이슈 불러오는 중…</small></li>';
      return '<li><span class="tag-name">' + esc(s.name) + '</span>' + extLink(is.url, is.text) + '<small>' + esc(is.meta) + '</small></li>';
    }).join('');
    return items ? '<ul class="issue-list">' + items + '</ul>' : '<p class="empty">관심종목을 추가하면 주요 이슈가 표시됩니다.</p>';
  }
  function viewHome() {
    const c = MR.countryById[state.country];
    const chips = MR.countries.map(function (x) {
      return '<button type="button" class="chip' + (x.id === c.id ? ' active' : '') + '" data-country="' + x.id + '">' + x.name + '</button>';
    }).join('');
    const flowSub = MR.reportLive ? '코스피 · 억원 · ' + MR.flowDate + ' ' + MR.sessionFor(MR.flowDate) : '코스피 · 억원';
    const html = pageHead('오늘의 시장') +
      '<section class="card globe-card"><div class="globe-col"><div class="globe" id="globe"></div>' +
      '<p class="hint">드래그로 지구본 회전 · 국가를 누르면 해당 시장으로 이동</p><div class="chips" id="chips">' + chips + '</div></div>' +
      '<div class="market-col" id="market">' + marketHtml(c) + '</div></section>' +
      '<div class="grid-main">' +
      '<section class="card"><div class="card-head"><h2>내 관심종목' + BADGE + '</h2><form class="add-form" id="addForm"><input id="addq" placeholder="종목명 또는 코드 입력" autocomplete="off" aria-label="관심종목 추가"><button type="submit" class="btn-dark">추가</button></form></div>' +
      '<div id="watchTable" class="tbl-wrap">' + watchTableHtml() + '</div><p class="note">수급 단위: 억원 · 최근 거래일 기준' + (MR.reportLive ? ' · 순매매 수량×종가 환산' : '') + '</p></section>' +
      '<section class="card"><h2>투자자별 순매수' + BADGE + '</h2><p class="sub">' + flowSub + '</p>' + (MR.kospiFlows.length ? flowBars(MR.kospiFlows) : '<p class="empty">수급 데이터를 가져오지 못했습니다.</p>') + '</section></div>' +
      (MR.live ? '<div class="grid-main">' + breadthCard() + macroCard() + '</div>' : '') +
      '<div class="grid-main">' +
      '<section class="card"><h2>관심종목 주요 이슈' + BADGE + '</h2><div id="issueBox">' + issuesHtml() + '</div></section>' +
      '<section class="card promo"><small>오늘의 일일 리포트</small><h2>' + MR.report.headline + '</h2><p>' + MR.report.promo + '</p><a class="btn-light" href="#/report">리포트 보기</a></section></div>';
    return { html: html, mount: function () {
      globe = MR.createGlobe($('#globe'), { countries: MR.countries, selected: c, onSelect: selectCountry });
      preloadWatch(4, function () { if (route().name === 'home') refreshWatch(); });
    } };
  }
  function selectCountry(id) {
    if (!MR.countryById[id]) return;
    state.country = id;
    const c = MR.countryById[id];
    $('#market').innerHTML = marketHtml(c);
    $$('#chips .chip').forEach(function (b) { b.classList.toggle('active', b.dataset.country === id); });
    if (globe) globe.select(c);
  }
  function addWatch(q) {
    const found = findStock(q);
    if (!q.trim()) return toast('종목명 또는 코드를 입력해 주세요.');
    if (!found.length) return toast('검색 결과가 없습니다(코스피·코스닥·나스닥·NYSE 시총 상위 종목 제공): ' + q.trim());
    const s = found[0];
    if (state.watch.indexOf(s.code) >= 0) return toast(s.name + '은(는) 이미 관심종목입니다.');
    state.watch.push(s.code); saveWatch();
    toast(s.name + ' 추가됨');
    return true;
  }
  function refreshWatch() {
    const t = $('#watchTable'); if (t) t.innerHTML = watchTableHtml();
    const i = $('#issueBox'); if (i) i.innerHTML = issuesHtml();
  }

  /* ---------- 종목 ---------- */
  function stockHeader(s) {
    const watched = state.watch.indexOf(s.code) >= 0;
    const sub = s.isUS ? esc(s.sym) + ' · ' + esc(s.market) + (s.eng ? ' · ' + esc(s.eng) : '') : esc(s.code) + ' · ' + esc(s.market);
    return '<section class="card stock-head"><div><h1>' + esc(s.name) + ' <small>' + sub + '</small></h1>' +
      '<div class="price"><strong class="' + cls(s.chg) + '">' + px(s, s.price) + '</strong>' + (s.isUS ? '<small class="cur">USD</small>' : '') + '<span class="' + cls(s.chg) + '"><i class="ar">' + arrow(s.chg) + '</i> ' + px(s, Math.abs(s.chg)) + ' (' + (s.pct > 0 ? '+' : '') + s.pct.toFixed(2) + '%)</span></div></div>' +
      '<div class="head-r"><span class="meta">' + (s.lastDate || MR.asOf) + (s.isUS ? ' 종가 (미국 현지 거래일)' : (s.live && MR.sessionFor(s.lastDate || MR.asOf) === '장중' ? ' 장중 현재가' : ' 종가 마감')) + (s.live ? ' · 네이버 증권' : ' · 샘플 데이터') + '</span><button type="button" class="btn-line" data-toggle-watch="' + s.code + '">' + (watched ? '★ 관심종목 해제' : '☆ 관심종목 추가') + '</button></div></section>';
  }
  function chartCard(s) {
    const ser = s.series(), last = ser.bars.length - 1;
    const tabs = Object.keys(RANGES).map(function (k) {
      return '<button type="button" class="' + (k === state.range ? 'active' : '') + '" data-range="' + k + '">' + RANGES[k].text + '</button>';
    }).join('');
    const legend = MA_DEFS.map(function (d) {
      const v = ser.ma[d.n][last];
      return '<span class="ma-chip"><i style="background:' + d.color + '"></i>' + d.n + '일 <b>' + (v == null ? '-' : px(s, v)) + '</b></span>';
    }).join('');
    return '<section class="card"><div class="card-head"><h2>차트</h2><div class="seg" id="rangeSeg">' + tabs + '</div></div>' +
      '<div class="ma-legend">' + legend + '</div><div class="candle" id="candle"></div>' +
      '<p class="legend-line"><b class="gold">골든</b> 골든크로스 · 20일선이 60일선을 상향 돌파 <b>데드</b> 데드크로스 · 20일선이 60일선을 하향 이탈</p></section>';
  }
  function drawCandle(s) {
    const ser = s.series(), r = RANGES[state.range], start = ser.bars.length - r.n;
    MR.candleChart($('#candle'), ser.bars.slice(start), MA_DEFS.map(function (d) {
      return { n: d.n, color: d.color, values: ser.ma[d.n].slice(start) };
    }), { leftLabel: r.label, rightLabel: (s.lastDate || MR.asOf).slice(5), dec: s.isUS ? 2 : 0 });
  }
  function flowCard(s) {
    if (!s.flow5) return '<section class="card"><h2>외국인 · 기관 수급</h2><p class="empty">미국 주식은 투자자별 수급 정보를 제공하지 않습니다.</p></section>';
    const dts = s.dates5(), f = s.flow5;
    const rows = dts.map(function (d, i) {
      return '<tr><td>' + d + '</td><td class="num ' + cls(f.f[i]) + '">' + sgn(f.f[i]) + '</td><td class="num ' + cls(f.i[i]) + '">' + sgn(f.i[i]) + '</td><td class="num ' + cls(f.p[i]) + '">' + sgn(f.p[i]) + '</td></tr>';
    }).reverse().join('');
    return '<section class="card"><div class="card-head"><h2>외국인 · 기관 수급</h2><span class="meta">최근 5거래일 · 순매수 · 억원' + (s.live ? ' (수량×종가 환산)' : '') + '</span></div>' +
      '<div class="flow-chart" id="flowChart"></div>' +
      '<p class="legend-line">진한색 = 외국인 · 연한색 = 기관 · 빨강 순매수 · 파랑 순매도</p>' +
      '<table class="tbl"><thead><tr><th>일자</th><th class="num">외국인</th><th class="num">기관</th><th class="num">개인</th></tr></thead><tbody>' + rows + '</tbody></table></section>';
  }
  function drawFlow(s) {
    if (!s.flow5) return;
    const dts = s.dates5(), f = s.flow5;
    MR.flowChart($('#flowChart'), dts.map(function (d, i) { return { d: d, f: f.f[i], i: f.i[i] }; }));
  }
  function finCard(s) {
    return '<section class="card"><div class="card-head"><h2>실적 · 재무</h2><div class="seg" id="finSeg">' +
      '<button type="button" data-fin="annual" class="' + (state.fin === 'annual' ? 'active' : '') + '">연간' + (s.live ? '' : ' (5년)') + '</button>' +
      '<button type="button" data-fin="quarter" class="' + (state.fin === 'quarter' ? 'active' : '') + '">분기' + (s.live ? '' : ' (5개 분기)') + '</button></div></div>' +
      '<p class="sub" id="finSub">영업이익 추이 · 억원</p><div class="fin-chart" id="finChart"></div><div class="tbl-wrap" id="finTable"></div>' +
      '<p class="note">' + (s.isUS ? '출처: 네이버 증권(월드: 매출·EBIT·순이익), yfinance(EPS·ROE·현금흐름) · 영업이익은 EBIT · ROE는 순이익÷평균 자기자본(분기는 4배 연환산) · 회계연도 기준 · 일부 종목·분기는 빈칸 · ' :
        s.live ? '출처: 네이버 증권(손익·지표), yfinance(연간 현금흐름, 시총 상위 종목) · E는 컨센서스 추정 · 현금흐름은 연간만 제공 · ' : '샘플 데이터 · ') +
      '음수(파랑)는 현금 유출 · FCF는 영업CF와 투자CF의 합으로 단순 계산</p></section>';
  }
  function drawFin(s) {
    const d = s.fin(state.fin);
    if (!d) { $('#finChart').innerHTML = ''; $('#finTable').innerHTML = '<p class="empty">재무 데이터를 가져오지 못했습니다.</p>'; return; }
    const unit = d.unit || '억원';
    $('#finSub').textContent = (s.isUS ? '영업이익(EBIT) 추이 · ' : '영업이익 추이 · ') + unit;
    const get = function (key, i) {
      if (key === 'fcf') return d.cfo[i] == null || d.cfi[i] == null ? null : d.cfo[i] + d.cfi[i];
      return d[key][i];
    };
    MR.barChart($('#finChart'), d.cols, d.op);
    let h = '<table class="tbl fin"><thead><tr><th>항목</th>' + d.cols.map(function (c) { return '<th class="num">' + c + '</th>'; }).join('') + '</tr></thead><tbody>';
    FIN_ROWS.forEach(function (r) {
      if (r.section) { h += '<tr class="sec"><td colspan="' + (d.cols.length + 1) + '">' + r.section + '</td></tr>'; return; }
      const label = s.isUS && r.key === 'op' ? '영업이익(EBIT)' : r.label;
      const u = r.unit === '억원' ? unit : (s.isUS && r.unit === '원' ? '달러' : r.unit);
      h += '<tr><td><b>' + label + '</b> <small>' + u + '</small></td>' + d.cols.map(function (c, i) {
        const v = get(r.key, i);
        if (v == null) return '<td class="num flat">-</td>';
        return '<td class="num ' + (v < 0 ? 'down' : '') + '"><b>' + (r.dec ? v.toFixed(r.dec) : fmt(v)) + '</b></td>';
      }).join('') + '</tr>';
    });
    $('#finTable').innerHTML = h + '</tbody></table>';
  }
  function metricsCard(s) {
    const dash = function (v) { return v == null || v === '' ? '-' : v; };
    const m = [['시가총액', dash(s.cap)], ['PER', dash(s.per)], ['PBR', dash(s.pbr)],
      ['52주 최고 / 최저', s.hi52 == null ? '-' : px(s, s.hi52) + ' / ' + px(s, s.lo52)], ['거래량', s.volume == null ? '-' : fmt(s.volume) + '주'],
      s.extra ? [s.extra[0], dash(s.extra[1])] : ['외국인 지분율', '-']];
    return '<section class="card"><h2>투자 지표</h2><dl class="metrics">' + m.map(function (r) {
      return '<div><dt>' + r[0] + '</dt><dd>' + (s.live ? '' : '<em class="sample">[샘플]</em> ') + esc(r[1]) + '</dd></div>';
    }).join('') + '</dl></section>';
  }
  function stockIssuesCard(s) {
    const items = s.issues.map(function (i) {
      return '<li><div class="ih"><span class="tag">' + esc(i.tag) + '</span><small>' + esc(i.meta) + '</small></div><p>' + extLink(i.url, i.text) + '</p></li>';
    }).join('');
    return '<section class="card"><h2>주요 이슈</h2>' + (items ? '<ul class="issue-list detail">' + items + '</ul>' : '<p class="empty">표시할 이슈가 없습니다.</p>') + '</section>';
  }
  function chipsRow(cur) {
    return '<div class="chips mine"><small>내 종목</small>' + watchStocks().map(function (s) {
      return '<a class="chip' + (s.code === cur ? ' active' : '') + '" href="#/stock/' + esc(s.code) + '">' + esc(s.name) + '</a>';
    }).join('') + '<button type="button" class="chip dashed" data-focus-search>+ 종목 추가</button></div>';
  }
  function stockBody(s) {
    const html = chipsRow(s.code) + stockHeader(s) +
      '<div class="grid-stock"><div class="col">' + chartCard(s) + flowCard(s) + finCard(s) + '</div><div class="col">' + metricsCard(s) + stockIssuesCard(s) + '</div></div>';
    return { html: html, mount: function () {
      const all = function () { drawCandle(s); drawFlow(s); drawFin(s); };
      drawFin(s); // 표가 칼럼 폭을 정하므로 먼저 그린 뒤 차트 폭을 잰다
      all(); redraw = all;
      requestAnimationFrame(all); // 폰트·레이아웃 확정 후 한 번 더
    } };
  }
  function viewStock(code) {
    const s = MR.stockByCode[code] || watchStocks()[0] || MR.stocks[0];
    if (code && code !== s.code) { location.replace('#/stock/' + encodeURIComponent(s.code)); }
    if (s.loaded) { const b = stockBody(s); return { html: b.html, mount: function () { view.dataset.code = s.code; b.mount(); } }; }
    // 상세(차트·재무·이슈)는 선택한 종목만 지연 로딩한다
    return { html: chipsRow(s.code) + stockHeader(s) + '<section class="card"><p class="empty">차트와 재무 정보를 불러오는 중…</p></section>', mount: function () {
      view.dataset.code = s.code;
      s.load().then(function () {
        if (route().name !== 'stock' || view.dataset.code !== s.code) return; // 그 사이 다른 화면으로 이동했으면 무시
        const b = stockBody(s);
        view.innerHTML = b.html;
        b.mount();
      }).catch(function () {
        if (view.dataset.code === s.code) view.innerHTML = chipsRow(s.code) + stockHeader(s) + '<section class="card"><p class="empty">상세 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.</p></section>';
      });
    } };
  }

  /* ---------- 일일 리포트 ---------- */
  function viewReport() {
    const R = MR.report;
    const sorted = MR.sectors.slice().sort(function (a, b) { return b.pct - a.pct; });
    const picks = sorted.length > 4 ? sorted.slice(0, 2).concat(sorted.slice(-2)) : sorted;
    const tiles = picks.map(function (x) {
      return '<div class="sector-tile ' + (x.pct >= 0 ? 'bg-up-l' : 'bg-down-l') + '"><span>' + esc(x.name) + '</span><b class="' + cls(x.pct) + '">' + (x.pct > 0 ? '+' : '') + x.pct.toFixed(1) + '%</b></div>';
    }).join('');
    const brief = watchStocks().slice(0, 3).map(function (s) {
      const is = headIssue(s);
      const line = is ? (s.live ? '<span class="tag">' + esc(is.tag) + '</span> ' + extLink(is.url, is.text) + ' <small>' + esc(is.meta) + '</small>' : esc(is.text)) : '표시할 이슈가 없습니다.';
      const ft = s.flowToday;
      return '<li><div class="bh"><b>' + esc(s.name) + '</b><span class="' + cls(s.chg) + '">' + px(s, s.price) + ' ' + pctTxt(s.pct) + '</span>' +
        (ft ? '<small>외국인 ' + sgn(ft.foreign) + ' · 기관 ' + sgn(ft.inst) + '</small>' : '<small>' + esc(s.market) + '</small>') + '</div>' +
        '<p>' + (is || s.loaded ? line : '이슈 불러오는 중…') + '</p></li>';
    }).join('');
    const closes = MR.closeIndices.map(function (i) {
      return '<li><span>' + esc(i.name) + badge(i.live) + '</span><div><b>' + i.value + '</b>' + pctTxt(i.pct) + '</div></li>';
    }).join('');
    let checks, checkTitle;
    if (MR.reportLive) {
      checkTitle = '내 종목 최근 공시';
      checks = watchStocks().slice(0, 5).map(function (s) {
        const d = s.issues.filter(function (i) { return i.tag === '공시'; })[0];
        return d ? '<li><time>' + esc(d.meta.split(' · ').pop().slice(0, 5)) + '</time><span>' + esc(s.name) + ' — ' + esc(d.text) + '</span></li>' : '';
      }).join('');
    } else {
      checkTitle = '내일 체크포인트' + BADGE;
      checks = R.checkpoints.map(function (c) { return '<li><time>' + c.t + '</time><span>' + c.text + '</span></li>'; }).join('');
    }
    return { html:
      '<section class="hero"><small>일일 시황 리포트 · ' + MR.asOfLabel + (R.live ? ' ' + MR.sessionWord : ' 샘플') + '</small><h1>' + esc(R.headline) + '</h1><p>' + esc(R.summary) + '</p></section>' +
      '<div class="grid-report"><div class="col">' +
      '<section class="card"><h2>1. 업종 흐름' + BADGE + '</h2>' + (tiles ? '<div class="sector-tiles">' + tiles + '</div>' : '<p class="empty">업종 데이터를 가져오지 못했습니다.</p>') + '<p class="note">' + esc(R.sectorNote) + '</p></section>' +
      '<section class="card"><h2>2. 투자자별 수급' + BADGE + '</h2>' + (MR.kospiFlows.length ? flowBars(MR.kospiFlows) : '<p class="empty">수급 데이터를 가져오지 못했습니다.</p>') + '<p class="note">코스피 · 순매수 · 억원' + (MR.reportLive ? ' · ' + MR.flowDate + ' ' + MR.sessionFor(MR.flowDate) : '') + '</p></section>' +
      '<section class="card"><h2>3. 내 종목 브리핑' + BADGE + '</h2>' + (brief ? '<ul class="brief">' + brief + '</ul>' : '<p class="empty">시황 홈에서 관심종목을 추가해 주세요.</p>') + '</section></div>' +
      '<div class="col"><section class="card"><h2>' + (MR.reportLive && MR.sessionWord === '장중' ? '장중 지수' : '마감 지수') + '</h2><ul class="closes">' + closes + '</ul></section>' +
      (MR.live ? breadthCard() + macroCard() : '') +
      '<section class="card"><h2>' + checkTitle + '</h2>' + (checks ? '<ul class="checks">' + checks + '</ul>' : '<p class="empty">최근 공시가 없습니다.</p>') + '</section></div></div>',
      mount: function () {
        // 관심종목의 이슈·공시는 상세 파일에 있어서, 받아 온 뒤 같은 화면을 다시 그린다(스크롤 유지)
        preloadWatch(5, function () {
          if (route().name !== 'report') return;
          view.innerHTML = viewReport().html;
        });
      } };
  }

  /* ---------- 랭킹 · 섹터 ---------- */
  function rankRows() {
    const key = state.rank;
    let list;
    if (MR.rankings) list = MR.rankings[key] || [];
    else {
      list = MR.ranking.slice();
      if (key === 'gain') list.sort(function (a, b) { return b.pct - a.pct; });
      if (key === 'loss') list.sort(function (a, b) { return a.pct - b.pct; });
    }
    if (!list.length) return '<tr><td colspan="7" class="empty">순위 데이터를 가져오지 못했습니다.</td></tr>';
    return list.map(function (r, i) {
      const s = r.code ? MR.stockByCode[r.code] : null;
      const name = s ? '<a href="#/stock/' + esc(s.code) + '"><b>' + esc(s.name) + '</b></a>' : '<b class="ph">' + esc(r.name) + '</b>';
      return '<tr' + (s ? ' data-href="#/stock/' + s.code + '"' : '') + '><td class="rk">' + (i + 1) + '</td><td>' + name + '</td><td class="num"><b>' + fmt(r.price) + '</b></td><td class="num">' + pctTxt(r.pct) + '</td>' +
        '<td class="num">' + fmt(r.vol) + '</td><td class="num ' + cls(r.f) + '">' + sgn(r.f) + '</td><td class="num ' + cls(r.i) + '">' + sgn(r.i) + '</td></tr>';
    }).join('');
  }
  function sectorBars() {
    const max = Math.max.apply(null, MR.sectors.map(function (s) { return Math.abs(s.pct); })) * 1.25;
    return MR.sectors.map(function (s) {
      const w = Math.abs(s.pct) / max * 50;
      return '<div class="sec-row"><div class="bar-top"><span>' + esc(s.name) + '</span><b class="' + cls(s.pct) + '">' + (s.pct > 0 ? '+' : '') + s.pct.toFixed(1) + '%</b></div>' +
        '<div class="div-track"><i class="' + (s.pct >= 0 ? 'bg-up' : 'bg-down') + '" style="width:' + w.toFixed(1) + '%;' + (s.pct >= 0 ? 'left:50%' : 'right:50%') + '"></i></div></div>';
    }).join('');
  }
  function viewRanking() {
    const tabs = [['volume', '거래상위'], ['gain', '상승률'], ['loss', '하락률']].map(function (t) {
      return '<button type="button" data-rank="' + t[0] + '" class="' + (state.rank === t[0] ? 'active' : '') + '">' + t[1] + '</button>';
    }).join('');
    return { html: pageHead('랭킹 · 섹터', MR.reportLive ? MR.asOf + ' ' + MR.sessionWord + ' 기준 · 코스피+코스닥 보통주 · 네이버 증권' : MR.asOf + ' 기준 · 샘플 데이터') + '<div class="grid-rank"><section class="card"><div class="seg" id="rankSeg">' + tabs + '</div>' +
      '<div class="tbl-wrap"><table class="tbl"><thead><tr><th class="rk">순위</th><th>종목</th><th class="num">현재가</th><th class="num">등락률</th><th class="num">거래량</th><th class="num">외국인</th><th class="num">기관</th></tr></thead><tbody id="rankBody">' + rankRows() + '</tbody></table></div>' +
      '<p class="note">' + (MR.reportLive ? '수급 단위: 억원(순매매 수량×종가 환산) · 거래상위는 거래량 기준 · ETF 제외' : '수급 단위: 억원 · 종목명 · 수치는 [샘플]이며 실제 연동 시 교체됩니다') + '</p></section>' +
      '<section class="card"><h2>업종별 등락</h2>' + (MR.sectors.length ? sectorBars() : '<p class="empty">업종 데이터를 가져오지 못했습니다.</p>') +
      (MR.reportLive ? '<p class="note">네이버 증권 업종 등락률 · 구성 종목 8개 이상 업종 중 상위·하위 4개</p>' : '') + '</section></div>' };
  }

  /* ---------- 라우터 ---------- */
  const view = $('#view');
  function route() {
    const parts = (location.hash.replace(/^#\/?/, '') || '').split('/');
    let arg = parts[1];
    try { arg = arg && decodeURIComponent(arg); } catch (e) { /* 잘못된 인코딩은 그대로 둔다 */ }
    return { name: parts[0] || 'home', arg: arg };
  }
  function render() {
    closeSuggest();
    if (globe) { globe.destroy(); globe = null; }
    redraw = null;
    const r = route();
    let v, title = '마켓리포트';
    if (r.name === 'stock') { v = viewStock(r.arg); title = '종목 · 마켓리포트'; }
    else if (r.name === 'report') { v = viewReport(); title = '일일 리포트 · 마켓리포트'; }
    else if (r.name === 'ranking') { v = viewRanking(); title = '랭킹 · 섹터 · 마켓리포트'; }
    else { r.name = 'home'; v = viewHome(); }
    view.innerHTML = v.html;
    document.title = title;
    $$('[data-route]').forEach(function (a) { a.classList.toggle('active', a.dataset.route === r.name); });
    if (v.mount) v.mount();
    window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', render);
  let rz = null;
  window.addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { if (redraw) redraw(); }, 120); });

  /* ---------- 이벤트 위임 ---------- */
  view.addEventListener('click', function (e) {
    const t = e.target;
    const btn = t.closest('button');
    if (btn) {
      if (btn.dataset.country) return selectCountry(btn.dataset.country);
      if (btn.dataset.remove) {
        state.watch = state.watch.filter(function (c) { return c !== btn.dataset.remove; }); saveWatch(); return refreshWatch();
      }
      if (btn.dataset.range) {
        state.range = btn.dataset.range;
        $$('#rangeSeg button').forEach(function (b) { b.classList.toggle('active', b.dataset.range === state.range); });
        return drawCandle(MR.stockByCode[view.dataset.code]);
      }
      if (btn.dataset.fin) {
        state.fin = btn.dataset.fin;
        $$('#finSeg button').forEach(function (b) { b.classList.toggle('active', b.dataset.fin === state.fin); });
        return drawFin(MR.stockByCode[view.dataset.code]);
      }
      if (btn.dataset.rank) {
        state.rank = btn.dataset.rank;
        $$('#rankSeg button').forEach(function (b) { b.classList.toggle('active', b.dataset.rank === state.rank); });
        $('#rankBody').innerHTML = rankRows(); return;
      }
      if (btn.dataset.toggleWatch) {
        const c = btn.dataset.toggleWatch, i = state.watch.indexOf(c);
        if (i >= 0) state.watch.splice(i, 1); else state.watch.push(c);
        saveWatch(); toast(MR.stockByCode[c].name + (i >= 0 ? ' 관심종목 해제' : ' 관심종목 추가'));
        return render();
      }
      if (btn.hasAttribute('data-focus-search')) { $('#q').focus(); return; }
    }
    const tr = t.closest('tr[data-href]');
    if (tr && !t.closest('a,button')) location.hash = tr.dataset.href;
  });
  view.addEventListener('submit', function (e) {
    if (e.target.id !== 'addForm') return;
    e.preventDefault();
    const input = $('#addq');
    if (addWatch(input.value)) { input.value = ''; refreshWatch(); }
  });

  /* ---------- 헤더 검색 ---------- */
  const q = $('#q'), sg = $('#suggest');
  function closeSuggest() { sg.hidden = true; sg.innerHTML = ''; }
  q.addEventListener('input', function () {
    const found = findStock(q.value).slice(0, 8);
    if (!q.value.trim()) return closeSuggest();
    sg.innerHTML = found.length ? found.map(function (s) {
      return '<li><a href="#/stock/' + encodeURIComponent(s.code) + '"><b>' + esc(s.name) + '</b><small>' + esc(s.sym || s.code) + ' · ' + esc(s.market) + '</small></a></li>';
    }).join('') : '<li class="none">검색 결과가 없습니다 (코스피·코스닥·나스닥·NYSE 시총 상위 종목)</li>';
    sg.hidden = false;
  });
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeSuggest(); q.blur(); }
    if (e.key === 'Enter') {
      const f = findStock(q.value);
      if (f.length) { location.hash = '#/stock/' + encodeURIComponent(f[0].code); q.value = ''; closeSuggest(); q.blur(); } else toast('검색 결과가 없습니다.');
    }
  });
  sg.addEventListener('click', function () { q.value = ''; closeSuggest(); });
  document.addEventListener('click', function (e) { if (!e.target.closest('.search')) closeSuggest(); });

  /* ---------- 앱 설치(PWA) ---------- */
  if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('sw.js').catch(function () { /* 미지원·차단 시 일반 웹으로 동작 */ });
    });
  }
  let installEvt = null;
  const installBtn = $('#installBtn');
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault(); installEvt = e; installBtn.hidden = false;
  });
  installBtn.addEventListener('click', function () {
    if (!installEvt) return;
    installEvt.prompt();
    installEvt.userChoice.finally(function () { installEvt = null; installBtn.hidden = true; });
  });
  window.addEventListener('appinstalled', function () { installBtn.hidden = true; toast('앱이 설치되었습니다.'); });

  MR.loadLive().then(function () {
    if (MR.reportLive) {
      BADGE = ''; // 모든 항목이 실데이터이므로 샘플 배지를 숨긴다
      const foot = $('#footNote');
      if (foot) foot.innerHTML = '데이터: 네이버 증권(한국 시세·수급·재무·뉴스·공시·순위·업종), yfinance(해외 지수·환율·현금흐름), <code>data/market_pulse.json</code>(시장 국면·공포탐욕). 수집: <code>tools/market_report/export_market_report.py</code>. 지연·오류가 있을 수 있으며 투자 판단의 근거가 아닙니다.';
    }
    state.watch = loadWatch();
    render();
  });
})();

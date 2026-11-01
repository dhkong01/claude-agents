/* 실데이터 로더
 *  1순위 data/market_report.json (tools/market_report/export_market_report.py 가 생성)
 *  시장 국면·공포탐욕은 data/market_pulse.json 에서 보조로 읽는다.
 *  둘 다 실패하면 data.js 의 샘플 데이터로 동작한다. */
(function () {
  const MR = (window.MR = window.MR || {});
  const REPORT_URL = '../data/market_report.json';
  const PULSE_URL = '../data/market_pulse.json';
  const INDEX_URL = '../data/mr/index.json';
  const STOCK_URL = '../data/mr/s/';
  const WEEK = ['일', '월', '화', '수', '목', '금', '토'];
  const f2 = function (n) { return Number(n).toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };
  const sp = function (p) { return (p > 0 ? '+' : '') + p.toFixed(2) + '%'; };
  const sg = function (n) { return (n > 0 ? '+' : n < 0 ? '-' : '') + Math.abs(Math.round(n)).toLocaleString('ko-KR'); };
  const ymd = function (n) { const s = String(n); return s.slice(0, 4) + '.' + s.slice(4, 6) + '.' + s.slice(6, 8); };
  const num = function (v) { return v == null || isNaN(v) ? null : Number(v); };

  function sma(closes, n) {
    const out = [];
    let sum = 0;
    for (let i = 0; i < closes.length; i++) {
      sum += closes[i];
      if (i >= n) sum -= closes[i - n];
      out.push(i >= n - 1 ? sum / n : null);
    }
    return out;
  }

  /* 색인 한 줄 [code,name,market,price,chg,pct,foreignToday,instToday,sym,eng,cur] -> 종목 객체.
   * 차트·재무·이슈 같은 상세는 load()를 부를 때 data/mr/s/<code>.json 에서 가져온다. */
  function makeStock(r) {
    const s = {
      code: r[0], name: r[1], market: r[2], price: r[3], chg: r[4], pct: r[5],
      sym: r[8] || r[0], eng: r[9] || '', cur: r[10] || 'KRW', live: true, loaded: false, issues: [], flow5: null,
      flowToday: r[6] == null ? null : { foreign: r[6], inst: r[7] },
    };
    s.isUS = s.cur !== 'KRW';
    s.key = [s.name, s.sym, s.eng, s.code].join(' ').toLowerCase().replace(/\s+/g, '');
    let pending = null, ser = null, d = null;
    s.load = function () {
      if (s.loaded) return Promise.resolve(s);
      if (!pending) {
        pending = fetch(STOCK_URL + encodeURIComponent(s.code) + '.json', { cache: 'no-cache' })
          .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
          .then(function (x) {
            d = x;
            Object.assign(s, { cap: x.cap, per: x.per, pbr: x.pbr, hi52: x.hi52, lo52: x.lo52, volume: x.volume, extra: x.extra || null, issues: x.issues || [] });
            if (x.flow) {
              s.flow5 = { f: x.flow.f, i: x.flow.i, p: x.flow.p };
              s.flowDates = x.flow.dates.map(function (n) { return ymd(n).slice(5); });
            }
            s.lastDate = x.bars.length ? ymd(x.bars[x.bars.length - 1][0]) : '';
            s.loaded = true;
            return s;
          })
          .catch(function (e) { pending = null; throw e; });
      }
      return pending;
    };
    s.dates5 = function () { return s.flowDates || []; };
    s.series = function () {
      if (!ser && d) {
        const bars = d.bars.map(function (b) { return { d: ymd(b[0]), o: b[1], h: b[2], l: b[3], c: b[4] }; });
        const closes = bars.map(function (b) { return b.c; });
        const ma = {};
        [10, 20, 60, 120, 200].forEach(function (n) { ma[n] = sma(closes, n); });
        ser = { bars: bars, ma: ma };
      }
      return ser;
    };
    s.fin = function (mode) { return (d && d.fin && (d.fin[mode] || d.fin.annual)) || null; };
    return s;
  }

  function applyReport(d, idx) {
    const dt = d.asOf.split('-').map(Number);
    const day = new Date(dt[0], dt[1] - 1, dt[2]);
    MR.reportLive = true;
    MR.live = true;
    MR.asOf = d.asOf.replace(/-/g, '.');
    MR.asOfLabel = MR.asOf + ' (' + WEEK[day.getDay()] + ')';
    MR.generatedAt = d.generatedAt ? d.generatedAt.slice(5, 16).replace('T', ' ').replace('-', '.') : '';
    MR.ageDays = 0;

    // 국가별 지수·타일
    Object.keys(d.countries).forEach(function (cid) {
      const c = MR.countryById[cid], src = d.countries[cid];
      if (!c) return;
      c.indices = src.indices.map(function (i) { return Object.assign({ live: true }, i); });
      c.tiles = src.tiles.map(function (t) { return Object.assign({ live: true }, t); });
    });

    // 종목 (색인 전체를 검색 대상으로 교체. 상세는 선택할 때 지연 로딩)
    MR.stocks = idx.stocks.map(makeStock);
    MR.stockByCode = {};
    MR.stocks.forEach(function (s) { MR.stockByCode[s.code] = s; });
    MR.defaultWatch = d.defaultWatch.length ? d.defaultWatch : MR.stocks.slice(0, 4).map(function (s) { return s.code; });

    // 수급·순위·업종
    const kf = d.kospiFlows;
    MR.kospiFlows = kf ? [{ label: '개인', val: kf['개인'] }, { label: '외국인', val: kf['외국인'] }, { label: '기관', val: kf['기관'] }] : [];
    MR.flowDate = kf ? ymd(kf.date) : MR.asOf;
    MR.rankings = d.ranking;
    MR.sectors = d.sectors;
    MR.macroLive = d.macro || [];

    // 시장 체감도 (코스피·코스닥 등락 종목수)
    MR.breadthKR = ['kospi', 'kosdaq'].map(function (k) {
      const b = d.breadth[k] || {};
      return { name: k === 'kospi' ? '코스피' : '코스닥', up: b.riseCount || 0, flat: b.steadyCount || 0, down: b.fallCount || 0, upper: b.upperCount || 0, lower: b.lowerCount || 0 };
    }).filter(function (b) { return b.up + b.down + b.flat > 0; });

    // 마감 지수 카드
    const C = d.countries, pick = function (cid, i) { return C[cid] && C[cid].indices[i]; };
    const list = [pick('KR', 0), pick('KR', 1), pick('US', 0), pick('US', 1), pick('US', 2), pick('JP', 0), pick('CN', 0), pick('CN', 1)].filter(Boolean);
    MR.closeIndices = list.map(function (i) { return { name: i.name, value: f2(i.value), pct: i.pct, live: true }; });
    const krw = (C.KR.tiles || []).filter(function (t) { return t.label === '원/달러'; })[0];
    if (krw) MR.closeIndices.push({ name: '원/달러', value: krw.value, pct: krw.dir * parseFloat(krw.delta || 0), live: true });

    buildReportText(d);
  }

  function buildReportText(d) {
    const R = MR.report, C = d.countries;
    const kp = C.KR.indices[0], kq = C.KR.indices[1];
    if (!kp) return;
    const both = kq && kp.pct > 0 && kq.pct > 0 ? '동반 강세' : kq && kp.pct < 0 && kq.pct < 0 ? '동반 약세' : '엇갈린 마감';
    R.headline = '코스피 ' + sp(kp.pct) + (kq ? ', 코스닥 ' + sp(kq.pct) : '') + ' — ' + both;
    const parts = [];
    parts.push('코스피는 ' + f2(kp.value) + '(' + sp(kp.pct) + ')' + (kq ? ', 코스닥은 ' + f2(kq.value) + '(' + sp(kq.pct) + ')' : '') + '로 마감했습니다.');
    const kf = d.kospiFlows;
    if (kf) {
      const t = function (k) { return k + ' ' + sg(kf[k]) + '억원'; };
      parts.push('코스피 투자자별 순매수는 ' + [t('외국인'), t('기관'), t('개인')].join(', ') + '입니다.');
    }
    const us = C.US && C.US.indices.length ? C.US.indices.map(function (i) { return i.name.replace('종합', '').replace('존스', '') + ' ' + sp(i.pct); }).join(', ') : '';
    if (us) parts.push('미국 증시는 ' + us + '를 기록했습니다.');
    const jp = C.JP && C.JP.indices[0];
    if (jp) parts.push('일본 ' + jp.name + '는 ' + sp(jp.pct) + '였습니다.');
    R.summary = parts.join(' ');
    const sec = d.sectors || [];
    if (sec.length >= 4) {
      const top = sec.slice(0, 2), bot = sec.slice(-2).reverse();
      const fm = function (a) { return a.map(function (x) { return x.name + '(' + sp(x.pct) + ')'; }).join(', '); };
      R.sectorNote = '강세 업종은 ' + fm(top) + ', 약세 업종은 ' + fm(bot) + '입니다. (네이버 증권 업종 등락률)';
    } else R.sectorNote = '';
    R.promo = '마감 지수, 투자자별 수급, 업종 흐름, 내 종목 브리핑을 한 장으로 정리했습니다.';
    R.live = true;
  }

  /* ---------- market_pulse.json (보조: 시장 국면·공포탐욕) / 단독 폴백 ---------- */
  const KO = {
    phase: { TRANSITIONAL: '전환기', EXPANSION: '확장', CONTRACTION: '수축', PEAK: '고점', TROUGH: '저점' },
    fg: { 'extreme fear': '극단적 공포', fear: '공포', neutral: '중립', greed: '탐욕', 'extreme greed': '극단적 탐욕' },
  };
  const ko = function (map, v) { return (v && map[String(v).toLowerCase()]) || map[v] || v || '-'; };
  function applyPulse(d) {
    const m = d.macro || {};
    const note = ' (' + String(d.date).slice(5).replace('-', '.') + ' 기준)';
    MR.pulseRows = [];
    if (m.phase) MR.pulseRows.push(['시장 국면' + note, ko(KO.phase, m.phase)]);
    if (m.fear_greed != null) MR.pulseRows.push(['공포·탐욕 지수' + note, Math.round(m.fear_greed) + ' · ' + ko(KO.fg, m.fear_greed_rating)]);
    if (MR.reportLive) return;

    // 폴백: market_report.json 이 없을 때 pulse 의 지수만이라도 반영
    const dt = d.date.split('-').map(Number), day = new Date(dt[0], dt[1] - 1, dt[2]);
    MR.live = true;
    MR.asOf = d.date.replace(/-/g, '.');
    MR.asOfLabel = MR.asOf + ' (' + WEEK[day.getDay()] + ')';
    MR.seriesEnd = [dt[0], dt[1] - 1, dt[2]];
    MR.ageDays = Math.max(0, Math.floor((Date.now() - day.getTime()) / 864e5));
    const MAP = { KR: [['코스피', 'kospi'], ['코스닥', 'kosdaq']], US: [['S&P500', 'sp500'], ['나스닥종합', 'nasdaq'], ['다우존스', 'dow']], JP: [['니케이225', 'nikkei']], CN: [['상해종합', 'shanghai'], ['선전성분', 'shenzhen']] };
    Object.keys(MAP).forEach(function (cid) {
      const c = MR.countryById[cid];
      MAP[cid].forEach(function (mm) {
        const src = d.indices[mm[1]], idx = c.indices.filter(function (i) { return i.name === mm[0]; })[0];
        if (src && idx) Object.assign(idx, { value: src.price, pct: src.change_pct, change: src.change, live: true, spark: null });
      });
    });
  }

  function fetchJson(url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }

  MR.loadLive = function () {
    const rep = Promise.all([fetchJson(REPORT_URL), fetchJson(INDEX_URL)]).then(function (r) {
      const d = r[0], idx = r[1];
      if (!d || !d.asOf || !d.countries || !idx || !Array.isArray(idx.stocks) || !idx.stocks.length) throw new Error('형식 오류');
      applyReport(d, idx);
    }).catch(function (e) { MR.reportLive = false; MR.liveError = String((e && e.message) || e); });
    const pul = fetchJson(PULSE_URL).catch(function () { return null; });
    return Promise.all([rep, pul]).then(function (r) {
      if (r[1] && r[1].date && r[1].indices) applyPulse(r[1]);
      if (!MR.live) MR.live = false;
    });
  };
})();

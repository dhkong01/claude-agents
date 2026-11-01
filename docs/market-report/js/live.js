/* docs/data/market_pulse.json 실데이터를 샘플 데이터 위에 덮어쓴다. 실패 시 샘플 그대로 동작. */
(function () {
  const MR = (window.MR = window.MR || {});
  const SRC = '../data/market_pulse.json';
  // 나라 → [화면 지수명, JSON 키]
  const INDEX_MAP = {
    KR: [['코스피', 'kospi'], ['코스닥', 'kosdaq']],
    US: [['S&P500', 'sp500'], ['나스닥종합', 'nasdaq'], ['다우존스', 'dow']],
    JP: [['니케이225', 'nikkei']],
    CN: [['상해종합', 'shanghai'], ['선전성분', 'shenzhen']],
  };
  const CLOSE_ORDER = [['코스피', 'kospi'], ['코스닥', 'kosdaq'], ['S&P500', 'sp500'], ['나스닥종합', 'nasdaq'], ['다우존스', 'dow'], ['니케이225', 'nikkei'], ['상해종합', 'shanghai'], ['선전성분', 'shenzhen']];
  const KO = {
    phase: { TRANSITIONAL: '전환기', EXPANSION: '확장', CONTRACTION: '수축', PEAK: '고점', TROUGH: '저점' },
    trend: { SIDEWAYS: '횡보', UP: '상승', DOWN: '하락', UPTREND: '상승', DOWNTREND: '하락' },
    vol: { LOW: '낮음', NORMAL: '보통', HIGH: '높음' },
    rate: { LOW: '저금리', NORMAL: '보통', HIGH: '고금리' },
    dollar: { FLAT: '보합', UP: '강세', DOWN: '약세', STRONG: '강세', WEAK: '약세' },
    fg: { 'extreme fear': '극단적 공포', fear: '공포', neutral: '중립', greed: '탐욕', 'extreme greed': '극단적 탐욕' },
  };
  const ko = function (map, v) { return (v && map[String(v).toLowerCase()]) || map[v] || v || '-'; };
  const WEEK = ['일', '월', '화', '수', '목', '금', '토'];
  const f2 = function (n) { return Number(n).toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };
  const sp = function (p) { return (p > 0 ? '+' : '') + p.toFixed(2) + '%'; };

  function apply(d) {
    const dt = d.date.split('-').map(Number);
    const day = new Date(dt[0], dt[1] - 1, dt[2]);
    MR.asOf = d.date.replace(/-/g, '.');
    MR.asOfLabel = MR.asOf + ' (' + WEEK[day.getDay()] + ')';
    MR.seriesEnd = [dt[0], dt[1] - 1, dt[2]];
    MR.ageDays = Math.max(0, Math.floor((Date.now() - day.getTime()) / 864e5));

    // 국가별 지수
    Object.keys(INDEX_MAP).forEach(function (cid) {
      const c = MR.countryById[cid];
      INDEX_MAP[cid].forEach(function (m) {
        const src = d.indices[m[1]], idx = c.indices.filter(function (i) { return i.name === m[0]; })[0];
        if (!src) return;
        const row = { name: m[0], value: src.price, pct: src.change_pct, change: src.change, live: true };
        if (idx) Object.assign(idx, row, { spark: null }); else c.indices.unshift(Object.assign(row, { spark: null }));
      });
    });
    // 미국 10년물 금리
    if (d.macro && d.macro.yield10y != null) {
      const t = MR.countryById.US.tiles[0];
      t.value = f2(d.macro.yield10y) + '%'; t.delta = ''; t.dir = 0; t.live = true;
    }

    // 마감 지수 목록
    MR.closeIndices = CLOSE_ORDER.filter(function (m) { return d.indices[m[1]]; }).map(function (m) {
      const s = d.indices[m[1]];
      return { name: m[0], value: f2(s.price), pct: s.change_pct, change: s.change, live: true };
    });

    // 시장 체감도·매크로
    MR.breadth = d.breadth || null;
    const m = d.macro || null;
    MR.macro = m && [
      ['시장 국면', ko(KO.phase, m.phase)], ['시장 추세', ko(KO.trend, m.market_trend)],
      ['VIX', f2(m.vix) + ' · ' + ko(KO.vol, m.volatility)],
      ['공포·탐욕 지수', Math.round(m.fear_greed) + ' · ' + ko(KO.fg, m.fear_greed_rating)],
      ['미국채 2Y / 10Y / 30Y', f2(m.yield2y) + ' / ' + f2(m.yield10y) + ' / ' + f2(m.yield30y) + '%'],
      ['금리 환경', ko(KO.rate, m.rate_env)], ['달러 추세', ko(KO.dollar, m.dollar_trend)],
    ];

    // 시황 문구 (실데이터로 생성)
    const kp = d.indices.kospi, kq = d.indices.kosdaq;
    if (kp && kq) {
      const both = kp.change_pct > 0 && kq.change_pct > 0 ? '동반 강세' : kp.change_pct < 0 && kq.change_pct < 0 ? '동반 약세' : '엇갈린 마감';
      const R = MR.report;
      R.headline = '코스피 ' + sp(kp.change_pct) + ', 코스닥 ' + sp(kq.change_pct) + ' — ' + both;
      const us = ['sp500', 'nasdaq', 'dow'].filter(function (k) { return d.indices[k]; }).map(function (k) {
        return { sp500: 'S&P500', nasdaq: '나스닥', dow: '다우' }[k] + ' ' + sp(d.indices[k].change_pct);
      }).join(', ');
      R.summary = '코스피는 ' + f2(kp.price) + '(' + sp(kp.change_pct) + '), 코스닥은 ' + f2(kq.price) + '(' + sp(kq.change_pct) + ')로 마감했습니다.' +
        (us ? ' 미국 증시는 ' + us + '를 기록했고' : '') + (d.indices.nikkei ? (us ? ', ' : ' ') + '일본 니케이225는 ' + sp(d.indices.nikkei.change_pct) + '였습니다.' : '.') +
        (m ? ' 공포·탐욕 지수는 ' + Math.round(m.fear_greed) + '(' + ko(KO.fg, m.fear_greed_rating) + '), VIX는 ' + f2(m.vix) + '입니다.' : '');
      R.promo = '마감 지수, 시장 체감도, 매크로 지표를 한 장으로 정리했습니다.';
      R.live = true;
    }
    MR.live = true;
  }

  MR.loadLive = function () {
    return fetch(SRC, { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { if (!d || !d.date || !d.indices) throw new Error('형식 오류'); apply(d); })
      .catch(function (e) { MR.live = false; MR.liveError = String(e && e.message || e); });
  };
})();

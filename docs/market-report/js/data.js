/* 마켓리포트 샘플 데이터 — 실제 연동 시 이 파일의 값만 교체하면 됩니다. */
(function () {
  const MR = (window.MR = window.MR || {});
  MR.asOf = '2026.11.01';
  MR.asOfLabel = '2026.11.01 (일)';

  function hash(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function rng(seed) {
    let s = seed >>> 0;
    return function () {
      s = (s + 0x6d2b79f5) >>> 0;
      let t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  MR.hash = hash;

  /* ---------- 국가별 시장 ---------- */
  function spark(key, pct, n) {
    const r = rng(hash(key));
    const out = [];
    let v = 100;
    for (let i = 0; i < (n || 24); i++) { v += (pct >= 0 ? 0.35 : -0.35) + (r() - 0.5) * 2.2; out.push(v); }
    const rising = out[out.length - 1] >= out[0];
    return rising === (pct >= 0) ? out : out.map(function (x) { return 2 * out[0] - x; });
  }
  function country(id, num, name, lon, lat, idx, y10, fx) {
    return {
      id: id, num: num, name: name, lon: lon, lat: lat,
      indices: idx.map(function (a) { return { name: a[0], value: a[1], pct: a[2], spark: spark(id + a[0], a[2]) }; }),
      tiles: [
        { label: '10년물 국채금리', value: y10[0], delta: y10[1], dir: y10[2] },
        { label: fx[0], value: fx[1], delta: fx[2], dir: fx[3], sub: fx[4] },
      ],
    };
  }
  MR.countries = [
    country('KR', 410, '대한민국', 127.8, 36.5,
      [['코스피', 2683.42, 0.69], ['코스닥', 861.15, -0.5], ['코스피200', 358.9, 0.74]],
      ['3.05%', '1.2bp', 1], ['원/달러', '1,382.50', '0.22%', 1, '1달러당 원화 · 원화 약세']),
    country('US', 840, '미국', -98, 39,
      [['S&P500', 5842.1, 0.31], ['나스닥종합', 18620.55, 0.52], ['다우존스', 42310.7, -0.12]],
      ['4.35%', '2.1bp', 1], ['달러지수', '104.20', '0.11%', 1, '주요 6개 통화 대비']),
    country('JP', 392, '일본', 138, 36,
      [['니케이225', 39420.8, -0.64], ['토픽스', 2745.3, -0.41], ['JPX400', 24510.2, -0.35]],
      ['0.95%', '0.8bp', 1], ['엔/달러', '151.80', '0.15%', 1, '1달러당 엔 · 엔화 약세']),
    country('CN', 156, '중국', 104, 35,
      [['상해종합', 3258.4, 0.22], ['선전성분', 10120.6, 0.48], ['CSI300', 3790.5, 0.19]],
      ['2.15%', '0.5bp', -1], ['위안/달러', '7.24', '0.05%', 1, '1달러당 위안 · 위안화 약세']),
    country('TW', 158, '대만', 121, 23.7,
      [['가권지수', 21840.3, 0.87], ['타이엑스', 21210.5, 0.74], ['TPEx', 245.8, 0.33]],
      ['1.55%', '0.3bp', 1], ['대만달러/달러', '31.90', '0.10%', -1, '1달러당 대만달러 · 대만달러 강세']),
    country('IN', 356, '인도', 79, 22,
      [['센섹스', 80250.4, 0.41], ['니프티50', 24380.1, 0.38], ['니프티뱅크', 51920.7, -0.22]],
      ['7.05%', '1.0bp', -1], ['루피/달러', '83.40', '0.04%', 1, '1달러당 루피 · 루피화 약세']),
    country('GB', 826, '영국', -2, 54,
      [['FTSE100', 8180.6, -0.18], ['FTSE250', 20410.2, -0.09], ['FTSE350', 4510.3, -0.15]],
      ['4.15%', '1.5bp', 1], ['파운드/달러', '1.265', '0.12%', -1, '1파운드당 달러 · 파운드 약세']),
    country('DE', 276, '독일', 10.4, 51,
      [['DAX', 19120.4, 0.28], ['MDAX', 26140.9, 0.17], ['TecDAX', 3410.2, 0.45]],
      ['2.35%', '1.0bp', 1], ['유로/달러', '1.082', '0.08%', 1, '1유로당 달러 · 유로 강세']),
    country('FR', 250, '프랑스', 2.5, 46.5,
      [['CAC40', 7610.3, 0.12], ['SBF120', 5920.8, 0.09], ['CAC Mid60', 14210.4, -0.05]],
      ['3.05%', '1.4bp', 1], ['유로/달러', '1.082', '0.08%', 1, '1유로당 달러 · 유로 강세']),
    country('BR', 76, '브라질', -52, -10,
      [['보베스파', 128400.5, -0.74], ['IBX100', 54210.3, -0.62], ['SMLL', 2110.8, -0.38]],
      ['11.80%', '4.0bp', 1], ['헤알/달러', '5.48', '0.35%', 1, '1달러당 헤알 · 헤알화 약세']),
    country('AR', 32, '아르헨티나', -64, -34,
      [['메르발', 1820410.5, 1.42], ['메르발25', 1790320.2, 1.35], ['S&P Merval', 1750110.9, 1.18]],
      ['18.20%', '12.0bp', -1], ['페소/달러', '975.00', '0.80%', 1, '1달러당 페소 · 페소화 약세']),
    country('MX', 484, '멕시코', -102, 23,
      [['IPC', 52310.4, 0.21], ['FTSE BIVA', 1090.3, 0.18], ['S&P/BMV 60', 1040.6, 0.25]],
      ['9.60%', '2.0bp', -1], ['페소/달러', '17.20', '0.10%', -1, '1달러당 페소 · 페소화 강세']),
  ];
  MR.countryById = {};
  MR.countries.forEach(function (c) { MR.countryById[c.id] = c; });

  /* ---------- 종목 ---------- */
  const ISSUE_TAGS = ['공시', '실적', '뉴스', '리포트'];
  const ISSUE_TEXT = [
    '[이슈 요약 자리] 주요 공시 한 줄 요약',
    '[이슈 요약 자리] 실적·컨센서스 관련 핵심 내용',
    '[이슈 요약 자리] 업황·수급 관련 뉴스 요약',
    '[이슈 요약 자리] 증권사 목표주가·투자의견 변화',
  ];
  // code, name, market, price, change, cap, per, pbr, 52wHigh, 52wLow, volume, foreignShare
  const BASE = [
    ['005930', '삼성전자', '코스피', 71400, 800, '426조원', '14.2배', '1.3배', 88000, 53400, 14820000, '51.8%'],
    ['000660', 'SK하이닉스', '코스피', 192500, 3500, '140조원', '9.8배', '2.6배', 235000, 121000, 6310000, '54.2%'],
    ['042700', '한미반도체', '코스피', 118300, -2100, '11.3조원', '31.5배', '9.4배', 160000, 70000, 4975000, '27.9%'],
    ['196170', '알테오젠', '코스닥', 281000, -2500, '14.9조원', '82.1배', '21.7배', 350000, 180000, 3402000, '8.3%'],
    ['373220', 'LG에너지솔루션', '코스피', 385000, -3000, '90.1조원', '48.3배', '4.1배', 470000, 310000, 410000, '4.6%'],
    ['005380', '현대차', '코스피', 245000, 2500, '51.3조원', '5.4배', '0.6배', 298000, 190000, 780000, '38.2%'],
    ['035420', 'NAVER', '코스피', 212000, 1500, '34.8조원', '24.6배', '1.4배', 255000, 160000, 520000, '52.4%'],
    ['035720', '카카오', '코스피', 48200, -400, '21.4조원', '41.2배', '1.5배', 64000, 35000, 1980000, '24.9%'],
    ['068270', '셀트리온', '코스피', 185000, 2200, '40.1조원', '36.7배', '4.3배', 230000, 140000, 690000, '20.1%'],
    ['005490', 'POSCO홀딩스', '코스피', 372000, -4200, '31.5조원', '16.9배', '0.5배', 460000, 280000, 350000, '17.8%'],
    ['207940', '삼성바이오로직스', '코스피', 1020000, 8000, '72.6조원', '58.4배', '6.8배', 1180000, 780000, 85000, '12.3%'],
    ['086520', '에코프로', '코스닥', 71300, 900, '19.3조원', '63.0배', '5.9배', 98000, 52000, 1240000, '9.6%'],
  ];
  // 최근 5거래일 수급(억원): 외국인 / 기관 / 개인. 마지막 값이 11.01.
  const FLOWS = {
    '005930': { f: [1240, -410, 860, -95, 1240], i: [-320, 620, 150, -340, -320], p: [-920, -210, -1010, 435, -920] },
  };
  const LAST_FLOW = { '000660': [860, 410], '042700': [-95, 40], '196170': [-210, -130] };

  function tickOf(p) {
    return p < 2000 ? 1 : p < 5000 ? 5 : p < 20000 ? 10 : p < 50000 ? 50 : p < 200000 ? 100 : p < 500000 ? 500 : 1000;
  }
  function fmtDate(d) {
    return d.getFullYear() + '.' + String(d.getMonth() + 1).padStart(2, '0') + '.' + String(d.getDate()).padStart(2, '0');
  }
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

  function genSeries(s) {
    const N = 520;
    const r = rng(hash(s.code + 'px'));
    const raw = [100];
    for (let i = 1; i < N; i++) raw.push(raw[i - 1] * Math.exp((r() - 0.485) * 0.034));
    const k = s.price / raw[N - 1];
    const tick = tickOf(s.price);
    const q = function (v) { return Math.max(tick, Math.round(v / tick) * tick); };
    const closes = raw.map(function (v) { return q(v * k); });
    closes[N - 1] = s.price;
    closes[N - 2] = s.price - s.chg;
    const dates = [];
    const end = MR.seriesEnd || [2026, 10, 1];
    const d = new Date(end[0], end[1], end[2]);
    for (let i = N - 1; i >= 0; i--) {
      dates[i] = fmtDate(d);
      d.setDate(d.getDate() - 1);
      while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1);
    }
    const bars = closes.map(function (c, i) {
      const o = i === 0 ? c : q(closes[i - 1] * (1 + (r() - 0.5) * 0.01));
      const h = q(Math.max(o, c) * (1 + r() * 0.008));
      const l = q(Math.min(o, c) * (1 - r() * 0.008));
      return { d: dates[i], o: o, h: Math.max(h, o, c), l: Math.min(l, o, c), c: c };
    });
    const ma = {};
    [10, 20, 60, 120, 200].forEach(function (n) { ma[n] = sma(closes, n); });
    return { bars: bars, ma: ma };
  }

  /* ---------- 재무 ---------- */
  const SAMSUNG_FIN = {
    cols: ['2022', '2023', '2024', '2025', '2026E'],
    rev: [3022314, 2589355, 3008709, 3330000, 3650000],
    op: [433766, 65670, 328000, 450000, 620000],
    ni: [556541, 154871, 344000, 400000, 520000],
    eps: [8057, 2131, 4950, 5780, 7500],
    roe: [17.1, 4.1, 8.9, 9.8, 12.0],
    opm: [14.4, 2.5, 10.9, 13.5, 17.0],
    cfo: [621000, 440000, 590000, 640000, 720000],
    cfi: [-460000, -430000, -520000, -560000, -590000],
  };
  function genFin(s) {
    if (s.code === '005930') return SAMSUNG_FIN;
    const r = rng(hash(s.code + 'fin'));
    const k = 0.01 + r() * 0.25;
    const sc = function (arr) { return arr.map(function (v) { return Math.round(v * k * (0.8 + r() * 0.4)); }); };
    const cfo = sc(SAMSUNG_FIN.cfo);
    const e = 0.05 + r() * 0.4;
    return {
      cols: SAMSUNG_FIN.cols,
      rev: sc(SAMSUNG_FIN.rev), op: sc(SAMSUNG_FIN.op), ni: sc(SAMSUNG_FIN.ni),
      eps: SAMSUNG_FIN.eps.map(function (v) { return Math.round(v * e * (0.8 + r() * 0.4)); }),
      roe: SAMSUNG_FIN.roe.map(function (v) { return +(v * (0.6 + r() * 0.8)).toFixed(1); }),
      opm: SAMSUNG_FIN.opm.map(function (v) { return +(v * (0.6 + r() * 0.8)).toFixed(1); }),
      cfo: cfo,
      cfi: cfo.map(function (v) { return -Math.round(v * (0.7 + r() * 0.5)); }),
    };
  }
  function genQuarter(s, a) {
    const r = rng(hash(s.code + 'q'));
    const src = [3, 3, 3, 3, 4]; // 25.1Q~25.4Q는 2025, 26.1QE는 2026E 기준
    const pick = function (key) {
      return src.map(function (idx) { return Math.round(a[key][idx] / 4 * (0.8 + r() * 0.4)); });
    };
    const ratio = function (key) {
      return src.map(function (idx) { return +(a[key][idx] * (0.9 + r() * 0.2)).toFixed(1); });
    };
    return {
      cols: ['25.1Q', '25.2Q', '25.3Q', '25.4Q', '26.1QE'],
      rev: pick('rev'), op: pick('op'), ni: pick('ni'), eps: pick('eps'),
      roe: ratio('roe'), opm: ratio('opm'), cfo: pick('cfo'), cfi: pick('cfi'),
    };
  }

  MR.stocks = BASE.map(function (b) {
    const price = b[3], chg = b[4];
    const s = {
      code: b[0], name: b[1], market: b[2], price: price, chg: chg,
      pct: +(chg / (price - chg) * 100).toFixed(2),
      cap: b[5], per: b[6], pbr: b[7], hi52: b[8], lo52: b[9], volume: b[10], foreignShare: b[11],
      issues: ISSUE_TAGS.map(function (t, i) { return { tag: t, meta: '출처 · 시간', text: ISSUE_TEXT[i] }; }),
    };
    // 최근 5거래일 수급
    let fl = FLOWS[s.code];
    if (!fl) {
      const r = rng(hash(s.code + 'flow'));
      const last = LAST_FLOW[s.code] || [Math.round((r() - 0.5) * 600), Math.round((r() - 0.5) * 400)];
      const scale = Math.abs(last[0]) * 2 + 300;
      const f = [], i2 = [], p = [];
      for (let n = 0; n < 4; n++) { f.push(Math.round((r() - 0.5) * scale)); i2.push(Math.round((r() - 0.5) * scale * 0.8)); }
      f.push(last[0]); i2.push(last[1]);
      for (let n = 0; n < 5; n++) p.push(-(f[n] + i2[n]) + Math.round((r() - 0.5) * 80));
      fl = { f: f, i: i2, p: p };
    }
    s.flow5 = fl;
    s.flowToday = { foreign: fl.f[4], inst: fl.i[4], person: fl.p[4] };
    // 실데이터 종목과 같은 인터페이스(지연 로딩 API)를 맞춘다
    s.cur = 'KRW'; s.sym = s.code; s.eng = ''; s.loaded = true; s.isUS = false;
    s.extra = ['외국인 지분율', s.foreignShare];
    s.key = (s.name + s.code).toLowerCase().replace(/\s+/g, '');
    s.load = function () { return Promise.resolve(s); };
    let _series = null, _fin = null, _q = null;
    s.series = function () { return _series || (_series = genSeries(s)); };
    s.dates5 = function () { return s.series().bars.slice(-5).map(function (b) { return b.d.slice(5); }); };
    s.fin = function (mode) {
      _fin = _fin || genFin(s);
      if (mode === 'quarter') return _q || (_q = genQuarter(s, _fin));
      return _fin;
    };
    return s;
  });
  MR.stockByCode = {};
  MR.stocks.forEach(function (s) { MR.stockByCode[s.code] = s; });
  MR.defaultWatch = ['005930', '000660', '042700', '196170'];

  /* ---------- 시장 요약 / 수급 / 섹터 / 랭킹 ---------- */
  MR.kospiFlows = [
    { label: '개인', val: -2310 },
    { label: '외국인', val: 1840 },
    { label: '기관', val: 520 },
  ];
  MR.closeIndices = [
    { name: '코스피', value: '2,683.42', pct: 0.69 },
    { name: '코스닥', value: '861.15', pct: -0.5 },
    { name: '코스피200', value: '358.90', pct: 0.74 },
    { name: '원/달러', value: '1,382.50', pct: 0.22 },
  ];
  MR.sectors = [
    { name: '반도체', pct: 1.9 }, { name: '자동차', pct: 0.8 }, { name: '금융', pct: 0.4 },
    { name: '화학', pct: -0.2 }, { name: '2차전지', pct: -0.7 }, { name: '바이오', pct: -1.2 },
    { name: '건설', pct: 0.2 }, { name: 'IT서비스', pct: 0.6 },
  ];
  // code가 있으면 종목 상세로 연결
  MR.ranking = [
    { code: '005930', price: 71400, pct: 1.13, vol: 14820000, f: 1240, i: -320 },
    { code: '000660', price: 192500, pct: 1.85, vol: 6310000, f: 860, i: 410 },
    { code: '042700', price: 118300, pct: -1.74, vol: 4975000, f: -95, i: 40 },
    { code: '196170', price: 281000, pct: -0.88, vol: 3402000, f: -210, i: -130 },
    { name: '[종목E]', price: 45250, pct: 2.4, vol: 3118000, f: 150, i: 95 },
    { name: '[종목F]', price: 33800, pct: -0.3, vol: 2764000, f: -40, i: 22 },
    { name: '[종목G]', price: 92100, pct: 0.65, vol: 2215000, f: 75, i: -18 },
    { name: '[종목H]', price: 15670, pct: 3.1, vol: 1980000, f: 12, i: 31 },
  ];
  MR.report = {
    headline: '외국인 매수가 지수를 끌어올린 하루, 내일은 환율이 변수',
    summary: '[샘플 문안] 코스피는 외국인 순매수에 힘입어 상승 마감했고 코스닥은 차익 실현 매물에 약세였습니다. 이 영역에 장 마감 한 문단 요약이 들어갑니다.',
    sectorNote: '[샘플 문안] 업종별 강세·약세 배경을 두세 문장으로 설명하는 영역입니다.',
    checkpoints: [
      { t: '08:00', text: '[일정 자리] 주요 경제지표 발표' },
      { t: '09:00', text: '[일정 자리] 미국 증시 마감 영향 점검' },
      { t: '장중', text: '[일정 자리] 환율 · 외국인 수급 흐름' },
      { t: '장후', text: '[일정 자리] 내 종목 실적 · 공시 일정' },
    ],
    promo: '장 마감 요약, 업종 흐름, 수급, 내일 체크포인트를 한 장으로 정리했습니다.',
  };
})();

/* d3 정사영 지구본: 드래그 회전 + 국가 클릭 선택 */
(function () {
  const MR = (window.MR = window.MR || {});
  const WORLD_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json';
  let worldP = null;

  function loadWorld() {
    if (!worldP) {
      worldP = fetch(WORLD_URL).then(function (r) { return r.json(); }).then(function (t) {
        return window.topojson.feature(t, t.objects.countries).features;
      });
      worldP.catch(function () { worldP = null; });
    }
    return worldP;
  }

  MR.createGlobe = function (el, opts) {
    const noop = { select: function () {}, destroy: function () {} };
    if (!window.d3 || !window.topojson) {
      el.innerHTML = '<p class="globe-fail">지구본 라이브러리를 불러오지 못했습니다. 아래 국가 버튼으로 시장을 선택하세요.</p>';
      return noop;
    }
    const d3 = window.d3;
    const size = 360; // 내부 좌표계 고정. 실제 크기는 CSS(width:100%)로 스케일된다.
    const byNum = new Map(opts.countries.map(function (c) { return [c.num, c]; }));
    let sel = opts.selected;
    el.innerHTML = '';
    const svg = d3.select(el).append('svg').attr('viewBox', '0 0 ' + size + ' ' + size)
      .attr('class', 'globe-svg').attr('role', 'img').attr('aria-label', '드래그해서 회전하는 지구본');
    const proj = d3.geoOrthographic().scale(size / 2 - 3).translate([size / 2, size / 2]).clipAngle(90).rotate([-sel.lon, -sel.lat, 0]);
    const path = d3.geoPath(proj);
    svg.append('circle').attr('class', 'globe-sea').attr('cx', size / 2).attr('cy', size / 2).attr('r', size / 2 - 3);
    const grat = svg.append('path').datum(d3.geoGraticule10()).attr('class', 'globe-grat');
    const g = svg.append('g');
    const mark = svg.append('circle').attr('class', 'globe-mark').attr('r', 5);
    let paths = null, alive = true;

    function cls(d) {
      const c = byNum.get(+d.id);
      return 'land' + (c ? ' supported' : '') + (c && c.id === sel.id ? ' selected' : '');
    }
    function draw() {
      grat.attr('d', path);
      if (paths) paths.attr('d', path).attr('class', cls);
      const r = proj.rotate();
      if (d3.geoDistance([sel.lon, sel.lat], [-r[0], -r[1]]) < Math.PI / 2 - 0.05) {
        const p = proj([sel.lon, sel.lat]);
        mark.attr('cx', p[0]).attr('cy', p[1]).style('display', null);
      } else {
        mark.style('display', 'none');
      }
    }
    loadWorld().then(function (features) {
      if (!alive) return;
      paths = g.selectAll('path').data(features).join('path')
        .on('click', function (e, d) { const c = byNum.get(+d.id); if (c) opts.onSelect(c.id); });
      draw();
    }).catch(function () {
      el.insertAdjacentHTML('beforeend', '<p class="globe-fail">지도 데이터를 불러오지 못했습니다. 네트워크를 확인해 주세요.</p>');
    });
    svg.call(d3.drag().on('drag', function (e) {
      const r = proj.rotate();
      proj.rotate([r[0] + e.dx * 0.3, Math.max(-80, Math.min(80, r[1] - e.dy * 0.3)), 0]);
      draw();
    }));
    draw();

    return {
      select: function (c) {
        sel = c;
        const r0 = proj.rotate(), r1 = [-c.lon, -c.lat, 0];
        r1[0] = r0[0] + ((((r1[0] - r0[0]) + 540) % 360) - 180);
        const ip = d3.interpolate(r0, r1);
        d3.transition().duration(900).tween('rotate', function () {
          return function (t) { if (alive) { proj.rotate(ip(t)); draw(); } };
        });
      },
      destroy: function () { alive = false; },
    };
  };
})();

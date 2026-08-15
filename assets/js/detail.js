/* EV보조금 상세 페이지 hydration ─ 프리렌더 정적 HTML 위에 실시간 요소만 갱신
   - app.js 전역(EVData·statusBadge·closedInfo·fmt·esc·CATS·categoryBar·cmpBasket·myCategory·makerShort) 재사용.
     app.js는 수정 금지 계약 — 여기서는 읽기만 한다.
   - data-live 앵커가 없는 페이지에선 아무 것도 하지 않음. 데이터 로드 실패 시 정적 내용 그대로(무소음 강등). */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var safe = function (fn) { try { fn(); } catch (e) { /* 무소음 — 정적 유지 */ } };

  document.addEventListener('DOMContentLoaded', function () { safe(boot); });

  function boot() {
    var badge = $('[data-live="badge"]'), cats = $('[data-live="cats"]'),
        tbl = $('[data-live="fulltable"]'), exp = $('[data-live="expand"]'),
        cmp = $('[data-live="cmp"]'), sidoTbl = $('[data-live="sidotable"]');
    if (!badge && !cats && !tbl && !cmp && !sidoTbl) return;   // 앵커 없음 → 무동작
    if (!window.EVData) return;

    /* 비교 버튼(정적 표의 data-cmp) — 데이터 로드와 무관하게 즉시 동작 */
    document.addEventListener('click', function (e) {
      var b = e.target.closest && e.target.closest('[data-cmp]');
      if (b && window.cmpBasket) { e.preventDefault(); cmpBasket.toggle(+b.getAttribute('data-cmp')); }
    });
    if (cmp && window.cmpBasket) {
      var cmpId = +cmp.getAttribute('data-id');
      var syncCmp = function () { cmp.textContent = cmpBasket.get().indexOf(cmpId) >= 0 ? '✓ 비교함에 담김' : '🚗 비교함에 담기'; };
      cmp.addEventListener('click', function () { cmpBasket.toggle(cmpId); syncCmp(); });
      syncCmp();
    }

    EVData.all().then(function (res) {
      var cars = res[0], regions = res[1], statusFile = res[3];
      var updated = statusFile && statusFile.updated;
      var cd = (badge && badge.getAttribute('data-cd')) || (cats && cats.getAttribute('data-cd')) ||
               (tbl && tbl.getAttribute('data-cd'));
      var st = cd && statusFile && statusFile.data && statusFile.data[cd];

      /* ① 상태 뱃지 실시간화 (내 신청 유형 반영) */
      var paint = function () {
        if (!badge || !st) return;
        var b = statusBadge(st, updated, myCategory.get());
        badge.innerHTML = '<span class="badge ' + b.cls + '" style="font-size:14px;padding:6px 14px"><span class="dot"></span>' + esc(b.label) + '</span>';
      };
      safe(paint);

      /* ② 신청 유형 탭 + 소진 예측 — categoryBar가 forecast까지 함께 렌더(app.js 공용) */
      if (cats && st) safe(function () {
        categoryBar(cats, st, paint, { cd: cd, updated: updated });
      });

      /* ③ 표 전체 펼치기 — 정적 상위 N행과 같은 마크업으로 전체 렌더 */
      if (tbl && exp) safe(function () {
        var tbody = tbl.querySelector('tbody');
        var kind = tbl.getAttribute('data-kind');
        var rowsHtml = null;
        if (kind === 'region' && cd && regions[cd]) {
          var r = regions[cd], list = [];
          cars.forEach(function (c) {
            var v = r.v && r.v[c.id];
            if (c.disc || !v) return;
            list.push({ c: c, loc: v[0], tot: c.nat + v[0] });
          });
          list.sort(function (a, b) { return b.tot - a.tot || a.c.name.localeCompare(b.c.name, 'ko'); });
          rowsHtml = list.map(function (x) {
            return '<tr><td><a href="/car/' + x.c.id + '.html" style="color:inherit;font-weight:700">' + esc(x.c.name) + '</a>' +
              '<div class="small muted">' + esc(makerShort(x.c.maker)) + (x.c.range ? ' · ' + x.c.range + 'km' : '') + '</div></td>' +
              '<td class="num">' + fmt(x.c.nat) + '</td><td class="num">' + fmt(x.loc) + '</td>' +
              '<td class="num" style="font-weight:800;color:var(--money)">' + fmt(x.tot) + '</td>' +
              '<td><button class="btn-s btn btn-ghost" data-cmp="' + x.c.id + '">비교</button></td></tr>';
          });
        } else if (kind === 'car') {
          var id = +tbl.getAttribute('data-id'), car = cars[id];
          if (car) {
            var rl = [];
            Object.keys(regions).forEach(function (k) {
              if (k === '9999') return;
              var v = regions[k].v && regions[k].v[id];
              if (!v) return;
              rl.push({ k: k, r: regions[k], loc: v[0], tot: car.nat + v[0] });
            });
            rl.sort(function (a, b) { return b.tot - a.tot || a.r.name.localeCompare(b.r.name, 'ko'); });
            rowsHtml = rl.map(function (x) {
              return '<tr><td><a href="/region/' + x.k + '.html" style="color:inherit;font-weight:700">' + esc(x.r.name) + '</a>' +
                '<div class="small muted">' + esc(x.r.sido || '') + '</div></td>' +
                '<td class="num">' + fmt(x.loc) + '</td>' +
                '<td class="num" style="font-weight:800;color:var(--money)">' + fmt(x.tot) + '</td></tr>';
            });
          }
        }
        if (rowsHtml && rowsHtml.length > tbody.children.length) {
          exp.hidden = false;
          exp.addEventListener('click', function () {
            tbody.innerHTML = rowsHtml.join('');
            exp.hidden = true;
          });
        }
      });

      /* ④ 시도 허브 표 — 잔여·상태 셀만 최신 수치로 교체 */
      if (sidoTbl && statusFile && statusFile.data) safe(function () {
        var trs = sidoTbl.querySelectorAll('tr[data-cd]');
        for (var i = 0; i < trs.length; i++) {
          var row = trs[i], rcd = row.getAttribute('data-cd');
          var rst = statusFile.data[rcd];
          if (!rst) continue;
          var leftCell = row.querySelector('[data-cell="left"]');
          if (leftCell) leftCell.textContent = fmt(rst.left);
          var badgeCell = row.querySelector('[data-cell="badge"]');
          if (badgeCell) {
            var b = statusBadge(rst, updated);
            badgeCell.className = 'badge ' + b.cls;
            badgeCell.innerHTML = '<span class="dot"></span>' + esc(b.label);
          }
        }
      });
    }).catch(function () { /* 로드 실패 — 정적 내용 유지 */ });
  }
})();

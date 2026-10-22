/* ============================================================
   ECharts 公共主题
   - 统一取色、字号与 tooltip 样式，避免每个图表各写一套
   - 数据统一由 data-payload 传入（| tojson 转义），这里只做渲染
   ============================================================ */
(function () {
  'use strict';

  var TEXT = '#1f2430';
  var MUTED = '#6b7280';
  var GRID_LINE = '#eef0f5';

  function baseTooltip(extra) {
    return Object.assign({
      backgroundColor: 'rgba(31, 36, 48, .92)',
      borderWidth: 0,
      padding: [8, 12],
      textStyle: { color: '#fff', fontSize: 12 },
      extraCssText: 'border-radius:8px;box-shadow:0 6px 20px rgba(16,24,40,.18);'
    }, extra || {});
  }

  var JTCharts = {
    text: TEXT,
    muted: MUTED,
    gridLine: GRID_LINE,
    tooltip: baseTooltip,

    /** 读取容器上的 data-payload 并初始化实例，注册到统一列表便于 resize/dispose */
    init: function (el, option) {
      if (!el || typeof echarts === 'undefined') return null;
      var chart = echarts.init(el, null, { renderer: 'canvas' });
      chart.setOption(option);
      JTCharts.instances.push(chart);
      return chart;
    },

    payloadOf: function (el) {
      if (!el || !el.dataset.payload) return null;
      try {
        return JSON.parse(el.dataset.payload);
      } catch (err) {
        console.error('图表数据解析失败', el.id, err);
        return null;
      }
    },

    /** 空数据的统一表现，避免出现一张空白画布 */
    emptyOption: function (title) {
      return {
        title: {
          text: '暂无数据',
          left: 'center',
          top: 'middle',
          textStyle: { color: '#b4bccb', fontSize: 13, fontWeight: 'normal' }
        },
        graphic: []
      };
    },

    axisLabel: { color: MUTED, fontSize: 11 },
    axisLineStyle: { lineStyle: { color: '#e3e7ef' } },
    splitLineStyle: { lineStyle: { color: GRID_LINE, type: 'dashed' } },

    instances: []
  };

  window.addEventListener('resize', function () {
    JTCharts.instances.forEach(function (chart) {
      chart.resize();
    });
  });

  window.JTCharts = JTCharts;
})();

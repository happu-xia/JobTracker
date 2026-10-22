/* 看板图表：近 7 天趋势 + 状态分布 */
(function () {
  'use strict';
  if (typeof JTCharts === 'undefined') return;

  // ---------------- 趋势折线 ----------------
  var trendEl = document.getElementById('trendChart');
  var trend = JTCharts.payloadOf(trendEl);
  if (trendEl && trend) {
    var hasData = (trend.total || 0) > 0;
    JTCharts.init(trendEl, hasData ? {
      tooltip: JTCharts.tooltip({
        trigger: 'axis',
        axisPointer: { type: 'line', lineStyle: { color: '#c9d2e3' } },
        formatter: function (params) {
          var p = params[0];
          return p.axisValue + '<br/><b>' + p.value + '</b> 条投递';
        }
      }),
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      xAxis: {
        type: 'category',
        data: trend.labels,
        boundaryGap: false,
        axisLabel: JTCharts.axisLabel,
        axisLine: JTCharts.axisLineStyle,
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        min: 0,
        axisLabel: JTCharts.axisLabel,
        splitLine: JTCharts.splitLineStyle
      },
      series: [{
        type: 'line',
        data: trend.values,
        /* 计数型数据不用平滑：贝塞尔插值会在 0/1 之间过冲，出现「负投递」的错觉 */
        smooth: false,
        symbol: 'circle',
        symbolSize: 6,
        showSymbol: true,
        lineStyle: { width: 2.5, color: '#3b6ef6' },
        itemStyle: { color: '#3b6ef6', borderWidth: 2, borderColor: '#fff' },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(59,110,246,.22)' },
              { offset: 1, color: 'rgba(59,110,246,0)' }
            ]
          }
        }
      }]
    } : JTCharts.emptyOption('近 7 天暂无投递'));
  }

  // ---------------- 状态环形图 ----------------
  var statusEl = document.getElementById('statusChart');
  var status = JTCharts.payloadOf(statusEl);
  if (statusEl && status && status.total > 0) {
    JTCharts.init(statusEl, {
      tooltip: JTCharts.tooltip({
        trigger: 'item',
        formatter: function (p) {
          return p.name + '<br/><b>' + p.value + '</b> 条（' + p.percent + '%）';
        }
      }),
      // 环形中心显示总量，避免中间空洞
      title: {
        text: String(status.total),
        subtext: '总投递',
        left: 'center',
        top: '34%',
        textAlign: 'center',
        textStyle: { fontSize: 22, fontWeight: 700, color: '#1f2430', lineHeight: 26 },
        subtextStyle: { fontSize: 11, color: '#6b7280' }
      },
      legend: {
        bottom: 0,
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        textStyle: { color: '#6b7280', fontSize: 11 }
      },
      series: [{
        type: 'pie',
        radius: ['48%', '68%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 4 },
        /* 小卡片里 6 个扇区的引线标签必然互相压字，改为「图例 + hover 提示」 */
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 12, fontWeight: 600, formatter: '{b}\n{c} 条' }
        },
        labelLine: { show: false },
        data: status.data.filter(function (item) { return item.value > 0; })
      }]
    });
  } else if (statusEl) {
    JTCharts.init(statusEl, JTCharts.emptyOption('近 30 天暂无投递'));
  }
})();

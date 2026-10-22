/* 统计页 6 张图：状态分布 / 趋势 / 漏斗 / 职位类型 / 渠道效果 / 面试轮次 */
(function () {
  'use strict';
  if (typeof JTCharts === 'undefined') return;

  function mount(id, builder, emptyText) {
    var el = document.getElementById(id);
    var payload = JTCharts.payloadOf(el);
    if (!el || !payload) return;
    var option = builder(payload);
    JTCharts.init(el, option || JTCharts.emptyOption(emptyText || '暂无数据'));
  }

  // ---------------- 1. 状态分布 ----------------
  mount('statusChart', function (data) {
    if (!data.total) return null;
    return {
      tooltip: JTCharts.tooltip({
        trigger: 'item',
        formatter: function (p) { return p.name + '<br/><b>' + p.value + '</b> 条（' + p.percent + '%）'; }
      }),
      title: {
        text: String(data.total),
        subtext: '总投递',
        left: 'center',
        top: '33%',
        textAlign: 'center',
        textStyle: { fontSize: 22, fontWeight: 700, color: '#1f2430', lineHeight: 26 },
        subtextStyle: { fontSize: 11, color: '#6b7280' }
      },
      legend: {
        orient: 'horizontal', bottom: 0, icon: 'circle',
        itemWidth: 8, itemHeight: 8,
        textStyle: { color: '#6b7280', fontSize: 11 }
      },
      series: [{
        type: 'pie',
        radius: ['46%', '66%'],
        center: ['50%', '43%'],
        itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 4 },
        label: { show: false },
        emphasis: {
          label: {
            show: true, fontSize: 13, fontWeight: 600,
            formatter: '{b}\n{c} 条'
          }
        },
        data: data.data.filter(function (item) { return item.value > 0; })
      }]
    };
  }, '该区间暂无投递');

  // ---------------- 2. 投递趋势 ----------------
  mount('trendChart', function (data) {
    if (!data.labels || !data.labels.length) return null;
    // 天数多时抽稀横轴标签，否则 30 个「09-19」会挤在一起看不清
    var labelInterval = data.labels.length > 24 ? Math.ceil(data.labels.length / 12) : 0;
    return {
      tooltip: JTCharts.tooltip({
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: function (params) {
          var p = params[0];
          return p.axisValue + '<br/><b>' + p.value + '</b> 条投递';
        }
      }),
      grid: { left: 8, right: 16, top: 20, bottom: 8, containLabel: true },
      xAxis: {
        type: 'category',
        data: data.labels,
        axisLabel: Object.assign({}, JTCharts.axisLabel, {
          hideOverlap: true,
          interval: labelInterval
        }),
        axisLine: JTCharts.axisLineStyle,
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value', minInterval: 1,
        axisLabel: JTCharts.axisLabel,
        splitLine: JTCharts.splitLineStyle
      },
      series: [{
        type: 'bar',
        data: data.values,
        barMaxWidth: 18,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: '#5b8ff9' },
              { offset: 1, color: '#8fb4ff' }
            ]
          }
        }
      }]
    };
  }, '该区间暂无投递');

  // ---------------- 3. 转化漏斗 ----------------
  mount('funnelChart', function (data) {
    if (!data.data || !data.data.length) return null;
    var colors = ['#8fb4ff', '#5ad8a6', '#f6bd16', '#ff7875'];
    return {
      tooltip: JTCharts.tooltip({
        trigger: 'item',
        formatter: function (p) {
          var item = data.data[p.dataIndex];
          return item.name + '<br/>数量：<b>' + item.value + '</b>'
            + '<br/>环比上一层：' + item.stepRate
            + '<br/>占总量：' + item.overallRate;
        }
      }),
      series: [{
        type: 'funnel',
        left: '8%', right: '8%', top: 16, bottom: 12,
        minSize: '28%',
        gap: 4,
        label: {
          show: true, position: 'inside',
          formatter: function (p) { return p.name + ' ' + p.value; },
          color: '#fff', fontSize: 12, fontWeight: 500
        },
        itemStyle: { borderWidth: 0, borderRadius: 4 },
        data: data.data.map(function (item, index) {
          return { name: item.name, value: item.value, itemStyle: { color: colors[index % colors.length] } };
        })
      }]
    };
  }, '该区间暂无转化数据');

  // ---------------- 4. 职位类型 ----------------
  mount('jobTypeChart', function (data) {
    if (!data.data || !data.data.length) return null;
    var items = data.data.slice().reverse(); // 横向柱：数值大的放上面
    return {
      tooltip: JTCharts.tooltip({
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: function (params) { return params[0].name + '：<b>' + params[0].value + '</b> 条'; }
      }),
      grid: { left: 8, right: 40, top: 12, bottom: 8, containLabel: true },
      xAxis: {
        type: 'value', minInterval: 1,
        axisLabel: JTCharts.axisLabel,
        splitLine: JTCharts.splitLineStyle
      },
      yAxis: {
        type: 'category',
        data: items.map(function (item) { return item.name; }),
        axisLabel: JTCharts.axisLabel,
        axisLine: JTCharts.axisLineStyle,
        axisTick: { show: false }
      },
      series: [{
        type: 'bar',
        data: items.map(function (item) {
          return { value: item.value, itemStyle: { color: item.itemStyle.color, borderRadius: [0, 4, 4, 0] } };
        }),
        barMaxWidth: 18,
        label: {
          show: true, position: 'right',
          color: '#6b7280', fontSize: 11
        }
      }]
    };
  }, '还没有职位类型数据');

  // ---------------- 5. 渠道效果（堆叠柱） ----------------
  mount('channelChart', function (data) {
    if (!data.categories || !data.categories.length) return null;
    return {
      tooltip: JTCharts.tooltip({
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: function (params) {
          var name = params[0].axisValue;
          var lines = [name + '（样本 ' + (data.samples[name] || 0) + ' 条）'];
          params.forEach(function (p) {
            lines.push(p.marker + p.seriesName + '：' + p.value + ' 条');
          });
          return lines.join('<br/>');
        }
      }),
      legend: {
        top: 0, icon: 'circle', itemWidth: 8, itemHeight: 8,
        textStyle: { color: '#6b7280', fontSize: 11 }
      },
      grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
      xAxis: {
        type: 'category',
        data: data.categories,
        axisLabel: JTCharts.axisLabel,
        axisLine: JTCharts.axisLineStyle,
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value', minInterval: 1,
        axisLabel: JTCharts.axisLabel,
        splitLine: JTCharts.splitLineStyle
      },
      series: data.series.map(function (item) {
        return {
          name: item.name,
          type: 'bar',
          stack: 'channel',
          barMaxWidth: 28,
          data: item.data,
          itemStyle: { color: item.color },
          emphasis: { focus: 'series' }
        };
      })
    };
  }, '该区间暂无渠道数据');

  // ---------------- 6. 面试轮次 ----------------
  mount('roundChart', function (data) {
    if (!data.categories || !data.categories.length) return null;
    var rateMap = {};
    (data.passRates || []).forEach(function (item) { rateMap[item.round] = item.pass_rate; });
    return {
      tooltip: JTCharts.tooltip({
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: function (params) {
          var lines = [params[0].axisValue];
          params.forEach(function (p) { lines.push(p.marker + p.seriesName + '：' + p.value); });
          var rate = rateMap[params[0].axisValue];
          if (rate !== undefined) lines.push('通过率：<b>' + rate + '%</b>');
          return lines.join('<br/>');
        }
      }),
      legend: {
        top: 0, icon: 'circle', itemWidth: 8, itemHeight: 8,
        textStyle: { color: '#6b7280', fontSize: 11 }
      },
      grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
      xAxis: {
        type: 'category',
        data: data.categories,
        axisLabel: JTCharts.axisLabel,
        axisLine: JTCharts.axisLineStyle,
        axisTick: { show: false }
      },
      yAxis: {
        type: 'value', minInterval: 1,
        axisLabel: JTCharts.axisLabel,
        splitLine: JTCharts.splitLineStyle
      },
      series: data.series.map(function (item) {
        return {
          name: item.name,
          type: 'bar',
          barMaxWidth: 26,
          data: item.data,
          itemStyle: { color: item.color, borderRadius: [3, 3, 0, 0] }
        };
      })
    };
  }, '该区间暂无面试记录');
})();

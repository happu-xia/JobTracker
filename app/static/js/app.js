/* 全局交互：flash 自动淡出、删除确认、表格行链接 */
(function () {
  'use strict';

  // ---------- flash 消息 6 秒后自动淡出（用户已经看到，不必一直占位） ----------
  document.querySelectorAll('.flash-stack .alert').forEach(function (alert) {
    window.setTimeout(function () {
      if (!alert.classList.contains('show')) return;
      alert.classList.remove('show');
      window.setTimeout(function () { alert.remove(); }, 300);
    }, 6000);
  });

  // ---------- 危险操作二次确认（表单带 data-confirm 时生效） ----------
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // ---------- 日期区间：开始大于结束时自动纠正 ----------
  var dateFrom = document.querySelector('input[name="date_from"]');
  var dateTo = document.querySelector('input[name="date_to"]');
  if (dateFrom && dateTo) {
    function sync() {
      if (dateFrom.value && dateTo.value && dateFrom.value > dateTo.value) {
        dateTo.value = dateFrom.value;
      }
    }
    dateFrom.addEventListener('change', sync);
  }
})();

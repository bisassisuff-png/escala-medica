// Polling de notificações de trocas a cada 30s
(function () {
  var badge = document.getElementById('swap-badge');
  if (!badge) return;

  function poll() {
    fetch('/medico/trocas/notificacoes')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.count > 0) {
          badge.textContent = data.count;
          badge.style.display = 'inline-flex';
        } else {
          badge.style.display = 'none';
        }
      })
      .catch(function () {}); // silencia erros de rede
  }

  poll();
  setInterval(poll, 30000);
})();

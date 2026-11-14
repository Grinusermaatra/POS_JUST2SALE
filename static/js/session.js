(function () {
  function wipe() {
    const keys = [];
    for (let index = 0; index < localStorage.length; index += 1) keys.push(localStorage.key(index));
    keys.forEach((key) => {
      if (key && key.indexOf("just2sale.") === 0) localStorage.removeItem(key);
    });
    if (window.J2SOfflineClose) window.J2SOfflineClose();
    const dropDb = new Promise((resolve) => {
      const request = indexedDB.deleteDatabase("just2sale");
      request.onsuccess = () => resolve();
      request.onerror = () => resolve();
      request.onblocked = () => resolve();
    });
    const dropCache = window.caches
      ? caches.keys().then((names) => Promise.all(
        names.filter((name) => name.indexOf("just2sale") === 0).map((name) => caches.delete(name))
      ))
      : Promise.resolve();
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "wipe" });
    }
    return Promise.all([dropDb, dropCache]);
  }

  const current = document.body.dataset.userId || "";
  const previous = localStorage.getItem("just2sale.userId") || "";
  const legacy = localStorage.getItem("just2sale.deviceToken");
  let ready = Promise.resolve();
  if (legacy || (current && previous && previous !== current)) {
    ready = wipe().then(() => {
      if (current) localStorage.setItem("just2sale.userId", current);
    });
  } else if (current && previous !== current) {
    localStorage.setItem("just2sale.userId", current);
  }

  document.querySelectorAll("form[data-end-session]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.dataset.wiped === "1") return;
      event.preventDefault();
      wipe().then(() => {
        form.dataset.wiped = "1";
        form.submit();
      });
    });
  });

  window.J2SSession = { wipe, ready };
})();

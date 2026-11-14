(function () {
  function tokenKeys() {
    const keys = [];
    for (let index = 0; index < localStorage.length; index += 1) keys.push(localStorage.key(index));
    return keys.filter((key) => key && (
      key === "just2sale.deviceToken"
      || key.indexOf("just2sale.deviceToken.") === 0
      || key.indexOf("just2sale.offlineBlocked.") === 0
    ));
  }

  function clearCredentials() {
    tokenKeys().forEach((key) => localStorage.removeItem(key));
    localStorage.removeItem("just2sale.userId");
  }

  function dropCaches() {
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({ type: "wipe" });
    }
    if (!window.caches) return Promise.resolve();
    return caches.keys().then((names) => Promise.all(
      names.filter((name) => name.indexOf("just2sale") === 0).map((name) => caches.delete(name))
    ));
  }

  function openNamed(name, version, upgrade) {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(name, version);
      request.onupgradeneeded = () => {
        if (upgrade) upgrade(request.result);
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function readStore(database, storeName) {
    return new Promise((resolve, reject) => {
      if (!database.objectStoreNames.contains(storeName)) {
        resolve([]);
        return;
      }
      const request = database.transaction(storeName, "readonly").objectStore(storeName).getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  function writeSales(userId, rows) {
    if (!rows.length) return Promise.resolve();
    return openNamed("just2sale-pending-" + userId, 1, (database) => {
      if (!database.objectStoreNames.contains("sales")) {
        database.createObjectStore("sales", { keyPath: "client_uuid" });
      }
    }).then((database) => new Promise((resolve, reject) => {
      const tx = database.transaction("sales", "readwrite");
      rows.forEach((row) => tx.objectStore("sales").put(row));
      tx.oncomplete = () => {
        database.close();
        resolve();
      };
      tx.onerror = () => {
        database.close();
        reject(tx.error);
      };
    }));
  }

  function stashShared(userId) {
    if (!userId || !window.indexedDB) return Promise.resolve(true);
    return new Promise((resolve) => {
      const request = indexedDB.open("just2sale");
      let created = false;
      request.onupgradeneeded = () => {
        created = true;
        request.transaction.abort();
      };
      request.onerror = () => resolve(created);
      request.onsuccess = () => {
        const database = request.result;
        readStore(database, "sales").then((rows) => {
          database.close();
          const pending = rows.filter((row) => row && row.pending && row.client_uuid);
          return writeSales(userId, pending);
        }).then(() => resolve(true)).catch(() => resolve(false));
      };
    });
  }

  function emptyShared() {
    return new Promise((resolve) => {
      const request = indexedDB.open("just2sale");
      let created = false;
      request.onupgradeneeded = () => {
        created = true;
        request.transaction.abort();
      };
      request.onerror = () => resolve(created);
      request.onsuccess = () => {
        const database = request.result;
        const names = ["kv", "sales"].filter((name) => database.objectStoreNames.contains(name));
        if (!names.length) {
          database.close();
          resolve(true);
          return;
        }
        const tx = database.transaction(names, "readwrite");
        names.forEach((name) => tx.objectStore(name).clear());
        tx.oncomplete = () => {
          database.close();
          resolve(true);
        };
        tx.onerror = () => {
          database.close();
          resolve(false);
        };
      };
    });
  }

  function dropShared() {
    if (window.J2SOfflineClose) window.J2SOfflineClose();
    return new Promise((resolve) => {
      const request = indexedDB.deleteDatabase("just2sale");
      request.onsuccess = () => resolve();
      request.onerror = () => resolve();
      request.onblocked = () => resolve();
    });
  }

  function hideSession(userId) {
    return stashShared(userId).then((saved) => {
      if (!saved) return false;
      return emptyShared().then((cleared) => {
        if (!cleared) return false;
        clearCredentials();
        return Promise.all([dropShared(), dropCaches()]).then(() => true);
      });
    });
  }

  const current = document.body.dataset.userId || "";
  const previous = localStorage.getItem("just2sale.userId") || "";
  const legacy = localStorage.getItem("just2sale.deviceToken");
  let ready = Promise.resolve();
  if (legacy || (current && previous && previous !== current)) {
    ready = hideSession(previous || current).then(() => {
      if (current) localStorage.setItem("just2sale.userId", current);
    });
  } else if (current && previous !== current) {
    localStorage.setItem("just2sale.userId", current);
  }

  document.querySelectorAll("form[data-end-session]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (form.dataset.wiped === "1") return;
      event.preventDefault();
      hideSession(current).then((saved) => {
        if (!saved) {
          window.alert("No se pudieron apartar las ventas pendientes. La sesión sigue abierta.");
          return;
        }
        form.dataset.wiped = "1";
        form.submit();
      });
    });
  });

  window.J2SSession = { hideSession, ready };
})();

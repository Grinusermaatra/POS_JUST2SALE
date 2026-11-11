(function () {
  const root = document.getElementById("offline-root");
  if (!root || !window.J2S) return;
  const money = window.J2S;
  const places = Number(root.dataset.places || "2");
  const taxRate = root.dataset.tax || "0";
  const pricesIncludeTax = root.dataset.include === "1";
  const symbol = root.dataset.symbol || "$";
  const staleHours = Number(root.dataset.stale || "24");
  const TOKEN_KEY = "just2sale.deviceToken";
  const CART_KEY = "cart";

  const dot = document.getElementById("net-dot");
  const label = document.getElementById("net-label");
  const note = document.getElementById("offline-note");
  const saleBox = document.getElementById("offline-sale");
  const matches = document.getElementById("offline-matches");
  const cartBox = document.getElementById("offline-cart");
  const ticket = document.getElementById("offline-ticket");
  const pending = document.getElementById("pending-count");

  function db() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("just2sale", 1);
      request.onupgradeneeded = () => {
        const database = request.result;
        if (!database.objectStoreNames.contains("kv")) database.createObjectStore("kv");
        if (!database.objectStoreNames.contains("sales")) database.createObjectStore("sales", { keyPath: "client_uuid" });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  function store(name, mode) {
    return db().then((database) => {
      const tx = database.transaction(name, mode);
      return { tx, store: tx.objectStore(name) };
    });
  }

  function kvGet(key) {
    return store("kv", "readonly").then(({ store: box }) => new Promise((resolve, reject) => {
      const request = box.get(key);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    }));
  }

  function kvSet(key, value) {
    return store("kv", "readwrite").then(({ tx, store: box }) => new Promise((resolve, reject) => {
      box.put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    }));
  }

  function putSale(sale) {
    return store("sales", "readwrite").then(({ tx, store: box }) => new Promise((resolve, reject) => {
      box.put(sale);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    }));
  }

  function allSales() {
    return store("sales", "readonly").then(({ store: box }) => new Promise((resolve, reject) => {
      const request = box.getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    }));
  }

  function token() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function bestUnitDiscount(product, promotions) {
    const unit = money.parseCents(product.price, places);
    const now = Date.now();
    let best = 0;
    (promotions || []).forEach((promo) => {
      if (promo.product_ids.length && promo.product_ids.indexOf(product.id) === -1) return;
      const start = Date.parse(promo.starts_at);
      const end = Date.parse(promo.ends_at);
      if (now < start || now > end) return;
      let amount = promo.discount_type === "percent"
        ? money.percentOff(unit, promo.discount_value)
        : money.parseCents(promo.discount_value, places);
      if (amount > unit) amount = unit;
      if (amount > best) best = amount;
    });
    return best;
  }

  function lineTotalCents(unitCents, discountCents, quantity) {
    const gross = unitCents * quantity;
    const discount = Math.min(gross, discountCents * quantity);
    const net = gross - discount;
    const rate = money.parseCents(taxRate, 2) || 0;
    if (pricesIncludeTax || rate === 0) return { net, discount };
    const tax = Math.floor((net * rate + 5000) / 10000);
    return { net: net + tax, discount };
  }

  function localStock(product, sales) {
    let used = 0;
    sales.filter((sale) => sale.pending).forEach((sale) => {
      sale.lines.forEach((line) => {
        if (line.product_id === product.id) used += line.quantity;
      });
    });
    return product.stock - used;
  }

  function renderCart(catalog, cart, sales) {
    if (!cart.length) {
      cartBox.innerHTML = "<p>El carrito local está vacío.</p>";
      return;
    }
    const products = {};
    catalog.products.forEach((product) => { products[product.id] = product; });
    let total = 0;
    const rows = cart.map((line) => {
      const product = products[line.product_id];
      if (!product) return "";
      const unit = money.parseCents(product.price, places);
      const discount = bestUnitDiscount(product, catalog.promotions);
      const quoted = lineTotalCents(unit, discount, line.quantity);
      total += quoted.net;
      return "<li>" + line.quantity + " × " + product.name + " · " + symbol + money.formatCents(quoted.net, places)
        + " <button type=\"button\" data-remove=\"" + product.id + "\">Quitar</button></li>";
    }).join("");
    cartBox.innerHTML = "<ul>" + rows + "</ul><p class=\"totals\">Total " + symbol + money.formatCents(total, places) + "</p>";
    cartBox.querySelectorAll("[data-remove]").forEach((button) => {
      button.addEventListener("click", () => {
        const next = cart.filter((line) => line.product_id !== Number(button.dataset.remove));
        kvSet(CART_KEY, next).then(() => renderCart(catalog, next, sales));
      });
    });
  }

  function showMatches(catalog, query, sales) {
    const text = query.trim().toLowerCase();
    const found = catalog.products.filter((product) => {
      return !text || product.name.toLowerCase().indexOf(text) !== -1 || product.code.toLowerCase() === text;
    }).slice(0, 8);
    matches.innerHTML = found.map((product) => {
      return "<p>" + product.name + " · " + product.code + " · " + symbol + product.price
        + " · local " + localStock(product, sales)
        + " <button type=\"button\" data-add=\"" + product.id + "\">Agregar</button></p>";
    }).join("") || "<p>No está en la copia local.</p>";
    matches.querySelectorAll("[data-add]").forEach((button) => {
      button.addEventListener("click", () => addProduct(catalog, Number(button.dataset.add), sales));
    });
  }

  function addProduct(catalog, productId, sales) {
    const product = catalog.products.find((item) => item.id === productId);
    kvGet(CART_KEY).then((cart) => {
      const lines = cart || [];
      const current = lines.find((line) => line.product_id === productId);
      const nextQty = (current ? current.quantity : 0) + 1;
      if (!product || nextQty > localStock(product, sales)) {
        note.textContent = "No hay existencia suficiente en la copia local.";
        return;
      }
      const next = current
        ? lines.map((line) => line.product_id === productId ? { product_id: productId, quantity: nextQty } : line)
        : lines.concat([{ product_id: productId, quantity: 1 }]);
      return kvSet(CART_KEY, next).then(() => renderCart(catalog, next, sales));
    });
  }

  function setOnline(online) {
    dot.className = "dot " + (online ? "ok" : "bad");
    label.textContent = online ? "Con internet" : "Sin internet";
    saleBox.hidden = online;
  }

  function refreshPending() {
    return allSales().then((sales) => {
      const waiting = sales.filter((sale) => sale.pending).length;
      pending.textContent = waiting ? waiting + " pendiente(s)" : "Nada pendiente";
      return sales;
    });
  }

  function syncNow() {
    const deviceToken = token();
    if (!deviceToken || !navigator.onLine) {
      note.textContent = navigator.onLine ? "Falta el token de este dispositivo." : "Sigue sin internet.";
      return Promise.resolve();
    }
    return allSales().then((sales) => {
      const waiting = sales.filter((sale) => sale.pending);
      if (!waiting.length) return null;
      return fetch("/offline/sincronizar/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + deviceToken },
        body: JSON.stringify({ sales: waiting }),
      }).then((response) => response.json().then((body) => ({ ok: response.ok, body })));
    }).then((result) => {
      if (!result) return;
      if (!result.ok) {
        note.textContent = (result.body && result.body.error) || "No se pudo sincronizar.";
        return;
      }
      const byId = {};
      (result.body.results || []).forEach((item) => { byId[item.client_uuid] = item; });
      return waitingFrom(byId).then((jobs) => Promise.all(jobs)).then(() => refreshPending()).then(() => {
        note.textContent = "Sincronización terminada.";
      });
    }).catch(() => {
      note.textContent = "No se pudo sincronizar. Las ventas locales siguen guardadas.";
    });

    function waitingFrom(byId) {
      return allSales().then((sales) => sales.filter((sale) => sale.pending).map((sale) => {
        const result = byId[sale.client_uuid];
        if (!result || result.status === "error" && !result.folio) return Promise.resolve();
        sale.pending = false;
        sale.folio = result.folio || "";
        sale.server_status = result.status || "";
        sale.server_message = result.message || "";
        return putSale(sale);
      }));
    }
  }

  function charge(catalog, sales) {
    const form = document.getElementById("offline-charge");
    return kvGet(CART_KEY).then((cart) => {
      const lines = cart || [];
      if (!lines.length) {
        note.textContent = "El carrito local está vacío.";
        return;
      }
      const products = {};
      catalog.products.forEach((product) => { products[product.id] = product; });
      const payloadLines = [];
      let total = 0;
      for (const line of lines) {
        const product = products[line.product_id];
        if (!product) {
          note.textContent = "Un producto ya no está en la copia local.";
          return;
        }
        if (line.quantity > localStock(product, sales)) {
          note.textContent = "No hay existencia suficiente de " + product.name + ".";
          return;
        }
        const unit = money.parseCents(product.price, places);
        const unitDiscount = bestUnitDiscount(product, catalog.promotions);
        const quoted = lineTotalCents(unit, unitDiscount, line.quantity);
        total += quoted.net;
        payloadLines.push({
          product_id: product.id,
          quantity: line.quantity,
          unit_price: product.price,
          discount: money.formatCents(unitDiscount * line.quantity, places),
        });
      }
      const data = new FormData(form);
      const payments = [];
      const cash = money.parseCents(data.get("cash_tendered"), places);
      const card = money.parseCents(data.get("card_amount"), places);
      if (cash) payments.push({ method: "cash", tendered: money.formatCents(cash, places), reference: "", confirmed: true });
      if (card) {
        if (!form.card_confirmed.checked) {
          note.textContent = "Confirma el cobro en la terminal externa.";
          return;
        }
        payments.push({
          method: "card",
          tendered: money.formatCents(card, places),
          reference: String(data.get("card_reference") || ""),
          confirmed: true,
        });
      }
      const paid = (cash || 0) + (card || 0);
      const cashOnly = cash || 0;
      if (card && card > total) {
        note.textContent = "La tarjeta no puede ser mayor que el total.";
        return;
      }
      if (paid < total) {
        note.textContent = "El pago no cubre el total.";
        return;
      }
      if (paid - total > cashOnly) {
        note.textContent = "El cambio solo sale del efectivo.";
        return;
      }
      const sale = {
        client_uuid: crypto.randomUUID(),
        created_at: new Date().toISOString(),
        catalog_as_of: catalog.fetched_at,
        lines: payloadLines,
        payments: payments,
        pending: true,
        total_cents: total,
      };
      return putSale(sale).then(() => allSales()).then((saved) => {
        const stored = saved.find((item) => item.client_uuid === sale.client_uuid);
        if (!stored) throw new Error("missing");
        return kvSet(CART_KEY, []).then(() => {
          ticket.hidden = false;
          ticket.innerHTML = "<p>Venta local guardada. Folio del servidor al sincronizar.</p><p>Total "
            + symbol + money.formatCents(total, places) + "</p><p>Referencia local " + sale.client_uuid + "</p>";
          form.reset();
          return refreshPending().then((nextSales) => renderCart(catalog, [], nextSales));
        });
      });
    }).catch(() => {
      note.textContent = "No se pudo guardar la venta en este navegador.";
    });
  }

  function bootCatalog() {
    return kvGet("catalog").then((catalog) => {
      if (!catalog) {
        note.textContent = "Con internet, guarda el token y abre la caja una vez para copiar productos.";
        return;
      }
      const age = Date.now() - Date.parse(catalog.fetched_at);
      if (age > staleHours * 3600 * 1000) {
        note.textContent = "La copia de productos tiene más de " + staleHours + " horas. Conéctate para actualizarla antes de cobrar.";
        return;
      }
      return allSales().then((sales) => {
        showMatches(catalog, "", sales);
        return kvGet(CART_KEY).then((cart) => renderCart(catalog, cart || [], sales));
      });
    });
  }

  function pullCatalog() {
    const deviceToken = token();
    if (!deviceToken || !navigator.onLine) return Promise.resolve();
    return fetch("/offline/catalogo/", { headers: { "Authorization": "Bearer " + deviceToken } })
      .then((response) => response.json().then((body) => ({ ok: response.ok, body })))
      .then((result) => {
        if (!result.ok) {
          note.textContent = result.body.error || "No se pudo copiar el catálogo.";
          return;
        }
        return kvSet("catalog", result.body);
      })
      .catch(() => undefined);
  }

  document.getElementById("token-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const value = document.getElementById("device-token").value.trim();
    if (value) localStorage.setItem(TOKEN_KEY, value);
    note.textContent = value ? "Token guardado en este navegador." : "Escribe el token.";
    if (value) pullCatalog().then(bootCatalog);
  });
  document.getElementById("offline-search").addEventListener("submit", (event) => {
    event.preventDefault();
    Promise.all([kvGet("catalog"), allSales()]).then((pair) => {
      if (pair[0]) showMatches(pair[0], document.getElementById("offline-query").value, pair[1]);
    });
  });
  document.getElementById("offline-charge").addEventListener("submit", (event) => {
    event.preventDefault();
    Promise.all([kvGet("catalog"), allSales()]).then((pair) => {
      if (pair[0]) return charge(pair[0], pair[1]);
    });
  });
  document.getElementById("sync-now").addEventListener("click", () => { syncNow(); });
  window.addEventListener("online", () => {
    setOnline(true);
    pullCatalog().then(() => syncNow());
  });
  window.addEventListener("offline", () => {
    setOnline(false);
    bootCatalog();
  });
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => undefined);
  }
  const saved = token();
  if (saved) document.getElementById("device-token").value = saved;
  setOnline(navigator.onLine);
  refreshPending();
  if (navigator.onLine) pullCatalog().then(bootCatalog);
  else bootCatalog();
})();

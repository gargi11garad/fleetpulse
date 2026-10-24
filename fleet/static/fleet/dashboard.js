(() => {
  const API = "/api/v1";
  const tokenKey = "fleetpulse.access";
  const refreshKey = "fleetpulse.refresh";
  const state = { vehicles: [], drivers: [], trips: [], maintenance: [], view: "overview" };
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const prettyStatus = (value) => ({ in_use: "In use", available: "Available", maintenance: "Maintenance", inactive: "Inactive", scheduled: "Scheduled", active: "Active", completed: "Completed", cancelled: "Cancelled" }[value] || value || "Unknown");
  const statusPill = (value) => `<span class="pill pill-${escapeHtml(value)}">${escapeHtml(prettyStatus(value))}</span>`;
  const shortId = (id) => String(id || "").slice(0, 8).toUpperCase();
  const niceDate = (value) => value ? new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(value)) : "—";
  const km = (value) => `${Number(value || 0).toLocaleString()} km`;

  function showToast(message, isError = false) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("show");
    window.setTimeout(() => toast.classList.remove("show"), 3200);
  }

  function setSignedIn(signedIn, username = "Fleet manager") {
    $("#login-modal").classList.toggle("open", !signedIn);
    $("#user-label").textContent = username;
    $("#greeting-name").textContent = username.split(/[\s@]/)[0] || "Fleet manager";
  }

  async function api(path, options = {}, mayRefresh = true) {
    const headers = new Headers(options.headers || {});
    const token = localStorage.getItem(tokenKey);
    if (token) headers.set("Authorization", `Bearer ${token}`);
    if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
    let response;
    try {
      response = await fetch(`${API}${path}`, { ...options, headers });
    } catch (_) {
      throw new Error("Can’t reach FleetPulse. Check that the server is running and refresh.");
    }
    if (response.status === 401 && mayRefresh && localStorage.getItem(refreshKey)) {
      const refreshResponse = await fetch(`${API}/auth/token/refresh/`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: localStorage.getItem(refreshKey) }),
      });
      if (refreshResponse.ok) {
        const renewed = await refreshResponse.json();
        localStorage.setItem(tokenKey, renewed.access);
        return api(path, options, false);
      }
      localStorage.removeItem(tokenKey);
      localStorage.removeItem(refreshKey);
      setSignedIn(false);
    }
    if (response.status === 204) return null;
    const text = await response.text();
    let data = {};
    try { data = text ? JSON.parse(text) : {}; } catch (_) { data = { detail: text }; }
    if (!response.ok) {
      const message = data.detail || Object.entries(data).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : value}`).join(" · ") || `Request failed (${response.status})`;
      throw new Error(message);
    }
    return data;
  }

  async function login(username, password) {
    const response = await fetch(`${API}/auth/token/`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Sign-in failed. Check your username and password.");
    localStorage.setItem(tokenKey, data.access);
    localStorage.setItem(refreshKey, data.refresh);
    localStorage.setItem("fleetpulse.username", username);
    setSignedIn(true, username);
    await loadData();
  }

  async function loadData() {
    if (!localStorage.getItem(tokenKey)) return setSignedIn(false);
    setSignedIn(true, localStorage.getItem("fleetpulse.username") || "Fleet manager");
    const results = await Promise.allSettled([
      api("/dashboard/"), api("/vehicles/?page_size=100&ordering=label"), api("/drivers/?page_size=100&ordering=name"), api("/trips/?page_size=100"), api("/maintenance/?page_size=100&ordering=-service_date"),
    ]);
    const failed = results.find((result) => result.status === "rejected");
    if (failed) {
      if (failed.reason?.message?.includes("credentials")) setSignedIn(false);
      showToast(failed.reason?.message || "Some fleet data could not be loaded.", true);
      return;
    }
    const [dashboard, vehicles, drivers, trips, maintenance] = results.map((result) => result.value);
    state.vehicles = vehicles.results || [];
    state.drivers = drivers.results || [];
    state.trips = trips.results || [];
    state.maintenance = maintenance.results || [];
    renderDashboard(dashboard);
    renderVehicles();
    renderDrivers();
    renderTrips();
    renderMaintenance();
    populateSelects();
    $("#vehicle-nav-count").textContent = state.vehicles.length;
  }

  function renderDashboard(data) {
    const vehicles = data.vehicles || {};
    const byStatus = vehicles.by_status || {};
    const total = vehicles.total || 0;
    const road = byStatus.in_use || 0;
    const available = byStatus.available || 0;
    const service = vehicles.service_due || 0;
    $("#metric-total").textContent = total;
    $("#metric-road").textContent = road;
    $("#metric-available").textContent = available;
    $("#metric-service").textContent = service;
    $("#donut-total").textContent = total;
    const percent = (value) => total ? Math.max(0, Math.min(100, value / total * 100)) : 0;
    $("#road-bar").style.width = `${percent(road)}%`;
    $("#available-bar").style.width = `${percent(available)}%`;
    $("#service-bar").style.width = `${percent(service)}%`;
    const colors = { available: "#3465e8", in_use: "#24aa7a", maintenance: "#eaa13b", inactive: "#dbe1ec" };
    const statuses = ["available", "in_use", "maintenance", "inactive"];
    let start = 0;
    const slices = statuses.map((item) => {
      const end = start + percent(byStatus[item] || 0);
      const slice = `${colors[item]} ${start}% ${end}%`;
      start = end;
      return slice;
    });
    $("#availability-donut").style.background = total ? `conic-gradient(${slices.join(",")})` : "conic-gradient(#e7ebf2 0 100%)";
    $("#availability-legend").innerHTML = statuses.map((item) => `<div class="legend-row"><span class="legend-swatch" style="background:${colors[item]}"></span><span>${escapeHtml(prettyStatus(item))}</span><b>${byStatus[item] || 0}</b></div>`).join("");
    const trips = data.trips || {};
    $("#trip-active").textContent = trips.active || 0;
    $("#trip-scheduled").textContent = trips.scheduled || 0;
    $("#trip-completed").textContent = trips.completed || 0;
    const recent = [...state.trips].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 5);
    $("#recent-trip-rows").innerHTML = recent.length ? recent.map((trip) => `<tr><td class="trip-id">#${shortId(trip.id)}</td><td>${escapeHtml(trip.vehicle_label || vehicleLabel(trip.vehicle))}</td><td>${escapeHtml(trip.driver_name || driverName(trip.driver))}</td><td class="route-cell">${escapeHtml(trip.origin)}<span class="route-arrow">→</span>${escapeHtml(trip.destination)}</td><td>${statusPill(trip.status)}</td><td>${niceDate(trip.started_at || trip.created_at)}</td></tr>`).join("") : `<tr><td colspan="6" class="empty-state">No trips yet. Schedule your first trip to get started.</td></tr>`;
  }

  function vehicleLabel(id) { return state.vehicles.find((item) => item.id === id)?.label || shortId(id); }
  function driverName(id) { return state.drivers.find((item) => item.id === id)?.name || shortId(id); }

  function renderVehicles() {
    const search = ($("#vehicle-search")?.value || "").toLowerCase();
    const filter = $("#vehicle-filter")?.value || "";
    const vehicles = state.vehicles.filter((item) => (!filter || item.status === filter) && `${item.label} ${item.vin} ${item.make} ${item.model}`.toLowerCase().includes(search));
    $("#vehicle-count").textContent = `${vehicles.length} vehicle${vehicles.length === 1 ? "" : "s"}`;
    $("#vehicle-rows").innerHTML = vehicles.length ? vehicles.map((vehicle) => `<tr><td><div class="vehicle-cell"><span class="vehicle-icon">▣</span><span><b>${escapeHtml(vehicle.label)}</b><small>${escapeHtml(vehicle.make)} ${escapeHtml(vehicle.model)}</small></span></div></td><td>${escapeHtml(vehicle.vin)}</td><td>${statusPill(vehicle.status)}</td><td>${km(vehicle.odometer_km)}</td><td>${vehicle.service_due ? '<span class="pill pill-maintenance">Due now</span>' : 'On schedule'}</td><td>${escapeHtml(vehicle.year)}</td></tr>`).join("") : `<tr><td colspan="6" class="empty-state">No vehicles found.</td></tr>`;
  }

  function renderDrivers() {
    const search = ($("#driver-search")?.value || "").toLowerCase();
    const drivers = state.drivers.filter((item) => `${item.name} ${item.license_number}`.toLowerCase().includes(search));
    $("#driver-count").textContent = `${drivers.length} driver${drivers.length === 1 ? "" : "s"}`;
    $("#driver-rows").innerHTML = drivers.length ? drivers.map((driver) => `<tr><td><div class="vehicle-cell"><span class="avatar">${escapeHtml(driver.name.split(/\s+/).map((part) => part[0]).slice(0, 2).join("").toUpperCase())}</span><span><b>${escapeHtml(driver.name)}</b><small>Fleet driver</small></span></div></td><td>${escapeHtml(driver.license_number)}</td><td>${driver.active ? '<span class="pill pill-available">Active</span>' : '<span class="pill pill-inactive">Inactive</span>'}</td><td>${niceDate(driver.created_at)}</td></tr>`).join("") : `<tr><td colspan="4" class="empty-state">No drivers found.</td></tr>`;
  }

  function renderTrips() {
    const search = ($("#trip-search")?.value || "").toLowerCase();
    const filter = $("#trip-filter")?.value || "";
    const trips = state.trips.filter((trip) => (!filter || trip.status === filter) && `${trip.origin} ${trip.destination} ${vehicleLabel(trip.vehicle)} ${driverName(trip.driver)}`.toLowerCase().includes(search));
    $("#trip-count").textContent = `${trips.length} trip${trips.length === 1 ? "" : "s"}`;
    $("#trip-rows").innerHTML = trips.length ? trips.map((trip) => {
      const action = trip.status === "scheduled" ? `<button class="status-action" data-trip-action="start" data-trip-id="${escapeHtml(trip.id)}">Start trip</button>` : trip.status === "active" ? `<button class="status-action" data-trip-action="complete" data-trip-id="${escapeHtml(trip.id)}">Complete</button>` : "—";
      return `<tr><td class="trip-id">#${shortId(trip.id)}</td><td>${escapeHtml(trip.vehicle_label || vehicleLabel(trip.vehicle))}</td><td>${escapeHtml(trip.driver_name || driverName(trip.driver))}</td><td class="route-cell">${escapeHtml(trip.origin)}<span class="route-arrow">→</span>${escapeHtml(trip.destination)}</td><td>${statusPill(trip.status)}</td><td>${niceDate(trip.created_at)}</td><td>${action}</td></tr>`;
    }).join("") : `<tr><td colspan="7" class="empty-state">No trips found.</td></tr>`;
  }

  function renderMaintenance() {
    const search = ($("#maintenance-search")?.value || "").toLowerCase();
    const records = state.maintenance.filter((record) => `${record.description} ${vehicleLabel(record.vehicle)}`.toLowerCase().includes(search));
    $("#maintenance-count").textContent = `${records.length} record${records.length === 1 ? "" : "s"}`;
    $("#maintenance-rows").innerHTML = records.length ? records.map((record) => `<tr><td>${escapeHtml(vehicleLabel(record.vehicle))}</td><td>${escapeHtml(record.description)}</td><td>${niceDate(record.service_date)}</td><td>${km(record.odometer_km)}</td><td>${record.cost ? `$${Number(record.cost).toLocaleString(undefined, { minimumFractionDigits: 2 })}` : "—"}</td></tr>`).join("") : `<tr><td colspan="5" class="empty-state">No service records found.</td></tr>`;
  }

  function populateSelects() {
    const available = state.vehicles.filter((item) => item.status === "available");
    $("#trip-vehicle").innerHTML = `<option value="">Choose a vehicle</option>${available.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)} · ${escapeHtml(item.make)} ${escapeHtml(item.model)}</option>`).join("")}`;
    $("#trip-driver").innerHTML = `<option value="">Choose a driver</option>${state.drivers.filter((item) => item.active).map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join("")}`;
    $("#maintenance-vehicle").innerHTML = `<option value="">Choose a vehicle</option>${state.vehicles.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)} · ${escapeHtml(item.make)} ${escapeHtml(item.model)}</option>`).join("")}`;
  }

  function switchView(view) {
    state.view = view;
    $$(".view-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `view-${view}`));
    $$(".nav-link").forEach((link) => link.classList.toggle("active", link.dataset.view === view));
    const active = $(`.nav-link[data-view="${view}"]`);
    $("#breadcrumb-current").textContent = active?.textContent.trim() || "Overview";
    window.location.hash = view === "overview" ? "overview" : view;
  }

  function openModal(id) {
    const modal = document.getElementById(id);
    if (id === "maintenance-modal") $("#maintenance-form [name=service_date]").value ||= new Date().toISOString().slice(0, 10);
    if (modal) modal.classList.add("open");
  }
  function closeModal(modal) { modal?.classList.remove("open"); }

  async function submitForm(form, path, successMessage) {
    const button = $("button[type=submit]", form);
    button.disabled = true;
    try {
      const data = Object.fromEntries(new FormData(form).entries());
      Object.keys(data).forEach((key) => { if (data[key] === "") delete data[key]; });
      await api(path, { method: "POST", body: JSON.stringify(data) });
      closeModal(form.closest(".modal-backdrop"));
      form.reset();
      showToast(successMessage);
      await loadData();
    } catch (error) { showToast(error.message, true); }
    finally { button.disabled = false; }
  }

  $("#today-date").textContent = new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(new Date()).toUpperCase();
  $("#login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = $("button[type=submit]", form);
    button.disabled = true;
    $("#login-error").textContent = "";
    try { await login(form.elements.username.value.trim(), form.elements.password.value); }
    catch (error) { $("#login-error").textContent = error.message; }
    finally { button.disabled = false; }
  });

  $$(".nav-link").forEach((link) => link.addEventListener("click", () => switchView(link.dataset.view)));
  $$("[data-view-link]").forEach((link) => link.addEventListener("click", () => switchView(link.dataset.viewLink)));
  $$("[data-open-modal]").forEach((button) => button.addEventListener("click", () => openModal(button.dataset.openModal)));
  $$("[data-close-modal]").forEach((button) => button.addEventListener("click", () => closeModal(button.closest(".modal-backdrop"))));
  $$(".modal-backdrop").forEach((backdrop) => backdrop.addEventListener("click", (event) => { if (event.target === backdrop && backdrop.id !== "login-modal") closeModal(backdrop); }));
  $("#vehicle-form").addEventListener("submit", (event) => { event.preventDefault(); submitForm(event.currentTarget, "/vehicles/", "Vehicle added successfully."); });
  $("#driver-form").addEventListener("submit", (event) => { event.preventDefault(); submitForm(event.currentTarget, "/drivers/", "Driver added successfully."); });
  $("#trip-form").addEventListener("submit", (event) => { event.preventDefault(); submitForm(event.currentTarget, "/trips/", "Trip scheduled successfully."); });
  $("#maintenance-form").addEventListener("submit", (event) => { event.preventDefault(); submitForm(event.currentTarget, "/maintenance/", "Service record saved."); });
  $("#vehicle-search").addEventListener("input", renderVehicles);
  $("#vehicle-filter").addEventListener("change", renderVehicles);
  $("#driver-search").addEventListener("input", renderDrivers);
  $("#trip-search").addEventListener("input", renderTrips);
  $("#trip-filter").addEventListener("change", renderTrips);
  $("#maintenance-search").addEventListener("input", renderMaintenance);
  $("#refresh-button").addEventListener("click", () => loadData().then(() => showToast("Fleet data refreshed.")).catch((error) => showToast(error.message, true)));
  $("#docs-button").addEventListener("click", () => window.open("/api/docs/", "_blank", "noopener,noreferrer"));
  $("#user-menu").addEventListener("click", () => {
    if (window.confirm("Sign out of FleetPulse?")) {
      localStorage.removeItem(tokenKey); localStorage.removeItem(refreshKey); localStorage.removeItem("fleetpulse.username"); setSignedIn(false);
    }
  });
  $("#trip-rows").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-trip-action]");
    if (!button) return;
    const { tripAction, tripId } = button.dataset;
    let path = `/trips/${tripId}/${tripAction}/`;
    let body;
    if (tripAction === "complete") {
      const trip = state.trips.find((item) => item.id === tripId);
      const vehicle = state.vehicles.find((item) => item.id === trip?.vehicle);
      const endOdometer = window.prompt("Enter the vehicle's final odometer reading in km:", vehicle?.odometer_km || "");
      if (endOdometer === null) return;
      body = JSON.stringify({ end_odometer_km: endOdometer });
    }
    button.disabled = true;
    try { await api(path, { method: "POST", ...(body ? { body } : {}) }); showToast(tripAction === "start" ? "Trip started." : "Trip completed."); await loadData(); }
    catch (error) { showToast(error.message, true); button.disabled = false; }
  });

  const initialView = window.location.hash.replace("#", "");
  if (["overview", "vehicles", "trips", "drivers", "maintenance"].includes(initialView)) switchView(initialView);
  if (localStorage.getItem(tokenKey)) loadData(); else setSignedIn(false);
})();

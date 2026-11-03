let latencyChart = null;
let currentServices = [];
let selectedServiceId = null;

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
  initChart();
  fetchDashboardData();
  setInterval(fetchDashboardData, 10000);
});

function initChart() {
  const ctx = document.getElementById("latencyChart").getContext("2d");
  latencyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Response Latency (ms)",
          data: [],
          borderColor: "#6366f1",
          backgroundColor: "rgba(99, 102, 241, 0.15)",
          borderWidth: 2,
          fill: true,
          tension: 0.35,
          pointRadius: 3,
          pointHoverRadius: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1e293b",
          borderColor: "#334155",
          borderWidth: 1,
          titleColor: "#e2e8f0",
          bodyColor: "#818cf8",
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(51, 65, 85, 0.3)" },
          ticks: { color: "#94a3b8", font: { size: 10 } },
        },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(51, 65, 85, 0.3)" },
          ticks: { color: "#94a3b8", font: { size: 10 } },
        },
      },
    },
  });
}

async function fetchDashboardData() {
  try {
    await Promise.all([fetchStats(), fetchServices(), fetchIncidents()]);
    document.getElementById("last-updated-text").innerText = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    console.error("Error fetching dashboard data:", err);
  }
}

async function fetchStats() {
  const res = await fetch("/api/stats");
  if (!res.ok) return;
  const stats = await res.json();

  document.getElementById("metric-total-services").innerText = stats.total_services;
  document.getElementById("metric-services-breakdown").innerText = `${stats.services_up} up / ${stats.services_down} down`;
  document.getElementById("metric-uptime").innerText = `${stats.overall_uptime_pct}%`;
  document.getElementById("metric-latency").innerText = `${stats.avg_response_time_ms} ms`;
  document.getElementById("metric-incidents").innerText = stats.active_incidents;

  const incidentStatus = document.getElementById("metric-incident-status");
  if (stats.active_incidents > 0) {
    incidentStatus.innerText = "System degraded";
    incidentStatus.className = "text-xs text-rose-400 font-semibold";
  } else {
    incidentStatus.innerText = "All systems normal";
    incidentStatus.className = "text-xs text-emerald-400 font-medium";
  }
}

async function fetchServices() {
  const res = await fetch("/api/services");
  if (!res.ok) return;
  currentServices = await res.json();

  // Populate Select Dropdown for Chart
  const select = document.getElementById("chart-service-select");
  const previousValue = select.value;
  select.innerHTML = "";

  currentServices.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.innerText = `${s.name} (${s.url})`;
    select.appendChild(opt);
  });

  if (currentServices.length > 0) {
    if (previousValue && currentServices.some((s) => s.id == previousValue)) {
      select.value = previousValue;
      selectedServiceId = previousValue;
    } else {
      select.value = currentServices[0].id;
      selectedServiceId = currentServices[0].id;
    }
    loadHistoryForSelectedService();
  }

  // Render Table Rows
  const tbody = document.getElementById("services-tbody");
  tbody.innerHTML = "";

  currentServices.forEach((s) => {
    const tr = document.createElement("tr");
    tr.className = "hover:bg-slate-800/40 transition";

    let statusBadge = '<span class="px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-700 text-slate-300">Pending</span>';
    if (s.is_up === true) {
      statusBadge = '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"><span class="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping"></span> Operational</span>';
    } else if (s.is_up === false) {
      statusBadge = '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20"><span class="h-1.5 w-1.5 rounded-full bg-rose-400"></span> Down</span>';
    }

    const latencyText = s.last_response_time_ms !== null ? `${s.last_response_time_ms} ms` : "—";
    const checkedText = s.last_checked_at ? new Date(s.last_checked_at).toLocaleTimeString() : "Never";

    tr.innerHTML = `
      <td class="px-6 py-4">${statusBadge}</td>
      <td class="px-6 py-4 font-medium text-white">${escapeHtml(s.name)}</td>
      <td class="px-6 py-4 font-mono text-xs text-slate-400">${escapeHtml(s.url)}</td>
      <td class="px-6 py-4 text-xs text-slate-400">${s.interval_seconds}s</td>
      <td class="px-6 py-4 font-semibold ${s.uptime_percentage >= 99 ? 'text-emerald-400' : 'text-amber-400'}">${s.uptime_percentage}%</td>
      <td class="px-6 py-4 text-slate-200">${latencyText}</td>
      <td class="px-6 py-4 text-right space-x-2">
        <button onclick="checkNow(${s.id})" title="Trigger check" class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"><i class="fa-solid fa-bolt text-xs"></i></button>
        <button onclick="deleteService(${s.id})" title="Delete" class="p-1.5 rounded-lg bg-slate-800 hover:bg-rose-900/50 hover:text-rose-400 text-slate-400 transition"><i class="fa-solid fa-trash text-xs"></i></button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

async function loadHistoryForSelectedService() {
  const select = document.getElementById("chart-service-select");
  if (!select.value) return;
  const serviceId = select.value;

  try {
    const res = await fetch(`/api/services/${serviceId}/history?limit=25`);
    if (!res.ok) return;
    const history = await res.json();

    const labels = history.map((h) => new Date(h.checked_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
    const data = history.map((h) => h.response_time_ms || 0);

    latencyChart.data.labels = labels;
    latencyChart.data.datasets[0].data = data;
    latencyChart.update();
  } catch (err) {
    console.error("Error loading service history:", err);
  }
}

async function fetchIncidents() {
  const res = await fetch("/api/incidents");
  if (!res.ok) return;
  const incidents = await res.json();
  const container = document.getElementById("incidents-container");

  if (incidents.length === 0) {
    container.innerHTML = `
      <div class="text-center py-6 text-slate-400 text-sm">
        <i class="fa-solid fa-circle-check text-emerald-400 text-2xl mb-2"></i>
        <p>No recent incidents recorded. All services operating smoothly.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  incidents.forEach((inc) => {
    const badge = inc.is_resolved
      ? '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Resolved</span>'
      : '<span class="px-2 py-0.5 rounded text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20 animate-pulse">Active Outage</span>';

    const div = document.createElement("div");
    div.className = "flex items-center justify-between p-3.5 bg-slate-900/40 rounded-xl border border-darkborder text-sm";
    div.innerHTML = `
      <div class="space-y-0.5">
        <div class="flex items-center gap-2">
          ${badge}
          <span class="font-medium text-white">Service #${inc.service_id} Outage</span>
        </div>
        <p class="text-xs text-slate-400">${escapeHtml(inc.cause)}</p>
      </div>
      <div class="text-right text-xs text-slate-500">
        <span>Started ${new Date(inc.started_at).toLocaleTimeString()}</span>
        ${inc.resolved_at ? `<br><span class="text-emerald-500">Resolved ${new Date(inc.resolved_at).toLocaleTimeString()}</span>` : ""}
      </div>
    `;
    container.appendChild(div);
  });
}

async function checkNow(serviceId) {
  try {
    await fetch(`/api/services/${serviceId}/check`, { method: "POST" });
    await fetchDashboardData();
  } catch (err) {
    console.error("Error triggering check:", err);
  }
}

async function triggerAllChecks() {
  for (const s of currentServices) {
    await checkNow(s.id);
  }
}

async function deleteService(serviceId) {
  if (!confirm("Are you sure you want to remove this monitored service?")) return;
  await fetch(`/api/services/${serviceId}`, { method: "DELETE" });
  await fetchDashboardData();
}

async function handleCreateService(event) {
  event.preventDefault();
  const payload = {
    name: document.getElementById("input-name").value.trim(),
    url: document.getElementById("input-url").value.trim(),
    method: document.getElementById("input-method").value,
    expected_status: parseInt(document.getElementById("input-expected-status").value),
    interval_seconds: parseInt(document.getElementById("input-interval").value),
    timeout_seconds: parseInt(document.getElementById("input-timeout").value),
  };

  const res = await fetch("/api/services", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (res.ok) {
    const created = await res.json();
    await checkNow(created.id);
    closeModal();
    document.getElementById("add-service-form").reset();
    await fetchDashboardData();
  } else {
    alert("Failed to create service. Please verify the URL.");
  }
}

function openModal() {
  document.getElementById("add-modal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("add-modal").classList.add("hidden");
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

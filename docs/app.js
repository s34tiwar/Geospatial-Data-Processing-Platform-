const datasets = {
  waterloo: {
    name: "North Waterloo", subtitle: "North Waterloo · 2.4 km²",
    leads: [
      { id: 1, name: "Northfield Commerce Centre", address: "Northfield Dr E, Waterloo", area: 4280, score: 92, signals: ["ponding", "discoloration"], x: 68, y: 29 },
      { id: 2, name: "Conestoga Industrial Building", address: "Davenport Rd, Waterloo", area: 3150, score: 84, signals: ["patching", "discoloration"], x: 39, y: 38 },
      { id: 3, name: "Colby Drive Warehouse", address: "Colby Dr, Waterloo", area: 5840, score: 78, signals: ["ponding"], x: 24, y: 66 },
      { id: 4, name: "Labrador Drive Complex", address: "Labrador Dr, Waterloo", area: 2690, score: 69, signals: ["patching"], x: 81, y: 69 },
      { id: 5, name: "Parkside Distribution", address: "Parkside Dr, Waterloo", area: 6320, score: 57, signals: ["discoloration"], x: 52, y: 76 },
      { id: 6, name: "Bathurst Business Unit", address: "Bathurst Dr, Waterloo", area: 1880, score: 46, signals: ["patching"], x: 17, y: 29 }
    ]
  },
  kitchener: {
    name: "Kitchener Innovation District", subtitle: "Kitchener Innovation District · 1.8 km²",
    leads: [
      { id: 7, name: "Victoria Street Works", address: "Victoria St N, Kitchener", area: 4720, score: 89, signals: ["ponding", "patching"], x: 58, y: 32 },
      { id: 8, name: "Breithaupt Block Annex", address: "Breithaupt St, Kitchener", area: 2410, score: 81, signals: ["discoloration"], x: 32, y: 52 },
      { id: 9, name: "Glasgow Commerce Hub", address: "Glasgow St, Kitchener", area: 5190, score: 73, signals: ["patching", "discoloration"], x: 75, y: 61 },
      { id: 10, name: "King West Workshop", address: "King St W, Kitchener", area: 1980, score: 62, signals: ["ponding"], x: 44, y: 77 },
      { id: 11, name: "Railway Distribution Unit", address: "Ahrens St W, Kitchener", area: 7220, score: 51, signals: ["discoloration"], x: 19, y: 24 }
    ]
  },
  cambridge: {
    name: "Cambridge Industrial Park", subtitle: "Cambridge Industrial Park · 3.1 km²",
    leads: [
      { id: 12, name: "Pinebush Logistics Centre", address: "Pinebush Rd, Cambridge", area: 8340, score: 95, signals: ["ponding", "patching", "discoloration"], x: 72, y: 38 },
      { id: 13, name: "Franklin Manufacturing", address: "Franklin Blvd, Cambridge", area: 6150, score: 86, signals: ["patching"], x: 43, y: 29 },
      { id: 14, name: "Sheldon Drive Warehouse", address: "Sheldon Dr, Cambridge", area: 4860, score: 76, signals: ["ponding", "discoloration"], x: 25, y: 63 },
      { id: 15, name: "Hespeler Commerce Park", address: "Hespeler Rd, Cambridge", area: 3570, score: 67, signals: ["discoloration"], x: 64, y: 74 },
      { id: 16, name: "Boxwood Business Centre", address: "Boxwood Dr, Cambridge", area: 2930, score: 55, signals: ["patching"], x: 84, y: 61 }
    ]
  }
};

const labels = { ponding: "Possible ponding", patching: "Surface patching", discoloration: "Discoloration" };
const area = document.querySelector("#area");
const threshold = document.querySelector("#threshold");
const thresholdOutput = document.querySelector("#threshold-output");
const scanButton = document.querySelector("#scan-button");
const scanLine = document.querySelector("#scan-line");
const emptyState = document.querySelector("#scan-empty");
const markers = document.querySelector("#markers");
const results = document.querySelector("#results");
const resultsBody = document.querySelector("#results-body");
const resultCount = document.querySelector("#result-count");
const mapSubtitle = document.querySelector("#map-subtitle");
const toast = document.querySelector("#toast");
let visibleLeads = [];

const scoreClass = score => score >= 80 ? "high" : score >= 60 ? "medium" : "low";

function selectedSignals() {
  return [...document.querySelectorAll('.check input:checked')].map(input => input.value);
}

function filteredLeads() {
  const selected = selectedSignals();
  return datasets[area.value].leads
    .filter(lead => lead.score >= Number(threshold.value))
    .filter(lead => lead.signals.some(signal => selected.includes(signal)))
    .sort((a, b) => b.score - a.score);
}

function render() {
  visibleLeads = filteredLeads();
  markers.replaceChildren();
  resultsBody.replaceChildren();

  visibleLeads.forEach((lead, index) => {
    const marker = document.createElement("button");
    marker.className = `marker ${scoreClass(lead.score)}`;
    marker.style.left = `${lead.x}%`;
    marker.style.top = `${lead.y}%`;
    marker.style.animationDelay = `${index * 80}ms`;
    marker.setAttribute("aria-label", `${lead.name}, opportunity score ${lead.score}`);
    marker.innerHTML = `<b>${lead.score}</b><span>${lead.name}</span>`;
    marker.addEventListener("click", () => focusLead(lead.id));
    markers.append(marker);

    const row = document.createElement("tr");
    row.id = `lead-${lead.id}`;
    row.innerHTML = `
      <td><strong>${lead.name}</strong><small>${lead.address}</small></td>
      <td>${lead.area.toLocaleString()} m²</td>
      <td>${lead.signals.map(signal => `<span class="signal">${labels[signal]}</span>`).join("")}</td>
      <td><span class="score ${scoreClass(lead.score)}">${lead.score} / 100</span></td>
      <td><button class="view-on-map" data-id="${lead.id}">Locate ↑</button></td>`;
    resultsBody.append(row);
  });

  resultCount.textContent = visibleLeads.length;
  results.hidden = false;
  emptyState.hidden = visibleLeads.length > 0;
  if (!visibleLeads.length) {
    emptyState.querySelector("strong").textContent = "No matching properties";
    emptyState.querySelector("small").textContent = "Lower the score or include more signals, then scan again.";
  }

  document.querySelectorAll(".view-on-map").forEach(button => button.addEventListener("click", () => focusLead(Number(button.dataset.id))));
}

function focusLead(id) {
  const lead = visibleLeads.find(item => item.id === id);
  if (!lead) return;
  const marker = [...markers.children].find(item => item.getAttribute("aria-label").startsWith(lead.name));
  marker?.focus();
  document.querySelector("#workspace").scrollIntoView({ behavior: "smooth", block: "center" });
}

function runScan() {
  scanButton.disabled = true;
  scanButton.querySelector(".button-label").textContent = "Analyzing footprints…";
  emptyState.hidden = true;
  markers.replaceChildren();
  results.hidden = true;
  scanLine.classList.remove("active");
  void scanLine.offsetWidth;
  scanLine.classList.add("active");
  window.setTimeout(() => {
    render();
    scanButton.disabled = false;
    scanButton.querySelector(".button-label").textContent = "Run simulated scan";
    showToast(`${visibleLeads.length} sample opportunities found in ${datasets[area.value].name}.`);
  }, 1800);
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3000);
}

threshold.addEventListener("input", () => thresholdOutput.value = threshold.value);
area.addEventListener("change", () => {
  mapSubtitle.textContent = datasets[area.value].subtitle;
  if (!results.hidden) runScan();
});
scanButton.addEventListener("click", runScan);

document.querySelector("#export-button").addEventListener("click", () => {
  const header = ["Property", "Address", "Roof area (m2)", "Signals", "Synthetic opportunity score"];
  const rows = visibleLeads.map(lead => [lead.name, lead.address, lead.area, lead.signals.map(signal => labels[signal]).join("; "), lead.score]);
  const csv = [header, ...rows].map(row => row.map(value => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "mapwork-sample-leads.csv";
  link.click();
  URL.revokeObjectURL(url);
  showToast("Sample CSV exported.");
});

// ==========================================
// Drone Monitor Map - Frontend Logic
// ==========================================

// Global State
let map;
let threats = [];
let selectedThreatId = null;
let currentTool = 'drone';
let regionsLayer = null;
let markersLayer = null;

// Trajectory lines layer
let trajectoriesLayer = null;
const DEFAULT_TRAJECTORY_LENGTH = 100; // km

// AUTO Mode state
let autoModeEnabled = false;
let wsConnection = null;
let wsReconnectTimer = null;

// Check if we're in view mode (for screenshots)
const urlParams = new URLSearchParams(window.location.search);
const isViewMode = urlParams.get('view') === 'true';

// ==========================================
// Initialization
// ==========================================

document.addEventListener('DOMContentLoaded', async () => {
    initMap();
    initClock();
    
    if (isViewMode) {
        // Hide controls in view mode
        const controls = document.getElementById('controls');
        if (controls) controls.style.display = 'none';
        
        const helpBtn = document.getElementById('help-btn');
        if (helpBtn) helpBtn.style.display = 'none';
        
        // Load state from server
        await loadStateFromServer();
    }
    
    // Initialize WebSocket for real-time updates
    initWebSocket();
    
    // Check AUTO mode status
    checkAutoStatus();
    
    updateOverlay();
});

function initMap() {
    // Initialize Leaflet map centered on Ukraine
    map = L.map('map', {
        center: [48.5, 31.5],
        zoom: 6,
        zoomControl: !isViewMode,
        attributionControl: !isViewMode
    });

    // Dark tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(map);

    // Initialize layers
    trajectoriesLayer = L.layerGroup().addTo(map);
    
    // Use MarkerClusterGroup for clustering when zoomed out
    markersLayer = L.markerClusterGroup({
        maxClusterRadius: 50,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        iconCreateFunction: function(cluster) {
            const childMarkers = cluster.getAllChildMarkers();
            let totalCount = 0;
            childMarkers.forEach(m => {
                const threat = threats.find(t => t.id === m.threatId);
                if (threat) totalCount += threat.count;
            });
            
            return L.divIcon({
                html: `<div class="cluster-icon">${totalCount}</div>`,
                className: 'marker-cluster-custom',
                iconSize: [40, 40]
            });
        }
    }).addTo(map);
    
    // Load Ukraine regions GeoJSON
    loadRegions();

    // Map click handler (add threat)
    if (!isViewMode) {
        map.on('click', onMapClick);
        map.on('contextmenu', onMapRightClick);
    }
    
    // Update trajectory visibility on zoom
    map.on('zoomend', updateTrajectoriesVisibility);
    
    // Disable browser context menu on map
    document.getElementById('map').addEventListener('contextmenu', (e) => {
        e.preventDefault();
    });
    
    // Keyboard handler for deleting selected threat
    document.addEventListener('keydown', (e) => {
        if ((e.key === 'Delete' || e.key === 'Backspace') && selectedThreatId !== null) {
            // Prevent backspace from navigating back
            if (e.key === 'Backspace' && document.activeElement.tagName !== 'INPUT') {
                e.preventDefault();
            }
            deleteThreat(selectedThreatId);
            selectedThreatId = null;
        }
    });
}

async function loadRegions() {
    try {
        const response = await fetch('ukraine-regions.json');
        const topoData = await response.json();
        
        // Convert TopoJSON to GeoJSON
        const geojson = topojson.feature(topoData, topoData.objects.UKR_adm1);
        
        regionsLayer = L.geoJSON(geojson, {
            style: {
                color: '#374151',
                weight: 1,
                fillColor: 'transparent',
                fillOpacity: 0
            },
            onEachFeature: (feature, layer) => {
                // Store region name for lookup
                layer.regionName = feature.properties.NAME_1;
            }
        }).addTo(map);
    } catch (error) {
        console.error('Failed to load regions:', error);
    }
}

function getRegionForPoint(lat, lng) {
    if (!regionsLayer) return null;
    
    const point = L.latLng(lat, lng);
    let regionName = null;
    
    regionsLayer.eachLayer(layer => {
        if (layer.getBounds && layer.getBounds().contains(point)) {
            // More precise check using point-in-polygon
            if (isPointInLayer(point, layer)) {
                regionName = layer.regionName;
            }
        }
    });
    
    return regionName;
}

function isPointInLayer(point, layer) {
    // Use ray casting algorithm for polygon
    if (!layer.getLatLngs) return false;
    
    const latlngs = layer.getLatLngs();
    // Handle MultiPolygon or Polygon
    const polygon = Array.isArray(latlngs[0][0]) ? latlngs[0] : latlngs;
    
    if (!polygon[0] || !Array.isArray(polygon[0])) return false;
    
    const ring = polygon[0];
    let inside = false;
    
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const xi = ring[i].lng, yi = ring[i].lat;
        const xj = ring[j].lng, yj = ring[j].lat;
        
        if (((yi > point.lat) !== (yj > point.lat)) &&
            (point.lng < (xj - xi) * (point.lat - yi) / (yj - yi) + xi)) {
            inside = !inside;
        }
    }
    
    return inside;
}

function initClock() {
    updateClock();
    setInterval(updateClock, 1000);
}

function updateClock() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
    
    const clockEl = document.getElementById('clock');
    if (clockEl) clockEl.textContent = timeStr;
}

// ==========================================
// Map Interaction
// ==========================================

function onMapClick(e) {
    const groupSize = parseInt(document.getElementById('group-size').value) || 1;
    
    const threat = {
        id: Date.now(),
        type: currentTool,
        lat: e.latlng.lat,
        lng: e.latlng.lng,
        angle: 0,
        count: groupSize,
        trajectoryLength: DEFAULT_TRAJECTORY_LENGTH
    };
    
    threats.push(threat);
    const marker = addMarker(threat);
    updateThreatList();
    updateOverlay();
    syncStateToServer();
    
    // Auto-select the new marker
    selectThreat(threat.id);
}

function onMapRightClick(e) {
    // Set trajectory direction and length for selected marker
    if (selectedThreatId === null) return;
    
    const threat = threats.find(t => t.id === selectedThreatId);
    if (!threat) return;
    
    // Find the marker
    let selectedMarker = null;
    markersLayer.eachLayer(marker => {
        if (marker.threatId === selectedThreatId) {
            selectedMarker = marker;
        }
    });
    if (!selectedMarker) return;
    
    // Calculate angle and distance from marker to click point
    const clickLat = e.latlng.lat;
    const clickLng = e.latlng.lng;
    
    // Calculate angle (0 = North, 90 = East, etc.)
    const deltaLat = clickLat - threat.lat;
    const deltaLng = (clickLng - threat.lng) * Math.cos(threat.lat * Math.PI / 180);
    
    let angle = Math.atan2(deltaLng, deltaLat) * (180 / Math.PI);
    if (angle < 0) angle += 360;
    
    // Calculate distance in km
    const distanceDeg = Math.sqrt(deltaLat * deltaLat + deltaLng * deltaLng);
    const distanceKm = distanceDeg * 111;
    
    // Update threat
    threat.angle = angle;
    threat.trajectoryLength = Math.max(0, distanceKm);
    
    // Update marker icon (rotation)
    const iconHtml = createMarkerHtml(threat);
    const icon = L.divIcon({
        html: iconHtml,
        className: 'custom-marker',
        iconSize: [40, 40],
        iconAnchor: [20, 20]
    });
    selectedMarker.setIcon(icon);
    
    // Update trajectory line
    updateTrajectoryLine(selectedMarker, threat);
    
    syncStateToServer();
}

function addMarker(threat) {
    const iconHtml = createMarkerHtml(threat);
    
    const icon = L.divIcon({
        html: iconHtml,
        className: 'custom-marker',
        iconSize: [40, 40],
        iconAnchor: [20, 20]
    });
    
    const marker = L.marker([threat.lat, threat.lng], {
        icon: icon,
        draggable: !isViewMode,
        rotationAngle: threat.angle,
        rotationOrigin: 'center center'
    });
    
    marker.threatId = threat.id;
    
    // Create trajectory line
    const trajectoryLine = createTrajectoryLine(threat);
    marker.trajectoryLine = trajectoryLine;
    
    if (!isViewMode) {
        // Drag handler - update trajectory while dragging
        marker.on('drag', (e) => {
            const t = threats.find(t => t.id === threat.id);
            if (t) {
                t.lat = e.target.getLatLng().lat;
                t.lng = e.target.getLatLng().lng;
                updateTrajectoryLine(marker, t);
            }
        });
        
        // Drag end handler
        marker.on('dragend', (e) => {
            const t = threats.find(t => t.id === threat.id);
            if (t) {
                t.lat = e.target.getLatLng().lat;
                t.lng = e.target.getLatLng().lng;
                updateThreatList();
                syncStateToServer();
            }
        });
        
        // Click to select
        marker.on('click', (e) => {
            L.DomEvent.stopPropagation(e);
            selectThreat(threat.id);
        });
        
        // Prevent context menu on marker
        marker.on('add', () => {
            const el = marker.getElement();
            if (el) {
                el.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                });
            }
        });
    }
    
    marker.addTo(markersLayer);
    return marker;
}

function getColorFilter(hexColor) {
    // Convert hex color to CSS filter for coloring SVG images
    // Pre-calculated filters for our specific colors
    const filters = {
        '#f59e0b': 'brightness(0) saturate(100%) invert(67%) sepia(74%) saturate(2243%) hue-rotate(360deg) brightness(101%) contrast(101%)', // Orange - drone
        '#ef4444': 'brightness(0) saturate(100%) invert(36%) sepia(93%) saturate(2066%) hue-rotate(338deg) brightness(95%) contrast(97%)', // Red - missile
        '#8b5cf6': 'brightness(0) saturate(100%) invert(44%) sepia(94%) saturate(2726%) hue-rotate(243deg) brightness(97%) contrast(96%)', // Purple - ballistic
        '#06b6d4': 'brightness(0) saturate(100%) invert(63%) sepia(96%) saturate(1352%) hue-rotate(152deg) brightness(95%) contrast(94%)', // Cyan - hypersonic
        '#facc15': 'brightness(0) saturate(100%) invert(83%) sepia(46%) saturate(1057%) hue-rotate(359deg) brightness(103%) contrast(97%)', // Yellow - nuclear
    };
    return filters[hexColor] || 'brightness(0) saturate(100%) invert(67%) sepia(74%) saturate(2243%) hue-rotate(360deg)';
}

function createMarkerHtml(threat) {
    // Define threat type properties - using custom SVG icons
    // All SVG icons have nose pointing UP (0° = north)
    const typeConfig = {
        drone: { svg: 'icons/drone.svg', color: '#f59e0b' },
        missile: { svg: 'icons/missile.svg', color: '#ef4444' },
        ballistic: { svg: 'icons/ballistic.svg', color: '#8b5cf6' },
        hypersonic: { svg: 'icons/missile.svg', color: '#06b6d4' },
        nuclear: { svg: 'icons/nuclear.svg', color: '#facc15' }
    };
    
    const config = typeConfig[threat.type] || typeConfig.drone;
    const iconClass = `${threat.type}-icon`;
    const color = config.color;
    
    // Rotate icon so nose points in direction of trajectory
    // SVG nose points UP (0°), angle 0=north, 90=east, 180=south, 270=west
    const iconRotation = threat.angle;
    
    let html;
    
    if (config.svg) {
        // Use custom SVG icon with color filter
        // NOTE: Rotation is handled by Leaflet rotationAngle, not CSS transform
        const colorFilter = getColorFilter(color);
        html = `
            <div class="${iconClass}" style="
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
                filter: drop-shadow(0 0 10px ${color});
            ">
                <img src="${config.svg}" style="width: 32px; height: 32px; filter: ${colorFilter};" />
            </div>
        `;
    } else {
        // Fallback to emoji
        // NOTE: Rotation is handled by Leaflet rotationAngle, not CSS transform
        html = `
            <div class="${iconClass}" style="
                font-size: 28px;
                color: ${color};
                text-shadow: 0 0 10px ${color};
                display: flex;
                align-items: center;
                justify-content: center;
                width: 40px;
                height: 40px;
            ">
                ${config.icon}
            </div>
        `;
    }
    
    // Add count badge if > 1
    if (threat.count > 1) {
        html += `<div class="count-badge">${threat.count}</div>`;
    }
    
    return html;
}

// ==========================================
// Trajectory Line Functions
// ==========================================

function getColorForType(type) {
    const colors = {
        drone: '#f59e0b',      // Orange
        missile: '#ef4444',     // Red
        ballistic: '#8b5cf6',   // Purple
        hypersonic: '#06b6d4',  // Cyan
        nuclear: '#facc15'      // Yellow
    };
    return colors[type] || colors.drone;
}

function createTrajectoryLine(threat) {
    const endPoint = calculateTrajectoryEndPoint(threat);
    
    const color = getColorForType(threat.type);
    // Default opacity 50% for non-selected markers
    const isSelected = selectedThreatId === threat.id;
    
    const line = L.polyline([[threat.lat, threat.lng], endPoint], {
        color: color,
        weight: 2,
        dashArray: '10, 6',
        opacity: isSelected ? 1.0 : 0.5
    });
    
    line.addTo(trajectoriesLayer);
    return line;
}

function calculateTrajectoryEndPoint(threat) {
    // Convert angle to radians (0 = East, 90 = North in standard math)
    // But we want 0 = North, 90 = East (compass style)
    const angleRad = (90 - threat.angle) * (Math.PI / 180);
    
    // Calculate distance in degrees (approximate: 1 degree ≈ 111 km)
    const distanceDeg = (threat.trajectoryLength || DEFAULT_TRAJECTORY_LENGTH) / 111;
    
    const endLat = threat.lat + distanceDeg * Math.sin(angleRad);
    const endLng = threat.lng + distanceDeg * Math.cos(angleRad) / Math.cos(threat.lat * Math.PI / 180);
    
    return [endLat, endLng];
}

function updateTrajectoryLine(marker, threat) {
    if (marker.trajectoryLine) {
        const endPoint = calculateTrajectoryEndPoint(threat);
        marker.trajectoryLine.setLatLngs([[threat.lat, threat.lng], endPoint]);
    }
}

function updateTrajectoriesVisibility() {
    const zoom = map.getZoom();
    // Hide trajectories when zoomed out (zoom < 7), show when zoomed in
    const opacity = zoom < 7 ? 0 : (zoom < 9 ? 0.3 : 0.5);
    const selectedOpacity = zoom < 7 ? 0.3 : 1.0;
    
    markersLayer.eachLayer(marker => {
        if (marker.trajectoryLine) {
            const isSelected = marker.threatId === selectedThreatId;
            marker.trajectoryLine.setStyle({
                opacity: isSelected ? selectedOpacity : opacity
            });
        }
    });
}

function selectThreat(id) {
    selectedThreatId = id;
    
    // Update list selection
    document.querySelectorAll('.threat-item').forEach(item => {
        if (parseInt(item.dataset.id) === id) {
            item.style.backgroundColor = '#3b82f6';
            item.style.color = 'white';
        } else {
            item.style.backgroundColor = '#252a40';
            item.style.color = '';
        }
    });
    
    // Update marker selection (visual glow) and trajectory opacity
    markersLayer.eachLayer(marker => {
        const el = marker.getElement();
        if (el) {
            if (marker.threatId === id) {
                el.classList.add('selected-marker');
            } else {
                el.classList.remove('selected-marker');
            }
        }
        
        // Update trajectory line opacity
        if (marker.trajectoryLine) {
            marker.trajectoryLine.setStyle({
                opacity: marker.threatId === id ? 1.0 : 0.5
            });
        }
    });
    
    // Pan to selected threat
    const threat = threats.find(t => t.id === id);
    if (threat) {
        map.panTo([threat.lat, threat.lng]);
    }
    
    // Clear region selection
    updateSelectedRegionDisplay(null);
}

let selectedRegion = null;

function selectRegion(regionName, group) {
    selectedRegion = regionName;
    
    // Highlight region header
    document.querySelectorAll('.region-header').forEach(header => {
        if (header.dataset.region === regionName) {
            header.classList.add('selected');
        } else {
            header.classList.remove('selected');
        }
    });
    
    // Find region bounds and zoom to it
    if (regionsLayer) {
        regionsLayer.eachLayer(layer => {
            if (layer.regionName === regionName) {
                map.fitBounds(layer.getBounds(), { padding: [50, 50] });
            }
        });
    }
    
    // Update selected region display
    updateSelectedRegionDisplay(regionName, group);
    
    // Clear threat selection
    selectedThreatId = null;
    markersLayer.eachLayer(marker => {
        const el = marker.getElement();
        if (el) el.classList.remove('selected-marker');
    });
}

function updateSelectedRegionDisplay(regionName, group) {
    const display = document.getElementById('selected-region-display');
    if (!display) return;
    
    if (!regionName || !group) {
        display.style.display = 'none';
        return;
    }
    
    const typeLabels = {
        drone: 'БПЛА',
        missile: 'КР',
        ballistic: 'Балістика',
        hypersonic: 'Гіперзвук',
        nuclear: 'Ядерна'
    };
    
    const counts = [];
    Object.keys(group.counts).forEach(type => {
        if (group.counts[type] > 0) {
            counts.push(`${group.counts[type]} ${typeLabels[type] || type}`);
        }
    });
    
    display.innerHTML = `<strong>${regionName}:</strong> ${counts.join(', ')}`;
    display.style.display = 'block';
}

// ==========================================
// Tool Selection
// ==========================================

function setTool(type) {
    currentTool = type;
    
    document.querySelectorAll('.tool-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.type === type) {
            btn.classList.add('active');
        }
    });
}

// ==========================================
// Threat List Management
// ==========================================

function updateThreatList() {
    const list = document.getElementById('threat-list');
    if (!list) return;
    
    list.innerHTML = '';
    
    // Type labels for display
    const typeLabels = {
        drone: 'БПЛА',
        missile: 'КР',
        ballistic: 'Балістика',
        hypersonic: 'Гіперзвук',
        nuclear: 'Ядерна'
    };
    
    // Count totals by type
    const totalCounts = {};
    
    // Group threats by region
    const regionGroups = {};
    
    threats.forEach(threat => {
        // Count totals
        if (!totalCounts[threat.type]) totalCounts[threat.type] = 0;
        totalCounts[threat.type] += threat.count;
        
        // Get region for this threat
        const region = getRegionForPoint(threat.lat, threat.lng) || 'Невідома область';
        
        if (!regionGroups[region]) {
            regionGroups[region] = {
                counts: {},
                threats: []
            };
        }
        
        if (!regionGroups[region].counts[threat.type]) {
            regionGroups[region].counts[threat.type] = 0;
        }
        regionGroups[region].counts[threat.type] += threat.count;
        regionGroups[region].threats.push(threat);
    });
    
    // Render grouped list
    Object.keys(regionGroups).sort().forEach(region => {
        const group = regionGroups[region];
        
        // Region header
        const header = document.createElement('li');
        header.className = 'region-header';
        header.dataset.region = region;
        
        const counts = [];
        Object.keys(group.counts).forEach(type => {
            if (group.counts[type] > 0) {
                counts.push(`${group.counts[type]} ${typeLabels[type] || type}`);
            }
        });
        
        header.innerHTML = `
            <span class="region-name">${region}</span>
            <span class="region-count">${counts.join(', ')}</span>
        `;
        
        // Click on region header to zoom to region
        header.addEventListener('click', () => {
            selectRegion(region, group);
        });
        
        list.appendChild(header);
        
        // Group threats by type within region
        const typeGroups = {};
        group.threats.forEach(threat => {
            if (!typeGroups[threat.type]) {
                typeGroups[threat.type] = [];
            }
            typeGroups[threat.type].push(threat);
        });
        
        // Render type subgroups
        Object.keys(typeGroups).forEach(type => {
            const typeThreats = typeGroups[type];
            const typeLabel = typeLabels[type] || type;
            const totalCount = typeThreats.reduce((sum, t) => sum + t.count, 0);
            
            // Type header (collapsible)
            const typeHeader = document.createElement('li');
            typeHeader.className = `type-header ${type}`;
            typeHeader.dataset.type = type;
            typeHeader.dataset.region = region;
            typeHeader.innerHTML = `
                <span class="type-toggle"><i class="fa-solid fa-chevron-right"></i></span>
                <span class="type-name">${typeLabel}</span>
                <span class="type-count">${totalCount}</span>
            `;
            
            // Container for threats of this type
            const typeContainer = document.createElement('ul');
            typeContainer.className = 'type-threats collapsed';
            typeContainer.dataset.type = type;
            typeContainer.dataset.region = region;
            
            // Add individual threats
            typeThreats.forEach(threat => {
                const li = document.createElement('li');
                li.className = `threat-item ${threat.type}`;
                li.dataset.id = threat.id;
                
                const countLabel = threat.count > 1 ? ` (x${threat.count})` : '';
                
                li.innerHTML = `
                    <div class="threat-info">
                        <span class="threat-type">${typeLabel}${countLabel}</span>
                    </div>
                    <button class="delete-btn" onclick="deleteThreat(${threat.id})">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                `;
                
                li.addEventListener('click', (e) => {
                    if (!e.target.closest('.delete-btn')) {
                        selectThreat(threat.id);
                    }
                });
                
                typeContainer.appendChild(li);
            });
            
            // Toggle collapse on type header click
            typeHeader.addEventListener('click', (e) => {
                e.stopPropagation();
                typeContainer.classList.toggle('collapsed');
                typeHeader.classList.toggle('expanded');
            });
            
            list.appendChild(typeHeader);
            list.appendChild(typeContainer);
        });
    });
    
    // Update total count badge
    const totalEl = document.getElementById('total-count');
    if (totalEl) {
        const totalStr = Object.keys(totalCounts)
            .map(type => `${totalCounts[type]} ${typeLabels[type]}`)
            .join(', ') || '0';
        totalEl.textContent = totalStr;
    }
}

function deleteThreat(id) {
    threats = threats.filter(t => t.id !== id);
    
    // Remove marker and its trajectory line
    markersLayer.eachLayer(marker => {
        if (marker.threatId === id) {
            // Remove trajectory line
            if (marker.trajectoryLine) {
                trajectoriesLayer.removeLayer(marker.trajectoryLine);
            }
            markersLayer.removeLayer(marker);
        }
    });
    
    updateThreatList();
    updateOverlay();
    syncStateToServer();
}

function clearThreats() {
    threats = [];
    markersLayer.clearLayers();
    trajectoriesLayer.clearLayers();
    updateThreatList();
    updateOverlay();
    syncStateToServer();
}

function clearAll() {
    clearThreats();
}

// ==========================================
// Overlay (for screenshots)
// ==========================================

function updateOverlay() {
    const dateEl = document.getElementById('overlay-date');
    const countEl = document.getElementById('overlay-count');
    
    if (dateEl) {
        const now = new Date();
        const dateStr = now.toLocaleDateString('uk-UA', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
        const timeStr = now.toLocaleTimeString('uk-UA', {
            hour: '2-digit',
            minute: '2-digit'
        });
        dateEl.textContent = `${dateStr} ${timeStr}`;
    }
    
    if (countEl) {
        const droneCount = threats.reduce((sum, t) => t.type === 'drone' ? sum + t.count : sum, 0);
        countEl.textContent = `${droneCount} x БПЛА`;
    }
}

// ==========================================
// Server Sync
// ==========================================

async function syncStateToServer() {
    try {
        await fetch('/api/state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                threats: threats,
                alerts: []
            })
        });
    } catch (error) {
        console.error('Failed to sync state:', error);
    }
}

async function loadStateFromServer() {
    try {
        const response = await fetch('/api/state');
        const state = await response.json();
        
        threats = state.threats || [];
        
        // Render markers
        threats.forEach(threat => addMarker(threat));
        
        updateThreatList();
        updateOverlay();
    } catch (error) {
        console.error('Failed to load state:', error);
    }
}

// ==========================================
// Screenshot / Export
// ==========================================

async function exportMap() {
    const btn = document.querySelector('.action-btn.primary');
    const originalText = btn.innerHTML;
    
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Обробка...';
    btn.disabled = true;
    
    try {
        const response = await fetch('/api/screenshot', { method: 'POST' });
        const result = await response.json();
        
        if (result.status === 'success') {
            btn.innerHTML = '<i class="fa-solid fa-check"></i> Готово!';
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }, 2000);
        } else {
            throw new Error(result.message || 'Screenshot failed');
        }
    } catch (error) {
        console.error('Screenshot error:', error);
        btn.innerHTML = '<i class="fa-solid fa-xmark"></i> Помилка';
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }, 2000);
    }
}

// ==========================================
// Help Modal
// ==========================================

function openHelp() {
    document.getElementById('help-modal').style.display = 'flex';
}

function closeHelp() {
    document.getElementById('help-modal').style.display = 'none';
}

// Close modal on outside click
document.addEventListener('click', (e) => {
    const modal = document.getElementById('help-modal');
    if (e.target === modal) {
        closeHelp();
    }
});

// ==========================================
// AUTO Mode Functions
// ==========================================

function initWebSocket() {
    if (wsConnection) {
        wsConnection.close();
    }
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    console.log('[WS] Connecting to', wsUrl);
    wsConnection = new WebSocket(wsUrl);
    
    wsConnection.onopen = () => {
        console.log('[WS] Connected');
        if (wsReconnectTimer) {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = null;
        }
    };
    
    wsConnection.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWebSocketMessage(msg);
        } catch (e) {
            console.error('[WS] Failed to parse message:', e);
        }
    };
    
    wsConnection.onclose = () => {
        console.log('[WS] Disconnected, reconnecting in 3s...');
        wsReconnectTimer = setTimeout(initWebSocket, 3000);
    };
    
    wsConnection.onerror = (error) => {
        console.error('[WS] Error:', error);
    };
}

function handleWebSocketMessage(msg) {
    console.log('[WS] Message:', msg.type, msg.data);
    
    switch (msg.type) {
        case 'init':
            // Initial state from server
            if (msg.data.auto_mode !== undefined) {
                autoModeEnabled = msg.data.auto_mode;
                updateAutoModeUI();
            }
            break;
            
        case 'threat_add':
            // New threat from AUTO mode
            addAutoThreat(msg.data);
            break;
            
        case 'threat_remove':
            // Threat removed by AUTO mode
            removeAutoThreat(msg.data.id);
            break;
            
        case 'auto_status':
            // AUTO mode status update
            if (msg.data.status === 'running') {
                autoModeEnabled = true;
            } else if (msg.data.status === 'stopped') {
                autoModeEnabled = false;
            }
            updateAutoModeUI();
            break;
            
        case 'pong':
            // Heartbeat response
            break;
    }
}

function addAutoThreat(data) {
    // Check if threat already exists
    if (threats.find(t => t.id === data.id)) {
        return;
    }
    
    const threat = {
        id: data.id,
        type: data.type || 'drone',
        lat: data.lat,
        lng: data.lng,
        angle: data.angle || 0,
        count: data.count || 1,
        trajectoryLength: data.trajectoryLength || 80, // Use server value, default 80km
        isAuto: true // Mark as auto-generated
    };
    
    threats.push(threat);
    addMarker(threat);
    updateThreatList();
    updateOverlay();
    
    // Show notification
    showAutoNotification(`+ ${data.type === 'missile' ? 'Ракета' : 'БПЛА'} (${data.region || 'Невідомо'})`);
}

function removeAutoThreat(id) {
    const threat = threats.find(t => t.id === id);
    if (!threat) return;
    
    threats = threats.filter(t => t.id !== id);
    
    // Remove marker
    markersLayer.eachLayer(marker => {
        if (marker.threatId === id) {
            if (marker.trajectoryLine) {
                trajectoriesLayer.removeLayer(marker.trajectoryLine);
            }
            markersLayer.removeLayer(marker);
        }
    });
    
    updateThreatList();
    updateOverlay();
    
    // Show notification
    showAutoNotification(`− Ціль знищено`);
}

function showAutoNotification(text) {
    // Create notification element if not exists
    let notif = document.getElementById('auto-notification');
    if (!notif) {
        notif = document.createElement('div');
        notif.id = 'auto-notification';
        notif.className = 'auto-notification';
        document.body.appendChild(notif);
    }
    
    notif.textContent = text;
    notif.classList.add('show');
    
    setTimeout(() => {
        notif.classList.remove('show');
    }, 3000);
}

async function toggleAutoMode() {
    const btn = document.getElementById('auto-mode-btn');
    if (!btn) return;
    
    btn.disabled = true;
    
    try {
        if (autoModeEnabled) {
            // Stop AUTO mode
            const response = await fetch('/api/auto/stop', { method: 'POST' });
            const result = await response.json();
            
            if (result.status === 'stopped' || result.status === 'not_running') {
                autoModeEnabled = false;
            }
        } else {
            // Start AUTO mode
            const response = await fetch('/api/auto/start', { method: 'POST' });
            const result = await response.json();
            
            if (result.status === 'started' || result.status === 'already_running') {
                autoModeEnabled = true;
                showAutoNotification(`AUTO режим активовано (тест: ${result.test_mode ? 'так' : 'ні'})`);
            }
        }
    } catch (error) {
        console.error('Failed to toggle AUTO mode:', error);
        showAutoNotification('Помилка AUTO режиму');
    } finally {
        btn.disabled = false;
        updateAutoModeUI();
    }
}

async function checkAutoStatus() {
    try {
        const response = await fetch('/api/auto/status');
        const result = await response.json();
        
        autoModeEnabled = result.enabled || false;
        updateAutoModeUI();
    } catch (error) {
        console.error('Failed to check AUTO status:', error);
    }
}

function updateAutoModeUI() {
    const btn = document.getElementById('auto-mode-btn');
    const indicator = document.getElementById('auto-mode-indicator');
    
    if (btn) {
        if (autoModeEnabled) {
            btn.classList.add('active');
            btn.innerHTML = '<i class="fa-solid fa-robot"></i> AUTO: ON';
        } else {
            btn.classList.remove('active');
            btn.innerHTML = '<i class="fa-solid fa-robot"></i> AUTO: OFF';
        }
    }
    
    if (indicator) {
        indicator.style.display = autoModeEnabled ? 'flex' : 'none';
    }
}

// ==========================================
// Expose functions globally
// ==========================================
window.setTool = setTool;
window.deleteThreat = deleteThreat;
window.clearThreats = clearThreats;
window.clearAll = clearAll;
window.exportMap = exportMap;
window.openHelp = openHelp;
window.closeHelp = closeHelp;
window.toggleAutoMode = toggleAutoMode;

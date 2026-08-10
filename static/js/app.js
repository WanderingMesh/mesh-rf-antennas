/**
 * Frontend JavaScript for interactive coverage mapping
 */

class CoverageApp {
    constructor() {
        this.map = null;
        this.coverageLayers = [];
        this.nodeMarkers = [];
        this.currentCoverageId = null;
        this.isCalculating = false;
        this.siteColors = ['#0033cc', '#ff0000', '#00ff00', '#ff8800', '#ff00ff', '#00ffff', '#ffff00', '#8800ff'];
        this.currentColorIndex = 0;
        
        this.init();
    }
    
    init() {
        this.initMap();
        this.bindEvents();
        this.updateStatus('Ready - Click on map to place a site or upload CSV for multi-site analysis');
    }
    
    initMap() {
        // Guard against Leaflet's "Map container is already initialized" error,
        // which prevents bindEvents() from ever running and breaks all UI controls
        const container = L.DomUtil.get('map');
        if (container._leaflet_id) {
            container._leaflet_id = null;
        }

        this.map = L.map('map').setView([39.5296, -119.8138], 10);
        
        // Add tile layers
        const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 19
        });
        
        const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: '© Esri',
            maxZoom: 19
        });
        
        const terrainLayer = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenTopoMap',
            maxZoom: 17
        });
        
        // Add default layer
        osmLayer.addTo(this.map);
        
        // Add layer control
        const baseLayers = {
            "OpenStreetMap": osmLayer,
            "Satellite": satelliteLayer,
            "Terrain": terrainLayer
        };
        
        L.control.layers(baseLayers).addTo(this.map);
        
        // Signal-strength legend (bottom-right corner of the map).
        // The legend updates dynamically when coverage is rendered
        // to reflect the auto-scaled color range.
        this._legendControl = L.control({ position: 'bottomright' });
        this._legendControl.onAdd = () => {
            const div = L.DomUtil.create('div', 'signal-legend');
            div.id = 'signalLegend';
            div.innerHTML = '<h4>Signal Strength</h4>'
                + '<p class="legend-note">Run a calculation to see the color scale</p>';
            return div;
        };
        this._legendControl.addTo(this.map);
        
        // Add click handler for single site placement
        this.map.on('click', (e) => {
            if (!this.isCalculating) {
                this.placeSite(e.latlng);
            }
        });
    }
    
    bindEvents() {
        // Single site calculation
        document.getElementById('calculateSingle').addEventListener('click', () => {
            this.calculateSingleSite();
        });
        
        // Multi-site calculation
        document.getElementById('calculateMulti').addEventListener('click', () => {
            this.calculateMultiSite();
        });
        
        // Import layer button
        document.getElementById('importLayer').addEventListener('click', () => {
            this.importLayer();
        });
        
        // Clear map button
        document.getElementById('clearMap').addEventListener('click', () => {
            this.clearCoverageLayers();
            this.updateStatus('Map cleared');
        });
        
        // File upload
        document.getElementById('sitesFile').addEventListener('change', (e) => {
            this.handleFileUpload(e);
        });
        
        // Form validation
        this.addFormValidation();
        
        // Antenna type change handler
        document.getElementById('antennaType').addEventListener('change', (e) => {
            this.handleAntennaTypeChange(e.target.value);
        });
        
        // Azimuth slider sync
        const azimuthSlider = document.getElementById('antennaAzimuth');
        const azimuthInput = document.getElementById('antennaAzimuthValue');
        
        azimuthSlider.addEventListener('input', (e) => {
            azimuthInput.value = e.target.value;
            this.updateAzimuthDirection(e.target.value);
        });
        
        azimuthInput.addEventListener('input', (e) => {
            azimuthSlider.value = e.target.value;
            this.updateAzimuthDirection(e.target.value);
        });
        
        // Tilt slider sync — show tilt azimuth when tilt is non-zero
        const tiltSlider = document.getElementById('antennaTilt');
        const tiltInput = document.getElementById('antennaTiltValue');
        
        const updateTiltAzimuthVisibility = (tiltValue) => {
            const tiltAzimuthGroup = document.getElementById('tiltAzimuthGroup');
            tiltAzimuthGroup.style.display = parseFloat(tiltValue) !== 0 ? 'block' : 'none';
        };
        
        tiltSlider.addEventListener('input', (e) => {
            tiltInput.value = e.target.value;
            updateTiltAzimuthVisibility(e.target.value);
        });
        
        tiltInput.addEventListener('input', (e) => {
            tiltSlider.value = e.target.value;
            updateTiltAzimuthVisibility(e.target.value);
        });
        
        // Tilt azimuth slider sync (reuses the same compass direction helper)
        const tiltAzSlider = document.getElementById('tiltAzimuth');
        const tiltAzInput = document.getElementById('tiltAzimuthValue');
        
        tiltAzSlider.addEventListener('input', (e) => {
            tiltAzInput.value = e.target.value;
            this.updateTiltAzimuthDirection(e.target.value);
        });
        
        tiltAzInput.addEventListener('input', (e) => {
            tiltAzSlider.value = e.target.value;
            this.updateTiltAzimuthDirection(e.target.value);
        });
        
        // Reliability slider sync — display as percentage
        const fotSlider = document.getElementById('fractionOfTime');
        const fotDisplay = document.getElementById('fractionOfTimeValue');
        fotSlider.addEventListener('input', () => {
            fotDisplay.textContent = `${Math.round(parseFloat(fotSlider.value) * 100)}%`;
        });
        fotDisplay.textContent = `${Math.round(parseFloat(fotSlider.value) * 100)}%`;
        
        // Theme toggle
        document.getElementById('themeToggle').addEventListener('click', () => {
            this.toggleTheme();
        });
        this.applyStoredTheme();
        
        // Initialize gain field with default antenna type's gain
        const initialAntennaType = document.getElementById('antennaType').value;
        this.handleAntennaTypeChange(initialAntennaType);
    }
    
    addFormValidation() {
        const inputs = document.querySelectorAll('input[type="number"]');
        inputs.forEach(input => {
            input.addEventListener('input', () => {
                this.validateInput(input);
            });
        });
    }
    
    validateInput(input) {
        const value = parseFloat(input.value);
        const min = parseFloat(input.min);
        const max = parseFloat(input.max);
        
        if (isNaN(value) || value < min || value > max) {
            input.style.borderColor = 'var(--validation-bad-border)';
            input.style.backgroundColor = 'var(--validation-bad-bg)';
        } else {
            input.style.borderColor = '';
            input.style.backgroundColor = '';
        }
    }
    
    handleAntennaTypeChange(antennaType) {
        const azimuthGroup = document.getElementById('azimuthGroup');
        const antennaGainInput = document.getElementById('antennaGain');
        const gainIndicator = document.getElementById('gainAutoFillIndicator');
        
        // Show azimuth controls only for directional antennas
        if (antennaType !== 'omnidirectional') {
            azimuthGroup.style.display = 'block';
        } else {
            azimuthGroup.style.display = 'none';
        }
        
        // Auto-fill typical gain based on antenna type
        const typicalGains = {
            'omnidirectional': 0.0,
            'yagi_3el': 7.0,
            'yagi_5el': 10.0,
            'yagi_11el': 13.0
        };
        
        if (antennaType in typicalGains) {
            const typicalGain = typicalGains[antennaType];
            antennaGainInput.value = typicalGain;
            gainIndicator.textContent = `(auto-filled: ${typicalGain} dBi)`;
            gainIndicator.style.color = '#28a745'; // Green to indicate auto-fill
            
            // Clear indicator after a short delay to show it was auto-filled
            setTimeout(() => {
                gainIndicator.textContent = '';
            }, 2000);
        }
    }
    
    updateAzimuthDirection(azimuth) {
        const directionSpan = document.getElementById('azimuthDirection');
        const angle = parseFloat(azimuth);
        
        const directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 
                           'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
        const index = Math.round(angle / 22.5) % 16;
        directionSpan.textContent = directions[index];
    }
    
    updateTiltAzimuthDirection(azimuth) {
        const directionSpan = document.getElementById('tiltAzimuthDirection');
        const angle = parseFloat(azimuth);
        
        const directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 
                           'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];
        const index = Math.round(angle / 22.5) % 16;
        directionSpan.textContent = directions[index];
    }
    
    placeSite(latlng) {
        // Update form with clicked coordinates
        document.getElementById('siteLat').value = latlng.lat.toFixed(6);
        document.getElementById('siteLon').value = latlng.lng.toFixed(6);
        
        // Add temporary marker
        this.clearTemporaryMarkers();
        const marker = L.marker(latlng, {
            icon: L.divIcon({
                className: 'node-marker',
                html: '<div style="background: #ff6b6b; border: 2px solid white; border-radius: 50%; width: 12px; height: 12px;"></div>',
                iconSize: [12, 12]
            })
        }).addTo(this.map);
        
        marker.bindPopup(`
            <h3>Site Location</h3>
            <p><strong>Latitude:</strong> ${latlng.lat.toFixed(6)}</p>
            <p><strong>Longitude:</strong> ${latlng.lng.toFixed(6)}</p>
            <p>Enter site details and click "Calculate Single Site"</p>
        `).openPopup();
        
        this.temporaryMarker = marker;
    }
    
    clearTemporaryMarkers() {
        if (this.temporaryMarker) {
            this.map.removeLayer(this.temporaryMarker);
            this.temporaryMarker = null;
        }
    }
    
    async pollForCoverageResults(coverageId) {
        /**
         * Poll the server for coverage calculation progress and results.
         * Shows real-time progress updates.
         */
        const maxAttempts = 120; // 2 minutes max (120 * 1 second)
        let attempts = 0;
        
        while (attempts < maxAttempts) {
            try {
                // Fetch status
                const statusResponse = await fetch(`/api/coverage/${coverageId}/status`);
                if (!statusResponse.ok) {
                    throw new Error('Failed to fetch status');
                }
                
                const status = await statusResponse.json();
                
                // Update progress display
                if (status.progress !== undefined) {
                    this.updateProgress(status.progress, status.progress_message || 'Processing...');
                }
                
                // Check if complete
                if (status.status === 'complete') {
                    // Fetch full coverage data
                    const coverageResponse = await fetch(`/api/coverage/${coverageId}`);
                    if (!coverageResponse.ok) {
                        throw new Error('Failed to fetch coverage data');
                    }
                    
                    const coverageData = await coverageResponse.json();
                    
                    console.log('Received coverage data, keys:', Object.keys(coverageData));
                    console.log('Has coverage_mask:', !!coverageData.coverage_mask);
                    console.log('Has dem_bounds:', !!coverageData.dem_bounds);
                    
                    // Display results
                    this.displayResults({ coverage_id: coverageId, statistics: coverageData.statistics });
                    await this.addCoverageToMap(coverageData, coverageId);
                    
                    this.showSuccess('Coverage calculated successfully!');
                    return;
                }
                
                // Check if error
                if (status.status === 'error') {
                    throw new Error(status.error || 'Calculation failed');
                }
                
                // Wait before next poll
                await new Promise(resolve => setTimeout(resolve, 1000));
                attempts++;
                
            } catch (error) {
                console.error('Polling error:', error);
                throw error;
            }
        }
        
        throw new Error('Calculation timed out after 2 minutes');
    }
    
    updateProgress(percent, message) {
        /**
         * Update the progress bar and message.
         */
        const loadingIndicator = document.getElementById('loadingIndicator');
        
        // Clear existing content and rebuild
        let progressContainer = loadingIndicator.querySelector('.progress-container');
        if (!progressContainer) {
            // Clear the loading indicator
            loadingIndicator.innerHTML = '';
            
            // Create progress container
            progressContainer = document.createElement('div');
            progressContainer.className = 'progress-container';
            progressContainer.innerHTML = `
                <div class="progress-header">
                    <i class="fas fa-satellite-dish"></i>
                    <span>Calculating Coverage</span>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar"></div>
                </div>
                <div class="progress-text"></div>
            `;
            loadingIndicator.appendChild(progressContainer);
        }
        
        // Update progress bar width
        const progressBar = loadingIndicator.querySelector('.progress-bar');
        if (progressBar) {
            progressBar.style.width = `${percent}%`;
        }
        
        // Update progress text
        const progressText = loadingIndicator.querySelector('.progress-text');
        if (progressText) {
            progressText.textContent = `${Math.round(percent)}% - ${message}`;
        }
        
        this.updateStatus(message);
    }
    
    async calculateSingleSite() {
        if (this.isCalculating) return;
        
        const siteName = document.getElementById('siteName').value.trim();
        const lat = parseFloat(document.getElementById('siteLat').value);
        const lon = parseFloat(document.getElementById('siteLon').value);
        const elev = parseFloat(document.getElementById('siteElev').value);
        
        // Validation
        if (!siteName || isNaN(lat) || isNaN(lon) || isNaN(elev)) {
            this.showError('Please fill in all site details');
            return;
        }
        
        if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
            this.showError('Invalid coordinates');
            return;
        }
        
        this.isCalculating = true;
        this.showLoading(true);
        this.updateStatus('Calculating single site coverage...');
        
        try {
            const request = {
                site_name: siteName,
                lat: lat,
                lon: lon,
                elev_m: elev,
                frequency_mhz: parseFloat(document.getElementById('frequency').value),
                tx_power_dbm: parseFloat(document.getElementById('txPower').value),
                antenna_gain_dbi: parseFloat(document.getElementById('antennaGain').value),
                antenna_type: document.getElementById('antennaType').value,
                antenna_azimuth: parseFloat(document.getElementById('antennaAzimuthValue').value),
                antenna_tilt: parseFloat(document.getElementById('antennaTiltValue').value),
                antenna_tilt_azimuth: parseFloat(document.getElementById('tiltAzimuthValue').value),
                rx_sensitivity_dbm: parseFloat(document.getElementById('rxSensitivity').value),
                analysis_radius_km: parseFloat(document.getElementById('analysisRadius').value),
                climate_zone: document.getElementById('climateZone').value,
                ground_type: document.getElementById('groundType').value,
                fraction_of_time: parseFloat(document.getElementById('fractionOfTime').value)
            };
            
            const response = await fetch('/api/coverage/single', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(request)
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Calculation failed');
            }
            
            const result = await response.json();
            this.currentCoverageId = result.coverage_id;
            
            // Poll for progress and results
            await this.pollForCoverageResults(result.coverage_id)
            
        } catch (error) {
            this.showError(`Error: ${error.message}`);
        } finally {
            this.isCalculating = false;
            this.showLoading(false);
        }
    }
    
    async calculateMultiSite() {
        if (this.isCalculating) return;
        
        const fileInput = document.getElementById('sitesFile');
        if (!fileInput.files[0]) {
            this.showError('Please upload a CSV file with sites data');
            return;
        }
        
        this.isCalculating = true;
        this.showLoading(true);
        this.updateStatus('Calculating multi-site coverage...');
        
        try {
            // First upload the file
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            
            const uploadResponse = await fetch('/api/coverage/upload', {
                method: 'POST',
                body: formData
            });
            
            if (!uploadResponse.ok) {
                const error = await uploadResponse.json();
                throw new Error(error.detail || 'File upload failed');
            }
            
            const uploadResult = await uploadResponse.json();
            
            // Then calculate coverage
            const request = {
                sites: uploadResult.sites,
                show_nodes: document.getElementById('showNodes').checked,
                frequency_mhz: parseFloat(document.getElementById('frequency').value),
                tx_power_dbm: parseFloat(document.getElementById('txPower').value),
                antenna_gain_dbi: parseFloat(document.getElementById('antennaGain').value),
                antenna_type: document.getElementById('antennaType').value,
                antenna_azimuth: parseFloat(document.getElementById('antennaAzimuthValue').value),
                antenna_tilt: parseFloat(document.getElementById('antennaTiltValue').value),
                antenna_tilt_azimuth: parseFloat(document.getElementById('tiltAzimuthValue').value),
                rx_sensitivity_dbm: parseFloat(document.getElementById('rxSensitivity').value),
                analysis_radius_km: parseFloat(document.getElementById('analysisRadius').value),
                climate_zone: document.getElementById('climateZone').value,
                ground_type: document.getElementById('groundType').value,
                fraction_of_time: parseFloat(document.getElementById('fractionOfTime').value)
            };
            
            const response = await fetch('/api/coverage/multi', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(request)
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Calculation failed');
            }
            
            const result = await response.json();
            this.currentCoverageId = result.coverage_id;
            
            // Fetch full coverage data for visualization
            const coverageResponse = await fetch(`/api/coverage/${result.coverage_id}`);
            if (!coverageResponse.ok) {
                throw new Error('Failed to fetch coverage data');
            }
            
            const coverageData = await coverageResponse.json();
            
            // Display results with coverage data
            this.displayResults(result);
            await this.addCoverageToMap(coverageData);
            
            // Show success message
            this.showSuccess(`Multi-site coverage calculated successfully for ${uploadResult.sites.length} sites`)
            
        } catch (error) {
            this.showError(`Error: ${error.message}`);
        } finally {
            this.isCalculating = false;
            this.showLoading(false);
        }
    }
    
    async importLayer() {
        const fileInput = document.getElementById('importFile');
        if (!fileInput.files[0]) {
            this.showError('Please select a KMZ or GeoTIFF file to import');
            return;
        }
        
        this.showLoading(true);
        this.updateStatus('Importing coverage layer...');
        
        try {
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            
            const response = await fetch('/api/coverage/import', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Import failed');
            }
            
            const coverageData = await response.json();
            const coverageId = coverageData.coverage_id;
            
            await this.addCoverageToMap(coverageData, coverageId);
            
            const siteName = coverageData.site_name || 'Imported';
            this.showSuccess(`Imported coverage layer: ${siteName}`);
            
            // Reset the file input so the same file can be re-imported
            fileInput.value = '';
            
        } catch (error) {
            this.showError(`Import error: ${error.message}`);
        } finally {
            this.showLoading(false);
        }
    }
    
    async handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        if (!file.name.toLowerCase().endsWith('.csv')) {
            this.showError('Please upload a CSV file');
            return;
        }
        
        // Update file input label
        const label = event.target.nextElementSibling;
        if (label) {
            label.textContent = `Selected: ${file.name}`;
            label.classList.add('has-file');
        }
    }
    
    displayResults(result) {
        const resultsPanel = document.getElementById('resultsPanel');
        
        if (result.statistics) {
            const stats = result.statistics;
            resultsPanel.innerHTML = `
                <h4>Coverage Results</h4>
                <div class="stat-item">
                    <span class="stat-label">Coverage Area:</span>
                    <span class="stat-value">${stats.coverage_area_km2?.toFixed(1) || stats.total_coverage_area_km2?.toFixed(1) || 'N/A'} km²</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Coverage Pixels:</span>
                    <span class="stat-value">${stats.coverage_pixels?.toLocaleString() || 'N/A'}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Coverage %:</span>
                    <span class="stat-value">${stats.coverage_percentage?.toFixed(1) || 'N/A'}%</span>
                </div>
                ${stats.number_of_sites ? `
                <div class="stat-item">
                    <span class="stat-label">Number of Sites:</span>
                    <span class="stat-value">${stats.number_of_sites}</span>
                </div>
                ` : ''}
                <div class="stat-item">
                    <span class="stat-label">Min Signal:</span>
                    <span class="stat-value">${stats.min_signal_dbm?.toFixed(1) || 'N/A'} dBm</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">Max Signal:</span>
                    <span class="stat-value">${stats.max_signal_dbm?.toFixed(1) || 'N/A'} dBm</span>
                </div>
            `;
        } else {
            resultsPanel.innerHTML = '<p>No statistics available</p>';
        }
    }
    
    async addCoverageToMap(coverageData, coverageId = null) {
        if (coverageData.coverage_mask) {
            this.addSingleSiteCoverage(coverageData, coverageId);
        } else if (coverageData.site_coverage_data) {
            this.addMultiSiteCoverage(coverageData);
        }
    }
    
    // Continuous heat-map gradient stops (strongest → weakest).
    // We interpolate linearly between these stops so the full color
    // range stretches across whatever signal range exists in the data,
    // making directional patterns clearly visible even when all signals
    // fall within a narrow dBm window.
    static get GRADIENT_STOPS() {
        return [
            // t (0=strongest, 1=weakest), R, G, B
            [0.00, 255,   0,   0],   // red       – strongest
            [0.15, 255, 165,   0],   // orange
            [0.30, 255, 255,   0],   // yellow
            [0.45,   0, 255,   0],   // green
            [0.60,   0, 196, 196],   // cyan
            [0.75,   0, 100, 255],   // blue
            [0.90, 142,  63, 255],   // purple
            [1.00, 196,  54, 255],   // magenta   – weakest
        ];
    }

    // Linearly interpolate within the gradient for a normalised t in [0,1].
    // t=0 is strongest signal, t=1 is weakest.
    static lerpGradient(t) {
        const stops = CoverageApp.GRADIENT_STOPS;
        if (t <= 0) return [stops[0][1], stops[0][2], stops[0][3]];
        if (t >= 1) {
            const last = stops[stops.length - 1];
            return [last[1], last[2], last[3]];
        }
        for (let i = 1; i < stops.length; i++) {
            if (t <= stops[i][0]) {
                const [t0, r0, g0, b0] = stops[i - 1];
                const [t1, r1, g1, b1] = stops[i];
                const f = (t - t0) / (t1 - t0);
                return [
                    Math.round(r0 + (r1 - r0) * f),
                    Math.round(g0 + (g1 - g0) * f),
                    Math.round(b0 + (b1 - b0) * f),
                ];
            }
        }
        const last = stops[stops.length - 1];
        return [last[1], last[2], last[3]];
    }

    addSingleSiteCoverage(coverageData, coverageId = null) {
        const coverageMask = coverageData.coverage_mask;
        const signalStrength = coverageData.signal_strength;
        const demBounds = coverageData.dem_bounds; // [west, south, east, north]
        const txLat = coverageData.tx_lat;
        const txLon = coverageData.tx_lon;
        
        console.log('addSingleSiteCoverage called');
        console.log('TX coordinates from backend:', txLat, txLon);
        console.log('Coverage mask:', coverageMask ? `${coverageMask.length}x${coverageMask[0]?.length}` : 'null');
        console.log('DEM bounds [W,S,E,N]:', demBounds);
        
        const [west, south, east, north] = demBounds;
        console.log('TX within bounds?', 
            `Lat ${txLat} in [${south}, ${north}]:`, txLat >= south && txLat <= north,
            `Lon ${txLon} in [${west}, ${east}]:`, txLon >= west && txLon <= east);
        
        if (!coverageMask || !demBounds) {
            console.error('Missing coverage data or bounds');
            return;
        }
        
        // Create canvas to render coverage with signal-strength heat map
        const height = coverageMask.length;
        const width = coverageMask[0].length;
        console.log(`Creating canvas: ${width}x${height}`);
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        const imageData = ctx.createImageData(width, height);
        
        // First pass: collect all signal values so we can compute
        // percentile-based bounds.  Using raw min/max produces a huge
        // range (e.g. 0 to -150 dBm) because of a few extreme pixels
        // very close to the TX and at the fringe.  That compresses the
        // useful directional differences into a tiny color slice.
        // Percentile clipping (2nd–98th) focuses the gradient on the
        // bulk of the data where directional patterns live.
        const allSignals = [];
        for (let row = 0; row < height; row++) {
            for (let col = 0; col < width; col++) {
                if (coverageMask[row][col]) {
                    allSignals.push(signalStrength[row][col]);
                }
            }
        }
        allSignals.sort((a, b) => a - b);
        const n = allSignals.length;
        let sigMin, sigMax;
        if (n === 0) {
            sigMin = -120; sigMax = -60;
        } else {
            sigMin = allSignals[Math.floor(n * 0.02)];
            sigMax = allSignals[Math.min(n - 1, Math.floor(n * 0.98))];
        }
        if (sigMax - sigMin < 5) sigMax = sigMin + 5;
        const sigRange = sigMax - sigMin;
        console.log(`Signal range (p2–p98): ${sigMax.toFixed(0)} to ${sigMin.toFixed(0)} dBm (${sigRange.toFixed(0)} dB span, ${n} pixels)`);
        
        // Store the range for the legend
        this._lastSigMin = sigMin;
        this._lastSigMax = sigMax;
        
        // Second pass: render each covered pixel using the continuous
        // gradient stretched across [sigMin, sigMax].
        const alpha = 200;
        let coveragePixelCount = 0;
        for (let row = 0; row < height; row++) {
            for (let col = 0; col < width; col++) {
                const idx = (row * width + col) * 4;
                
                if (coverageMask[row][col]) {
                    coveragePixelCount++;
                    const signal = signalStrength[row][col];
                    // Clamp to [sigMin, sigMax] so outliers beyond the
                    // percentile bounds saturate at the gradient endpoints
                    // instead of producing out-of-range t values.
                    const clamped = Math.max(sigMin, Math.min(sigMax, signal));
                    const t = 1.0 - (clamped - sigMin) / sigRange;
                    const [r, g, b] = CoverageApp.lerpGradient(t);
                    imageData.data[idx] = r;
                    imageData.data[idx + 1] = g;
                    imageData.data[idx + 2] = b;
                    imageData.data[idx + 3] = alpha;
                } else {
                    imageData.data[idx + 3] = 0;
                }
            }
        }
        
        ctx.putImageData(imageData, 0, 0);
        console.log(`Canvas rendered with ${coveragePixelCount} coverage pixels out of ${width * height} total`);
        console.log('Creating image overlay');
        
        // Add image overlay to map
        // DEM bounds are larger than actual coverage due to terrain data padding
        // Use DEM bounds as-is since the coverage mask already matches the DEM area
        // demBounds format: [west, south, east, north]
        const bounds = [[demBounds[1], demBounds[0]], [demBounds[3], demBounds[2]]];
        console.log('Leaflet bounds [[S,W],[N,E]]:', bounds);
        
        const imageOverlay = L.imageOverlay(canvas.toDataURL(), bounds, {
            opacity: 0.7,
            interactive: false
        }).addTo(this.map);
        
        console.log('Image overlay added to map');
        
        // Store layer with metadata
        const layerInfo = {
            layer: imageOverlay,
            siteName: coverageData.site_name || 'Unknown Site',
            coverageId: coverageId,
            color: null,  // signal-strength heat map, no single site color
            visible: true
        };
        this.coverageLayers.push(layerInfo);
        this.currentColorIndex++;
        
        // Update layer control panel and signal legend
        this.updateLayerControl();
        this.updateSignalLegend();
        
        // Fit map to coverage bounds
        this.map.fitBounds(bounds, { padding: [50, 50] });
        
        // Add transmitter marker
        console.log('Creating marker at:', [txLat, txLon]);
        const txMarker = L.marker([txLat, txLon], {
            icon: L.divIcon({
                className: 'node-marker',
                html: '<div style="background: #ff0000; border: 3px solid white; border-radius: 50%; width: 16px; height: 16px; box-shadow: 0 0 10px rgba(255,0,0,0.5);"></div>',
                iconSize: [16, 16]
            })
        }).addTo(this.map);
        console.log('Marker added at LatLng:', txMarker.getLatLng());
        
        // Get antenna info from coverage data
        const antennaType = coverageData.antenna_type || 'omnidirectional';
        const antennaAzimuth = coverageData.antenna_azimuth || 0;
        const antennaTilt = coverageData.antenna_tilt || 0;
        const antennaTiltAzimuth = coverageData.antenna_tilt_azimuth || 0;
        
        // Add directional indicator for directional antennas
        if (antennaType !== 'omnidirectional') {
            this.addDirectionalIndicator(txLat, txLon, antennaAzimuth, antennaType);
        }
        
        txMarker.bindPopup(`
            <h3>${coverageData.site_name || 'Transmitter'}</h3>
            <p><strong>Latitude:</strong> ${txLat.toFixed(6)}</p>
            <p><strong>Longitude:</strong> ${txLon.toFixed(6)}</p>
            <p><strong>Elevation:</strong> ${coverageData.tx_elev_m} m</p>
            <p><strong>Frequency:</strong> ${coverageData.frequency_mhz} MHz</p>
            <p><strong>Power:</strong> ${coverageData.tx_power_dbm} dBm</p>
            <p><strong>Antenna:</strong> ${this.getAntennaDescription(antennaType)}</p>
            ${antennaType !== 'omnidirectional' ? `<p><strong>Azimuth:</strong> ${antennaAzimuth}°</p>` : ''}
            ${antennaTilt !== 0 ? `<p><strong>Tilt:</strong> ${antennaTilt}° (${antennaTilt > 0 ? 'down' : 'up'}) toward ${antennaTiltAzimuth}°</p>` : ''}
        `);
        
        this.nodeMarkers.push(txMarker);
    }
    
    addMultiSiteCoverage(coverageData) {
        // Add coverage for each site
        if (coverageData.site_coverage_data) {
            Object.values(coverageData.site_coverage_data).forEach(siteData => {
                this.addSingleSiteCoverage(siteData);
            });
        }
        
        // Add node locations if requested
        if (coverageData.show_nodes && coverageData.node_locations) {
            coverageData.node_locations.forEach(node => {
                const marker = L.marker([node.lat, node.lon], {
                    icon: L.divIcon({
                        className: 'node-marker',
                        html: '<div style="background: #4CAF50; border: 2px solid white; border-radius: 50%; width: 10px; height: 10px;"></div>',
                        iconSize: [10, 10]
                    })
                }).addTo(this.map);
                
                marker.bindPopup(`
                    <h3>${node.name}</h3>
                    <p><strong>Latitude:</strong> ${node.lat.toFixed(6)}</p>
                    <p><strong>Longitude:</strong> ${node.lon.toFixed(6)}</p>
                    <p><strong>Elevation:</strong> ${node.elev} m</p>
                `);
                
                this.nodeMarkers.push(marker);
            });
        }
    }
    
    addDirectionalIndicator(lat, lon, azimuth, antennaType) {
        // Get beamwidth based on antenna type
        const beamwidths = {
            'yagi_3el': 60,
            'yagi_5el': 40,
            'yagi_11el': 30
        };
        const beamwidth = beamwidths[antennaType] || 60;
        
        // Calculate endpoints for the directional indicator
        // Draw a wedge/sector showing the main lobe
        const distance = 0.05;  // degrees (roughly 5km at mid-latitudes)
        
        // Convert azimuth to radians (0° = North, clockwise)
        // For geographic coordinates: lat increases northward, lon increases eastward
        const azimuthRad = azimuth * Math.PI / 180;
        const halfBeamRad = (beamwidth / 2) * Math.PI / 180;
        
        // Calculate sector points
        const points = [[lat, lon]];  // Start at transmitter
        
        // Add arc points for the sector
        for (let angle = azimuthRad - halfBeamRad; angle <= azimuthRad + halfBeamRad; angle += Math.PI / 36) {
            // For azimuth: 0° = North, 90° = East, 180° = South, 270° = West
            // lat changes with cos(azimuth), lon changes with sin(azimuth)
            const pointLat = lat + distance * Math.cos(angle);
            const pointLon = lon + distance * Math.sin(angle);
            points.push([pointLat, pointLon]);
        }
        
        points.push([lat, lon]);  // Close the sector
        
        // Create polygon for the sector
        const sector = L.polygon(points, {
            color: '#ff0000',
            fillColor: '#ff0000',
            fillOpacity: 0.2,
            weight: 2,
            dashArray: '5, 5'
        }).addTo(this.map);
        
        // Add center line showing exact pointing direction
        const centerLat = lat + distance * Math.cos(azimuthRad);
        const centerLon = lon + distance * Math.sin(azimuthRad);
        const centerLine = L.polyline([[lat, lon], [centerLat, centerLon]], {
            color: '#ff0000',
            weight: 3,
            opacity: 0.8
        }).addTo(this.map);
        
        // Add arrowhead at the end
        const arrow = L.marker([centerLat, centerLon], {
            icon: L.divIcon({
                className: 'direction-arrow',
                html: `<div style="color: #ff0000; font-size: 24px; transform: rotate(${azimuth}deg);">▲</div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            })
        }).addTo(this.map);
        
        // Store these for cleanup
        this.nodeMarkers.push(sector, centerLine, arrow);
    }
    
    getAntennaDescription(antennaType) {
        const descriptions = {
            'omnidirectional': 'Omnidirectional (0 dBi)',
            'yagi_3el': '3-Element Yagi (7 dBi)',
            'yagi_5el': '5-Element Yagi (10 dBi)',
            'yagi_11el': '11-Element Yagi (13 dBi)'
        };
        return descriptions[antennaType] || antennaType;
    }
    
    clearCoverageLayers() {
        this.coverageLayers.forEach(layerInfo => this.map.removeLayer(layerInfo.layer));
        this.nodeMarkers.forEach(marker => this.map.removeLayer(marker));
        this.coverageLayers = [];
        this.nodeMarkers = [];
        this.currentColorIndex = 0;
        this._lastSigMin = null;
        this._lastSigMax = null;
        this.updateLayerControl();
        const legend = document.getElementById('signalLegend');
        if (legend) {
            legend.innerHTML = '<h4>Signal Strength</h4>'
                + '<p class="legend-note">Run a calculation to see the color scale</p>';
        }
    }
    
    hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : {r: 0, g: 51, b: 204};
    }
    
    updateLayerControl() {
        let panel = document.getElementById('layerControlPanel');
        if (!panel) {
            const controlPanel = document.querySelector('.control-panel');
            panel = document.createElement('div');
            panel.id = 'layerControlPanel';
            panel.className = 'panel-section';
            panel.innerHTML = '<h3><i class="fas fa-layer-group"></i> Coverage Layers</h3><div id="layerList"></div>';
            controlPanel.appendChild(panel);
        }
        
        const layerList = document.getElementById('layerList');
        layerList.innerHTML = '';
        
        this.coverageLayers.forEach((layerInfo, index) => {
            const layerItem = document.createElement('div');
            layerItem.className = 'layer-item';
            
            // Export buttons are only shown when we have a coverageId to reference
            const exportButtons = layerInfo.coverageId ? `
                <div style="display: flex; gap: 4px; margin-left: auto;">
                    <button class="export-btn" data-id="${layerInfo.coverageId}" data-format="kmz" title="Export as KMZ (Google Earth)">KMZ</button>
                    <button class="export-btn" data-id="${layerInfo.coverageId}" data-format="geotiff" title="Export as GeoTIFF (GIS)">TIF</button>
                </div>
            ` : '';
            
            // Heat-map layers get a gradient swatch; legacy flat-color layers get a solid swatch
            const swatchStyle = layerInfo.color
                ? `background-color: ${layerInfo.color};`
                : `background: linear-gradient(to right, rgb(255,0,0), rgb(255,255,0), rgb(0,255,0), rgb(0,148,255), rgb(142,63,255));`;

            layerItem.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px; width: 100%;">
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; flex: 1; min-width: 0;">
                        <input type="checkbox" id="layer-${index}" ${layerInfo.visible ? 'checked' : ''}>
                        <span style="width: 24px; height: 14px; flex-shrink: 0; ${swatchStyle} border: 1px solid #ccc; border-radius: 3px;"></span>
                        <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${layerInfo.siteName}</span>
                    </label>
                    ${exportButtons}
                </div>
            `;
            
            const checkbox = layerItem.querySelector('input[type="checkbox"]');
            checkbox.addEventListener('change', (e) => {
                this.toggleLayerVisibility(index, e.target.checked);
            });
            
            // Wire up export buttons
            layerItem.querySelectorAll('.export-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    const covId = btn.dataset.id;
                    const fmt = btn.dataset.format;
                    this.exportLayer(covId, fmt);
                });
            });
            
            layerList.appendChild(layerItem);
        });
    }
    
    updateSignalLegend() {
        const div = document.getElementById('signalLegend');
        if (!div) return;

        const min = this._lastSigMin;
        const max = this._lastSigMax;
        if (min == null || max == null) return;

        // Build 7 evenly-spaced legend entries across the data range
        const numSteps = 7;
        let html = '<h4>Signal Strength (dBm)</h4><div class="legend-scale">';
        for (let i = 0; i < numSteps; i++) {
            const t = i / (numSteps - 1);              // 0 → 1
            const dbm = max - t * (max - min);          // strongest → weakest
            const [r, g, b] = CoverageApp.lerpGradient(t);
            const label = i === 0 ? `${Math.round(dbm)} (strongest)`
                        : i === numSteps - 1 ? `${Math.round(dbm)} (weakest)`
                        : `${Math.round(dbm)}`;
            html += `<div class="legend-item">`
                + `<span class="legend-color" style="background:rgb(${r},${g},${b});"></span>`
                + `<span class="legend-label">${label} dBm</span></div>`;
        }
        html += '</div>';
        html += '<p class="legend-note">Colors auto-scaled to data range</p>';
        div.innerHTML = html;
    }

    exportLayer(coverageId, format) {
        const url = `/api/coverage/${coverageId}/export/${format}`;
        // Trigger a browser download by navigating to the endpoint
        const link = document.createElement('a');
        link.href = url;
        link.download = '';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
    
    toggleLayerVisibility(index, visible) {
        if (index < 0 || index >= this.coverageLayers.length) return;
        
        const layerInfo = this.coverageLayers[index];
        layerInfo.visible = visible;
        
        if (visible) {
            if (!this.map.hasLayer(layerInfo.layer)) {
                this.map.addLayer(layerInfo.layer);
            }
        } else {
            if (this.map.hasLayer(layerInfo.layer)) {
                this.map.removeLayer(layerInfo.layer);
            }
        }
    }
    
    showLoading(show) {
        const loadingIndicator = document.getElementById('loadingIndicator');
        if (show) {
            loadingIndicator.style.display = 'flex';
            // Set initial spinner content (will be replaced by progress bar)
            loadingIndicator.innerHTML = `
                <div class="spinner"></div>
                <p>Initializing...</p>
            `;
        } else {
            loadingIndicator.style.display = 'none';
            loadingIndicator.innerHTML = '';
        }
    }
    
    updateStatus(message) {
        document.getElementById('statusText').textContent = message;
        document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
    }
    
    showError(message) {
        this.updateStatus(`Error: ${message}`);
        // You could add a toast notification here
        console.error(message);
    }
    
    showSuccess(message) {
        this.updateStatus(message);
        // You could add a toast notification here
        console.log(message);
    }
    
    applyStoredTheme() {
        const stored = localStorage.getItem('rf-theme') || 'light';
        document.documentElement.setAttribute('data-theme', stored);
        this.updateThemeIcon(stored);
    }
    
    toggleTheme() {
        const current = document.documentElement.getAttribute('data-theme') || 'light';
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('rf-theme', next);
        this.updateThemeIcon(next);
    }
    
    updateThemeIcon(theme) {
        const icon = document.getElementById('themeIcon');
        if (!icon) return;
        icon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
    }
}

// Initialize the application when the page loads

document.addEventListener('DOMContentLoaded', () => {
    new CoverageApp();
});

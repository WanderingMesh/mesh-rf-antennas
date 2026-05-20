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
            input.style.borderColor = '#c62828';
            input.style.backgroundColor = '#ffebee';
        } else {
            input.style.borderColor = '#ddd';
            input.style.backgroundColor = 'white';
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
                    await this.addCoverageToMap(coverageData);
                    
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
                antenna_gain_dbi: parseFloat(document.getElementById('antennaGain').value),  // Read from gain field (auto-filled or custom)
                antenna_type: document.getElementById('antennaType').value,
                antenna_azimuth: parseFloat(document.getElementById('antennaAzimuthValue').value),
                antenna_tilt: parseFloat(document.getElementById('antennaTiltValue').value),
                antenna_tilt_azimuth: parseFloat(document.getElementById('tiltAzimuthValue').value),
                rx_sensitivity_dbm: parseFloat(document.getElementById('rxSensitivity').value),
                analysis_radius_km: parseFloat(document.getElementById('analysisRadius').value),
                climate_zone: document.getElementById('climateZone').value
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
                antenna_gain_dbi: parseFloat(document.getElementById('antennaGain').value),  // Read from gain field (auto-filled or custom)
                antenna_type: document.getElementById('antennaType').value,
                antenna_azimuth: parseFloat(document.getElementById('antennaAzimuthValue').value),
                antenna_tilt: parseFloat(document.getElementById('antennaTiltValue').value),
                antenna_tilt_azimuth: parseFloat(document.getElementById('tiltAzimuthValue').value),
                rx_sensitivity_dbm: parseFloat(document.getElementById('rxSensitivity').value),
                analysis_radius_km: parseFloat(document.getElementById('analysisRadius').value),
                climate_zone: document.getElementById('climateZone').value
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
    
    async addCoverageToMap(coverageData) {
        // Don't clear - allow accumulation of multiple sites
        // Users can manually clear using the "Clear All Coverage" button
        
        if (coverageData.coverage_mask) {
            // Single site coverage
            this.addSingleSiteCoverage(coverageData);
        } else if (coverageData.site_coverage_data) {
            // Multi-site coverage
            this.addMultiSiteCoverage(coverageData);
        }
    }
    
    addSingleSiteCoverage(coverageData) {
        // Render actual coverage mask data as image overlay
        const coverageMask = coverageData.coverage_mask;
        const signalStrength = coverageData.signal_strength;
        const demBounds = coverageData.dem_bounds; // [west, south, east, north]
        const txLat = coverageData.tx_lat;
        const txLon = coverageData.tx_lon;
        
        console.log('addSingleSiteCoverage called');
        console.log('TX coordinates from backend:', txLat, txLon);
        console.log('Coverage mask:', coverageMask ? `${coverageMask.length}x${coverageMask[0]?.length}` : 'null');
        console.log('DEM bounds [W,S,E,N]:', demBounds);
        
        // Check if TX is within DEM bounds
        const [west, south, east, north] = demBounds;
        console.log('TX within bounds?', 
            `Lat ${txLat} in [${south}, ${north}]:`, txLat >= south && txLat <= north,
            `Lon ${txLon} in [${west}, ${east}]:`, txLon >= west && txLon <= east);
        
        if (!coverageMask || !demBounds) {
            console.error('Missing coverage data or bounds');
            return;
        }
        
        // Create canvas to render coverage
        const height = coverageMask.length;
        const width = coverageMask[0].length;
        console.log(`Creating canvas: ${width}x${height}`);
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        const imageData = ctx.createImageData(width, height);
        
        // Get color for this site (cycles through color array)
        const siteColor = this.siteColors[this.currentColorIndex % this.siteColors.length];
        const rgb = this.hexToRgb(siteColor);
        
        const getColor = (signalDbm) => {
            // 75% transparency = 191 alpha (0.75 * 255)
            return [rgb.r, rgb.g, rgb.b, 191];
        };
        
        // Render coverage mask to canvas
        let coveragePixelCount = 0;
        for (let row = 0; row < height; row++) {
            for (let col = 0; col < width; col++) {
                const idx = (row * width + col) * 4;
                
                if (coverageMask[row][col]) {
                    // Has coverage - color by signal strength
                    coveragePixelCount++;
                    const signal = signalStrength[row][col];
                    const [r, g, b, a] = getColor(signal);
                    imageData.data[idx] = r;
                    imageData.data[idx + 1] = g;
                    imageData.data[idx + 2] = b;
                    imageData.data[idx + 3] = a;
                } else {
                    // No coverage - transparent
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
            color: siteColor,
            visible: true
        };
        this.coverageLayers.push(layerInfo);
        this.currentColorIndex++;
        
        // Update layer control panel
        this.updateLayerControl();
        
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
        this.updateLayerControl();
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
            layerItem.innerHTML = `
                <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                    <input type="checkbox" id="layer-${index}" ${layerInfo.visible ? 'checked' : ''}>
                    <span style="width: 16px; height: 16px; background-color: ${layerInfo.color}; border: 1px solid #ccc; border-radius: 3px;"></span>
                    <span>${layerInfo.siteName}</span>
                </label>
            `;
            
            const checkbox = layerItem.querySelector('input');
            checkbox.addEventListener('change', (e) => {
                this.toggleLayerVisibility(index, e.target.checked);
            });
            
            layerList.appendChild(layerItem);
        });
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
    
    addSignalStrengthLegend() {
        /**
         * Add a legend showing signal strength color scale.
         */
        // Remove existing legend if present
        if (this.legend) {
            this.map.removeControl(this.legend);
        }
        
        // Create legend control
        this.legend = L.control({ position: 'bottomright' });
        
        this.legend.onAdd = function() {
            const div = L.DomUtil.create('div', 'signal-legend');
            div.innerHTML = `
                <h4>Signal Strength</h4>
                <div class="legend-scale">
                    <div class="legend-item">
                        <span class="legend-color" style="background: rgb(0, 255, 0);"></span>
                        <span class="legend-label">Strong (-50 dBm)</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background: rgb(255, 255, 0);"></span>
                        <span class="legend-label">Medium (-75 dBm)</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background: rgb(255, 0, 0);"></span>
                        <span class="legend-label">Weak (-100 dBm)</span>
                    </div>
                </div>
                <p class="legend-note">Coverage shows realistic terrain blocking</p>
            `;
            return div;
        };
        
        this.legend.addTo(this.map);
    }
}

// Initialize the application when the page loads

document.addEventListener('DOMContentLoaded', () => {
    new CoverageApp();
});

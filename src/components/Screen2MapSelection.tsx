import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, useMapEvents, useMap } from 'react-leaflet';
import L from 'leaflet';
import {
  LocomotionMode,
  Coordinate,
  RouteData,
  GpsStatus,
  HistorySession,
  MapTileProvider
} from '../types';
import {
  calculateRoute,
  fetchGps,
  checkLocalTiles,
  fetchHistory,
  getLocalSessions
} from '../api';
import { OfflineTileBanner, MAP_PROVIDERS } from './OfflineTileBanner';
import {
  ArrowLeft,
  Navigation,
  MapPin,
  Compass,
  AlertTriangle,
  Play,
  RotateCcw,
  Route as RouteIcon,
  Layers,
  History as HistoryIcon,
  X,
  Clock,
  CheckCircle2
} from 'lucide-react';

// Custom Crisp SVG DivIcons for Leaflet
const createSvgIcon = (svgString: string, anchor: [number, number] = [16, 32]) => {
  return L.divIcon({
    html: svgString,
    className: 'custom-leaflet-icon',
    iconSize: [32, 32],
    iconAnchor: anchor,
    popupAnchor: [0, -32],
  });
};

const startGpsIcon = createSvgIcon(`
  <div style="filter: drop-shadow(0 2px 5px rgba(6,182,212,0.6));">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="10" fill="#06b6d4" stroke="#ffffff" stroke-width="2.5"/>
      <circle cx="12" cy="12" r="4" fill="#070b14"/>
    </svg>
  </div>
`, [16, 16]);

const manualStartIcon = createSvgIcon(`
  <div style="filter: drop-shadow(0 2px 5px rgba(59,130,246,0.6));">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" fill="#3b82f6" stroke="#ffffff" stroke-width="1.5"/>
      <circle cx="12" cy="9" r="3" fill="#ffffff"/>
    </svg>
  </div>
`);

const destIcon = createSvgIcon(`
  <div style="filter: drop-shadow(0 2px 5px rgba(239,68,68,0.6));">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" fill="#ef4444" stroke="#ffffff" stroke-width="1.5"/>
      <circle cx="12" cy="9" r="3" fill="#ffffff"/>
    </svg>
  </div>
`);

// Map Click Handler Component
function MapClickHandler({
  onMapClick
}: {
  onMapClick: (coord: Coordinate) => void;
}) {
  useMapEvents({
    click(e) {
      onMapClick({ lat: e.latlng.lat, lng: e.latlng.lng });
    },
  });
  return null;
}

// Map Bounds Controller to fit route
function RouteBoundsController({ coordinates }: { coordinates?: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (coordinates && coordinates.length > 0) {
      const bounds = L.latLngBounds(coordinates.map(c => [c[0], c[1]]));
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 17 });
    }
  }, [coordinates, map]);
  return null;
}

interface Props {
  mode: LocomotionMode;
  tileProvider?: MapTileProvider;
  onChangeTileProvider?: (provider: MapTileProvider) => void;
  onBack: () => void;
  onStartLocomotion: (
    startCoord: Coordinate,
    destCoord: Coordinate,
    startSource: 'gnss' | 'manual',
    route: RouteData
  ) => void;
}

export const Screen2MapSelection: React.FC<Props> = ({
  mode,
  tileProvider = 'google',
  onChangeTileProvider,
  onBack,
  onStartLocomotion
}) => {
  // Coordinates & State
  const [startCoord, setStartCoord] = useState<Coordinate | null>(null);
  const [startSource, setStartSource] = useState<'gnss' | 'manual'>('manual');
  const [destCoord, setDestCoord] = useState<Coordinate | null>(null);
  const [clickTarget, setClickTarget] = useState<'start' | 'dest'>('start');
  
  // GPS Status
  const [gps, setGps] = useState<GpsStatus | null>(null);

  // Route State
  const [route, setRoute] = useState<RouteData | null>(null);
  const [isCalculatingRoute, setIsCalculatingRoute] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);

  // Tiles
  const [localTileSource, setLocalTileSource] = useState<MapTileProvider>(tileProvider);
  const [hasLocalTiles, setHasLocalTiles] = useState(false);

  const activeTileSource = tileProvider || localTileSource;
  const handleTileSourceChange = (prov: MapTileProvider) => {
    setLocalTileSource(prov);
    if (onChangeTileProvider) onChangeTileProvider(prov);
  };

  // History modal
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [historySessions, setHistorySessions] = useState<any[]>([]);

  // Default initial center: Bangalore (robot demonstration area)
  const defaultCenter: [number, number] = [12.9716, 77.5946];

  // Check local offline tiles on mount
  useEffect(() => {
    checkLocalTiles().then(exists => {
      setHasLocalTiles(exists);
    });
  }, []);

  // Poll GPS once or periodically
  useEffect(() => {
    let isMounted = true;

    async function checkGps() {
      try {
        const data = await fetchGps();
        if (!isMounted) return;
        setGps(data);

        // Auto populate start coordinates ONLY when valid GNSS fix exists
        if (data.fix_valid && data.latitude != null && data.longitude != null) {
          setStartCoord({ lat: data.latitude, lng: data.longitude });
          setStartSource('gnss');
          setClickTarget('dest');
        }
      } catch (err) {
        console.warn('GPS check error:', err);
      }
    }

    checkGps();
    const interval = setInterval(checkGps, 4000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Handle map click
  const handleMapClick = (coord: Coordinate) => {
    if (clickTarget === 'start' || !startCoord) {
      setStartCoord(coord);
      setStartSource('manual');
      setClickTarget('dest'); // Switch to destination selection after setting start
      setRoute(null);
      setRouteError(null);
    } else {
      setDestCoord(coord);
      setRoute(null); // Recalculate route when destination changes
      setRouteError(null);
    }
  };

  // Quick preset: Demo Start (Bangalore)
  const handleUseDemoStart = () => {
    setStartCoord({ lat: 12.9716, lng: 77.5946 });
    setStartSource('manual');
    setClickTarget('dest');
    setRoute(null);
    setRouteError(null);
  };

  // Handle Show Route
  const handleShowRoute = async () => {
    if (!startCoord || !destCoord) return;
    setIsCalculatingRoute(true);
    setRouteError(null);

    try {
      const res = await calculateRoute(
        startCoord.lat,
        startCoord.lng,
        destCoord.lat,
        destCoord.lng
      );
      if (res.success && res.route) {
        setRoute(res.route);
      } else {
        setRouteError(res.error || 'No traversable path found between points. Please choose another destination.');
      }
    } catch (err: any) {
      setRouteError(err.message || 'Route computation error.');
    } finally {
      setIsCalculatingRoute(false);
    }
  };

  // Use Current GPS handler
  const handleUseCurrentGps = () => {
    if (gps?.fix_valid && gps.latitude != null && gps.longitude != null) {
      setStartCoord({ lat: gps.latitude, lng: gps.longitude });
      setStartSource('gnss');
      setClickTarget('dest');
      setRoute(null);
    }
  };

  // Open history modal
  const handleOpenHistory = async () => {
    const backendHistory = await fetchHistory();
    const localHistory = getLocalSessions();
    const combined = [...backendHistory];
    for (const loc of localHistory) {
      if (!combined.some(b => b.session_id === loc.session_id)) {
        combined.push({
          session_id: loc.session_id,
          mode: loc.mode,
          start_lat: loc.start_lat,
          start_lon: loc.start_lon,
          dest_lat: loc.dest_lat,
          dest_lon: loc.dest_lon,
          status: loc.status,
          start_time: loc.start_time,
          end_time: loc.end_time,
          source: loc.completion_source
        });
      }
    }
    setHistorySessions(combined);
    setShowHistoryModal(true);
  };

  return (
    <div className="flex flex-col h-screen bg-[#070b14] text-slate-100 overflow-hidden">
      
      {/* Top Header */}
      <header className="bg-[#0d1527] border-b border-[#1f2d4d] px-4 py-3 flex items-center justify-between shrink-0 z-20">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="p-2 rounded-xl bg-[#13203c] hover:bg-[#1a2d54] text-slate-300 hover:text-white border border-[#273a62] transition-colors cursor-pointer flex items-center gap-1.5 text-xs font-mono"
            title="Return to Locomotion Mode Selection"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Back</span>
          </button>
          
          <div className="flex items-center gap-2">
            <h1 className="font-mono font-black text-white text-lg tracking-wider">
              TRACK GUARD
            </h1>
            <span className="text-slate-500 text-sm">/</span>
            <span className="text-xs uppercase font-mono px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-400 border border-cyan-800/50">
              {mode === 'wheel' ? 'Wheel Mode' : 'Integrated Mode'}
            </span>
          </div>
        </div>

        {/* GPS Status Indicator & History */}
        <div className="flex items-center gap-3 text-xs">
          <button
            onClick={handleOpenHistory}
            className="px-2.5 py-1.5 rounded-lg bg-[#13203c] hover:bg-[#1a2d54] text-slate-300 hover:text-white border border-[#273a62] font-mono flex items-center gap-1.5 cursor-pointer"
            title="View Past Navigation Sessions"
          >
            <HistoryIcon className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">History</span>
          </button>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#111c34] border border-[#1f2d4d]">
            <div
              className={`w-2.5 h-2.5 rounded-full ${
                gps?.fix_valid
                  ? 'bg-emerald-400 animate-pulse'
                  : 'bg-amber-500'
              }`}
            />
            <span className="font-mono text-slate-300">
              {gps?.fix_valid ? 'GNSS Fix: VALID (3D)' : 'Waiting for GNSS Fix (COM10 Disconnected)'}
            </span>
          </div>
        </div>
      </header>

      {/* Offline Tile Info Banner */}
      <OfflineTileBanner
        hasLocalTiles={hasLocalTiles}
        tileSource={activeTileSource}
        onChangeSource={handleTileSourceChange}
      />

      {/* Main Content: Map + Side Control Panel */}
      <div className="flex-1 relative flex flex-col md:flex-row overflow-hidden">
        
        {/* Map View */}
        <div className="flex-1 relative h-full">
          <MapContainer
            center={startCoord ? [startCoord.lat, startCoord.lng] : defaultCenter}
            zoom={15}
            scrollWheelZoom={true}
            className="w-full h-full z-10"
          >
            {(() => {
              const prov = MAP_PROVIDERS[activeTileSource] || MAP_PROVIDERS.google;
              return (
                <TileLayer
                  key={activeTileSource}
                  attribution={prov.attribution}
                  url={prov.url}
                  maxZoom={prov.maxZoom}
                />
              );
            })()}

            <MapClickHandler onMapClick={handleMapClick} />

            {/* Start Marker */}
            {startCoord && (
              <Marker
                position={[startCoord.lat, startCoord.lng]}
                icon={startSource === 'gnss' ? startGpsIcon : manualStartIcon}
              />
            )}

            {/* Destination Marker */}
            {destCoord && (
              <Marker
                position={[destCoord.lat, destCoord.lng]}
                icon={destIcon}
              />
            )}

            {/* Calculated Route Polyline */}
            {route && route.coordinates && (
              <>
                <Polyline
                  positions={route.coordinates}
                  pathOptions={{
                    color: '#06b6d4',
                    weight: 5,
                    opacity: 0.9,
                    lineCap: 'round',
                    lineJoin: 'round',
                  }}
                />
                <RouteBoundsController coordinates={route.coordinates} />
              </>
            )}
          </MapContainer>

          {/* Floating Instructions on Map */}
          <div className="absolute top-4 left-4 z-20 pointer-events-none">
            <div className="bg-[#0d1527]/90 backdrop-blur-md border border-[#1f2d4d] p-3 rounded-xl shadow-xl max-w-xs pointer-events-auto space-y-1.5">
              <div className="flex items-center gap-2 text-cyan-400 font-bold text-xs uppercase tracking-wider">
                <Compass className="w-4 h-4" />
                <span>Map Interaction</span>
              </div>
              <p className="text-xs text-slate-300">
                {!startCoord || clickTarget === 'start'
                  ? 'Click on the map to set Manual Start position (or click "Use Demo Start").'
                  : 'Click anywhere on the map to place Destination marker.'}
              </p>
            </div>
          </div>
        </div>

        {/* Right Side Control & Routing Panel */}
        <div className="w-full md:w-96 bg-[#0d1527] border-t md:border-t-0 md:border-l border-[#1f2d4d] p-5 flex flex-col justify-between overflow-y-auto shrink-0 z-20 shadow-2xl">
          
          <div className="space-y-5">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <RouteIcon className="w-5 h-5 text-cyan-400" />
                Route Planning
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Select start & destination on map to compute shortest traversable robot route.
              </p>
            </div>

            {/* GPS Warning if invalid */}
            {!gps?.fix_valid && (
              <div className="p-3 rounded-xl bg-amber-950/40 border border-amber-800/40 text-amber-300 text-xs flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold">GPS Unavailable / Waiting for GNSS Fix</div>
                  <p className="text-amber-400/80 mt-0.5 leading-relaxed">
                    NEO-M9N receiver is not receiving satellite fix (COM10). Operating in manual coordinate mode.
                  </p>
                </div>
              </div>
            )}

            {/* Coordinates Summary Card */}
            <div className="space-y-3 bg-[#070b14] p-3.5 rounded-xl border border-[#1f2d4d]">
              
              {/* Start Point */}
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-slate-400 font-medium">Start Location:</span>
                  <span
                    className={`font-mono text-[10px] px-1.5 py-0.5 rounded uppercase ${
                      startSource === 'gnss'
                        ? 'bg-cyan-950 text-cyan-400 border border-cyan-800/50'
                        : 'bg-blue-950 text-blue-400 border border-blue-800/50'
                    }`}
                  >
                    {startSource === 'gnss' ? 'Current GPS' : 'Manual Start'}
                  </span>
                </div>
                
                <div className="font-mono text-xs text-slate-200">
                  {startCoord
                    ? `${startCoord.lat.toFixed(6)}, ${startCoord.lng.toFixed(6)}`
                    : 'Click map or select demo start'}
                </div>

                <div className="flex flex-wrap items-center gap-2 mt-2">
                  <button
                    onClick={() => setClickTarget('start')}
                    className={`text-[11px] px-2 py-1 rounded font-mono transition-colors cursor-pointer border ${
                      clickTarget === 'start'
                        ? 'bg-blue-600 text-white border-blue-400'
                        : 'bg-[#13203c] text-slate-300 hover:text-white border-[#273a62]'
                    }`}
                  >
                    {startCoord ? 'Change Start on Map' : 'Set Start on Map'}
                  </button>

                  {!startCoord && (
                    <button
                      onClick={handleUseDemoStart}
                      className="text-[11px] px-2 py-1 rounded font-mono bg-[#13203c] hover:bg-[#1a2d54] text-cyan-300 border border-cyan-800/50 cursor-pointer"
                    >
                      Use Demo Start
                    </button>
                  )}

                  <button
                    onClick={handleUseCurrentGps}
                    disabled={!gps?.fix_valid}
                    className={`text-[11px] px-2 py-1 rounded font-mono transition-colors border ${
                      gps?.fix_valid
                        ? 'bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border-cyan-700/60 cursor-pointer'
                        : 'bg-slate-900 text-slate-600 border-slate-800 cursor-not-allowed'
                    }`}
                    title={gps?.fix_valid ? 'Use GPS Fix' : 'GPS Fix unavailable'}
                  >
                    Use Current GPS
                  </button>
                </div>
              </div>

              <div className="border-t border-[#1f2d4d]" />

              {/* Destination Point */}
              <div>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-slate-400 font-medium">Destination:</span>
                  <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-red-950 text-red-400 border border-red-800/50 uppercase">
                    Target
                  </span>
                </div>

                <div className="font-mono text-xs text-slate-200">
                  {destCoord
                    ? `${destCoord.lat.toFixed(6)}, ${destCoord.lng.toFixed(6)}`
                    : 'Click map to place target'}
                </div>

                {destCoord && (
                  <div className="mt-2">
                    <button
                      onClick={() => {
                        setDestCoord(null);
                        setRoute(null);
                        setClickTarget('dest');
                      }}
                      className="text-[11px] px-2 py-1 rounded font-mono bg-[#13203c] hover:bg-[#1a2d54] text-slate-300 hover:text-white border border-[#273a62] transition-colors cursor-pointer"
                    >
                      Change Destination
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Action: Show Route */}
            <div>
              <button
                onClick={handleShowRoute}
                disabled={!startCoord || !destCoord || isCalculatingRoute}
                className={`w-full py-3 rounded-xl font-bold text-sm tracking-wide transition-all cursor-pointer flex items-center justify-center gap-2 shadow-lg ${
                  startCoord && destCoord && !isCalculatingRoute
                    ? 'bg-cyan-500 hover:bg-cyan-400 text-black shadow-cyan-500/20'
                    : 'bg-slate-800 text-slate-500 cursor-not-allowed'
                }`}
              >
                {isCalculatingRoute ? (
                  <>
                    <RotateCcw className="w-4 h-4 animate-spin" />
                    <span>Calculating Shortest Route...</span>
                  </>
                ) : (
                  <>
                    <RouteIcon className="w-4 h-4" />
                    <span>Show Route</span>
                  </>
                )}
              </button>
            </div>

            {/* Error Message */}
            {routeError && (
              <div className="p-3 rounded-xl bg-red-950/60 border border-red-800/50 text-red-300 text-xs">
                {routeError}
              </div>
            )}

            {/* Route Summary & Steps Preview */}
            {route && (
              <div className="space-y-3 bg-[#070b14] p-3.5 rounded-xl border border-cyan-800/40">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-cyan-400 uppercase tracking-wider">Route Computed</span>
                  <span className="font-mono text-slate-400 text-[11px]">{route.source}</span>
                </div>

                {/* Display Start and Destination Coords prominently */}
                <div className="text-[11px] font-mono space-y-1 bg-[#0d1527] p-2.5 rounded-lg border border-[#1f2d4d]">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Start:</span>
                    <span className="text-slate-200">{startCoord ? `${startCoord.lat.toFixed(6)}, ${startCoord.lng.toFixed(6)}` : 'N/A'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Destination:</span>
                    <span className="text-slate-200">{destCoord ? `${destCoord.lat.toFixed(6)}, ${destCoord.lng.toFixed(6)}` : 'N/A'}</span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2 text-center">
                  <div className="bg-[#0d1527] p-2 rounded-lg border border-[#1f2d4d]">
                    <div className="text-[10px] text-slate-400 uppercase font-mono">Distance</div>
                    <div className="text-base font-bold text-white font-mono mt-0.5">
                      {route.distance_m >= 1000
                        ? `${(route.distance_m / 1000).toFixed(2)} km`
                        : `${Math.round(route.distance_m)} m`}
                    </div>
                  </div>
                  <div className="bg-[#0d1527] p-2 rounded-lg border border-[#1f2d4d]">
                    <div className="text-[10px] text-slate-400 uppercase font-mono">Est. Time</div>
                    <div className="text-base font-bold text-white font-mono mt-0.5">
                      {Math.ceil(route.duration_s / 60)} min
                    </div>
                  </div>
                </div>

                {/* Steps Preview */}
                <div className="space-y-1.5 pt-1">
                  <div className="text-[11px] font-mono text-slate-400 uppercase">Maneuver Preview:</div>
                  <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                    {route.steps.map((st, i) => (
                      <div key={i} className="text-xs text-slate-300 p-1.5 rounded bg-[#0d1527] border border-[#1f2d4d]/60 flex items-start gap-2">
                        <span className="text-cyan-400 font-mono text-[10px] shrink-0 mt-0.5">{i + 1}.</span>
                        <div className="flex-1">
                          <div>{st.instruction}</div>
                          {st.distance_m > 0 && (
                            <div className="text-[10px] font-mono text-slate-500 mt-0.5">{Math.round(st.distance_m)} m</div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

          </div>

          {/* Reveal Start Locomotion Button ONLY after route calculation succeeds */}
          {route && (
            <div className="pt-4 border-t border-[#1f2d4d]">
              <button
                onClick={() => {
                  if (startCoord && destCoord && route) {
                    onStartLocomotion(startCoord, destCoord, startSource, route);
                  }
                }}
                className="w-full py-3.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-black font-extrabold text-sm tracking-wider uppercase transition-all shadow-lg shadow-cyan-500/25 flex items-center justify-center gap-2 cursor-pointer"
              >
                <Play className="w-4 h-4 fill-black" />
                <span>Start Locomotion</span>
              </button>
            </div>
          )}

        </div>

      </div>

      {/* History Modal */}
      {showHistoryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="max-w-2xl w-full bg-[#0d1527] border border-[#1f2d4d] rounded-2xl p-6 shadow-2xl space-y-4 max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-[#1f2d4d] pb-3 shrink-0">
              <div className="flex items-center gap-2 text-cyan-400">
                <HistoryIcon className="w-5 h-5" />
                <h3 className="font-bold text-white text-base">Navigation Session History</h3>
              </div>
              <button
                onClick={() => setShowHistoryModal(false)}
                className="text-slate-400 hover:text-white transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 pr-1 text-xs font-mono">
              {historySessions.length === 0 ? (
                <div className="text-center py-8 text-slate-500">No navigation sessions recorded yet.</div>
              ) : (
                historySessions.map((sess, idx) => (
                  <div key={idx} className="p-3.5 rounded-xl bg-[#070b14] border border-[#1f2d4d] space-y-2">
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="font-bold text-white">{sess.session_id || `Session #${sess.id}`}</span>
                      <span className={`px-2 py-0.5 rounded uppercase text-[10px] ${
                        sess.status === 'completed'
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/50'
                          : sess.status === 'cancelled'
                          ? 'bg-slate-800 text-slate-400 border border-slate-700'
                          : 'bg-cyan-950 text-cyan-400 border border-cyan-800/50'
                      }`}>
                        {sess.status}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-slate-400 text-[11px]">
                      <div>Mode: <span className="text-slate-200 capitalize">{sess.mode}</span></div>
                      <div>Distance: <span className="text-slate-200">{sess.distance_traveled_km ? `${sess.distance_traveled_km} km` : '0 m'}</span></div>
                      <div>Start: <span className="text-slate-300">{sess.start_lat ? `${sess.start_lat.toFixed(4)}, ${sess.start_lon.toFixed(4)}` : 'N/A'}</span></div>
                      <div>Target: <span className="text-slate-300">{sess.dest_lat ? `${sess.dest_lat.toFixed(4)}, ${sess.dest_lon.toFixed(4)}` : 'N/A'}</span></div>
                    </div>

                    <div className="text-[10px] text-slate-500 flex items-center justify-between border-t border-[#1f2d4d]/60 pt-1.5">
                      <span>Started: {sess.start_time ? new Date(sess.start_time).toLocaleString() : 'N/A'}</span>
                      {sess.end_time && <span>Ended: {new Date(sess.end_time).toLocaleTimeString()}</span>}
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="pt-2 text-right border-t border-[#1f2d4d] shrink-0">
              <button
                onClick={() => setShowHistoryModal(false)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs cursor-pointer font-mono"
              >
                Close History
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};

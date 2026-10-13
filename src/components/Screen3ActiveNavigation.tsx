import React, { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Polyline, useMap } from 'react-leaflet';
import L from 'leaflet';
import {
  LocomotionMode,
  Coordinate,
  RouteData,
  RouteStep,
  GpsStatus,
  NavigationSession,
  MapTileProvider
} from '../types';
import {
  fetchGps,
  stopNavigationSession,
  completeNavigationSession,
  saveLocalSession,
  checkLocalTiles
} from '../api';
import { ConfirmationModal } from './ConfirmationModal';
import { MAP_PROVIDERS } from './OfflineTileBanner';
import {
  ArrowLeft,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Compass,
  Navigation as NavIcon,
  CornerUpLeft,
  CornerUpRight,
  ArrowUp,
  RotateCcw,
  MapPin,
  Clock,
  Gauge,
  Activity,
  Maximize2
} from 'lucide-react';

// Custom Crisp SVG Icons
const createSvgIcon = (svgString: string, anchor: [number, number] = [16, 16]) => {
  return L.divIcon({
    html: svgString,
    className: 'custom-leaflet-icon',
    iconSize: [32, 32],
    iconAnchor: anchor,
    popupAnchor: [0, -16],
  });
};

const liveRobotGpsIcon = createSvgIcon(`
  <div style="filter: drop-shadow(0 0 10px rgba(6,182,212,0.9));">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="10" fill="#06b6d4" stroke="#ffffff" stroke-width="2.5"/>
      <polygon points="12,4 16,16 12,13 8,16" fill="#070b14"/>
    </svg>
  </div>
`);

const staleRobotGpsIcon = createSvgIcon(`
  <div style="filter: drop-shadow(0 0 8px rgba(245,158,11,0.8)); opacity: 0.85;">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="10" fill="#d97706" stroke="#ffffff" stroke-width="2.5" stroke-dasharray="3,2"/>
      <polygon points="12,4 16,16 12,13 8,16" fill="#070b14"/>
    </svg>
  </div>
`);

const startIcon = createSvgIcon(`
  <div style="filter: drop-shadow(0 2px 4px rgba(59,130,246,0.6));">
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="9" fill="#3b82f6" stroke="#ffffff" stroke-width="2"/>
      <circle cx="12" cy="12" r="3" fill="#ffffff"/>
    </svg>
  </div>
`, [14, 14]);

const destIcon = createSvgIcon(`
  <div style="filter: drop-shadow(0 2px 6px rgba(239,68,68,0.7));">
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" fill="#ef4444" stroke="#ffffff" stroke-width="1.5"/>
      <circle cx="12" cy="9" r="3.5" fill="#ffffff"/>
    </svg>
  </div>
`, [16, 32]);

// Helper: Haversine distance in meters
function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371000; // meters
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// Map recentering controller
function RecenterController({ center }: { center?: [number, number] }) {
  const map = useMap();
  useEffect(() => {
    if (center) {
      map.setView(center, map.getZoom(), { animate: true });
    }
  }, [center, map]);
  return null;
}

interface Props {
  mode: LocomotionMode;
  tileProvider?: MapTileProvider;
  onChangeTileProvider?: (provider: MapTileProvider) => void;
  startCoord: Coordinate;
  destCoord: Coordinate;
  startSource: 'gnss' | 'manual';
  route: RouteData;
  sessionId: string | null;
  onFinishNavigation: () => void; // Returns directly to Screen 1
  onCancelNavigation: () => void; // Returns to Screen 1
}

export const Screen3ActiveNavigation: React.FC<Props> = ({
  mode,
  tileProvider = 'google',
  onChangeTileProvider,
  startCoord,
  destCoord,
  startSource,
  route,
  sessionId,
  onFinishNavigation,
  onCancelNavigation
}) => {
  // GPS State
  const [gps, setGps] = useState<GpsStatus | null>(null);
  const [traveledTrack, setTraveledTrack] = useState<[number, number][]>([]);
  const [isStale, setIsStale] = useState<boolean>(true);
  const [lastFixTime, setLastFixTime] = useState<string | null>(null);
  const [lastKnownPosition, setLastKnownPosition] = useState<[number, number] | null>(
    startSource === 'gnss' ? [startCoord.lat, startCoord.lng] : null
  );

  // Maneuver state & Real step advancement
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(0);

  // Local tile support
  const [hasLocalTiles, setHasLocalTiles] = useState(false);

  // Modals
  const [showCompleteModal, setShowCompleteModal] = useState<boolean>(false);
  const [showCancelModal, setShowCancelModal] = useState<boolean>(false);

  // Map center
  const [mapCenter, setMapCenter] = useState<[number, number]>([startCoord.lat, startCoord.lng]);

  // Check offline tiles on mount
  useEffect(() => {
    checkLocalTiles().then(res => setHasLocalTiles(res));
  }, []);

  // Telemetry polling and live route advancement
  useEffect(() => {
    let isMounted = true;

    async function pollGps() {
      try {
        const data = await fetchGps();
        if (!isMounted) return;
        setGps(data);

        if (data.fix_valid && data.latitude != null && data.longitude != null) {
          setIsStale(false);
          const newPt: [number, number] = [data.latitude, data.longitude];
          setLastKnownPosition(newPt);
          setTraveledTrack(prev => [...prev, newPt]);
          const updateTime = data.last_update
            ? new Date(data.last_update).toLocaleTimeString()
            : new Date().toLocaleTimeString();
          setLastFixTime(updateTime);
          setMapCenter(newPt);

          // Real route step progression: advance when robot approaches current maneuver point (within 20m)
          if (route.steps && route.steps.length > 0) {
            setCurrentStepIndex(prevIdx => {
              const currentStep = route.steps[prevIdx];
              if (currentStep && currentStep.location) {
                const distToStep = haversineM(
                  data.latitude!,
                  data.longitude!,
                  currentStep.location[0],
                  currentStep.location[1]
                );
                if (distToStep < 20 && prevIdx < route.steps.length - 1) {
                  return prevIdx + 1;
                }
              }
              return prevIdx;
            });
          }
        } else {
          // No fix / disconnected / stale
          setIsStale(true);
        }
      } catch (err) {
        if (!isMounted) return;
        setIsStale(true);
      }
    }

    pollGps();
    const interval = setInterval(pollGps, 3000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [route.steps]);

  // Handle Manual Completion
  const handleConfirmCompletion = async () => {
    setShowCompleteModal(false);
    try {
      await completeNavigationSession(sessionId);
      // Persist to local storage
      saveLocalSession({
        session_id: sessionId,
        mode,
        start_lat: startCoord.lat,
        start_lon: startCoord.lng,
        dest_lat: destCoord.lat,
        dest_lon: destCoord.lng,
        start_source: startSource,
        status: 'completed',
        completion_source: 'manual',
        start_time: new Date().toISOString(),
        end_time: new Date().toISOString(),
        route_data: route,
        points: traveledTrack
      });
    } catch (e) {
      console.warn('Completion error:', e);
    }
    // Directly navigate back to Screen 1 (Initial Mode Selection)
    onFinishNavigation();
  };

  // Handle Cancellation (Stop Navigation)
  const handleConfirmCancel = async () => {
    setShowCancelModal(false);
    try {
      await stopNavigationSession(sessionId);
      saveLocalSession({
        session_id: sessionId,
        mode,
        start_lat: startCoord.lat,
        start_lon: startCoord.lng,
        dest_lat: destCoord.lat,
        dest_lon: destCoord.lng,
        start_source: startSource,
        status: 'cancelled',
        start_time: new Date().toISOString(),
        end_time: new Date().toISOString(),
        route_data: route,
        points: traveledTrack
      });
    } catch (e) {
      console.warn('Stop error:', e);
    }
    onCancelNavigation();
  };

  // Maneuver Icon Helper
  const getManeuverIcon = (type: string) => {
    const t = type.toLowerCase();
    if (t.includes('left') || t.includes('sharp left')) return <CornerUpLeft className="w-8 h-8 text-cyan-400" />;
    if (t.includes('right') || t.includes('sharp right')) return <CornerUpRight className="w-8 h-8 text-cyan-400" />;
    if (t.includes('uturn')) return <RotateCcw className="w-8 h-8 text-amber-400" />;
    if (t.includes('arrive') || t.includes('dest')) return <MapPin className="w-8 h-8 text-emerald-400" />;
    return <ArrowUp className="w-8 h-8 text-cyan-400" />;
  };

  const currentStep: RouteStep | undefined = route.steps[currentStepIndex] || route.steps[0];
  const nextStep: RouteStep | undefined = route.steps[currentStepIndex + 1];

  // Recenter target: robot position if available, else start
  const handleRecenter = () => {
    if (lastKnownPosition) {
      setMapCenter(lastKnownPosition);
    } else {
      setMapCenter([startCoord.lat, startCoord.lng]);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-[#070b14] text-slate-100 overflow-hidden select-none">
      
      {/* Top Status Header */}
      <header className="bg-[#0d1527] border-b border-[#1f2d4d] px-4 py-2.5 flex items-center justify-between shrink-0 z-30">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-mono font-black text-white text-base tracking-wider">
              ACTIVE NAVIGATION
            </span>
          </div>
          
          <span className="text-slate-500 text-sm">/</span>
          
          <span className="text-xs uppercase font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/50">
            {mode === 'wheel' ? 'Wheel Mode' : 'Integrated Mode'}
          </span>

          {sessionId && (
            <span className="hidden sm:inline font-mono text-[11px] text-slate-400 px-2 py-0.5 rounded bg-[#111c34]">
              ID: {sessionId}
            </span>
          )}
        </div>

        {/* Map Layer Switcher */}
        {onChangeTileProvider && (
          <div className="hidden md:flex items-center bg-[#13203c] rounded-lg p-0.5 border border-[#273a62]">
            {(['google', 'google-hybrid', 'carto-dark'] as MapTileProvider[]).map((key) => {
              const prov = MAP_PROVIDERS[key];
              const isSelected = tileProvider === key;
              return (
                <button
                  key={key}
                  onClick={() => onChangeTileProvider(key)}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-cyan-500 text-black font-bold'
                      : 'text-slate-300 hover:text-white hover:bg-[#1a2d54]'
                  }`}
                  title={`Switch to ${prov.name}`}
                >
                  {prov.shortName}
                </button>
              );
            })}
          </div>
        )}

        {/* Action Controls */}
        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setShowCancelModal(true)}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 font-mono text-xs transition-colors flex items-center gap-1.5 cursor-pointer"
            title="Cancel Navigation Session without arrival"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Stop Navigation</span>
          </button>

          <button
            onClick={() => setShowCompleteModal(true)}
            className="px-4 py-1.5 rounded-lg bg-gradient-to-r from-emerald-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-black font-extrabold text-xs tracking-wider uppercase transition-all shadow-lg shadow-emerald-500/25 flex items-center gap-1.5 cursor-pointer"
            title="Confirm Manual Arrival at Target"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>Reached Location</span>
          </button>
        </div>
      </header>

      {/* 50:50 Desktop Split Layout */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        
        {/* ========================================================= */}
        {/* LEFT HALF: MAP (UPPER) + TELEMETRY (LOWER)                */}
        {/* ========================================================= */}
        <div className="w-full lg:w-1/2 flex flex-col border-b lg:border-b-0 lg:border-r border-[#1f2d4d] h-1/2 lg:h-full overflow-hidden">
          
          {/* Upper Section: Map */}
          <div className="flex-1 relative min-h-[220px]">
            <MapContainer
              center={mapCenter}
              zoom={16}
              scrollWheelZoom={true}
              className="w-full h-full z-10"
            >
              {(() => {
                const prov = MAP_PROVIDERS[tileProvider] || MAP_PROVIDERS.google;
                return (
                  <TileLayer
                    key={tileProvider}
                    attribution={prov.attribution}
                    url={prov.url}
                    maxZoom={prov.maxZoom}
                  />
                );
              })()}

              <RecenterController center={mapCenter} />

              {/* Start Marker */}
              <Marker position={[startCoord.lat, startCoord.lng]} icon={startIcon} />

              {/* Destination Marker */}
              <Marker position={[destCoord.lat, destCoord.lng]} icon={destIcon} />

              {/* Planned Route (Solid Cyan Polyline) */}
              {route && route.coordinates && (
                <Polyline
                  positions={route.coordinates}
                  pathOptions={{
                    color: '#06b6d4',
                    weight: 6,
                    opacity: 0.9,
                    lineCap: 'round',
                  }}
                />
              )}

              {/* Traveled Track (Amber Dashed Polyline when live GPS points exist) */}
              {traveledTrack.length > 0 && (
                <Polyline
                  positions={traveledTrack}
                  pathOptions={{
                    color: '#f59e0b',
                    weight: 4,
                    dashArray: '8, 8',
                    opacity: 0.95,
                  }}
                />
              )}

              {/* Robot Position Marker: Stays frozen if GNSS stops updating */}
              {lastKnownPosition && (
                <Marker
                  position={lastKnownPosition}
                  icon={!isStale && gps?.fix_valid ? liveRobotGpsIcon : staleRobotGpsIcon}
                />
              )}
            </MapContainer>

            {/* Floating GNSS Warning Badge */}
            {isStale && (
              <div className="absolute top-3 left-3 z-20 pointer-events-none">
                <div className="bg-amber-950/90 backdrop-blur-md border border-amber-800/60 text-amber-300 px-3 py-1.5 rounded-lg shadow-xl text-xs flex items-center gap-2 pointer-events-auto">
                  <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
                  <div>
                    <span className="font-semibold">GNSS Stale / Disconnected</span>
                    <span className="text-amber-400/80 block text-[10px]">
                      {lastKnownPosition
                        ? 'Position marker frozen at last known coordinates.'
                        : 'Operating in manual coordinate mode without satellite fix.'}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Recenter Button */}
            <div className="absolute bottom-3 right-3 z-20">
              <button
                onClick={handleRecenter}
                className="p-2.5 rounded-xl bg-[#0d1527]/90 hover:bg-[#13203c] text-cyan-400 border border-[#1f2d4d] shadow-lg transition-colors cursor-pointer"
                title="Recenter Map on Robot / Start Position"
              >
                <Maximize2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Lower Section: Telemetry Panel */}
          <div className="h-56 lg:h-64 bg-[#0d1527] border-t border-[#1f2d4d] p-4 flex flex-col justify-between shrink-0 overflow-y-auto">
            <div>
              <div className="flex items-center justify-between border-b border-[#1f2d4d] pb-2 mb-3">
                <div className="flex items-center gap-2 text-xs font-mono font-bold text-white uppercase tracking-wider">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  <span>Hardware Telemetry Panel</span>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                      gps?.fix_valid
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/50'
                        : 'bg-red-950 text-red-300 border border-red-800/50'
                    }`}
                  >
                    GNSS: {gps?.fix_state || 'DISCONNECTED'}
                  </span>
                </div>
              </div>

              {/* Telemetry Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs font-mono">
                
                {/* Latitude */}
                <div className="bg-[#070b14] p-2.5 rounded-lg border border-[#1f2d4d]">
                  <span className="text-slate-500 text-[10px] uppercase block">Latitude</span>
                  <span className="text-white font-bold text-sm">
                    {gps?.fix_valid && gps.latitude != null ? gps.latitude.toFixed(6) : 'N/A'}
                  </span>
                </div>

                {/* Longitude */}
                <div className="bg-[#070b14] p-2.5 rounded-lg border border-[#1f2d4d]">
                  <span className="text-slate-500 text-[10px] uppercase block">Longitude</span>
                  <span className="text-white font-bold text-sm">
                    {gps?.fix_valid && gps.longitude != null ? gps.longitude.toFixed(6) : 'N/A'}
                  </span>
                </div>

                {/* Speed */}
                <div className="bg-[#070b14] p-2.5 rounded-lg border border-[#1f2d4d]">
                  <span className="text-slate-500 text-[10px] uppercase block">Speed</span>
                  <span className="text-white font-bold text-sm">
                    {gps?.fix_valid && gps.speed_kmh != null ? `${gps.speed_kmh.toFixed(1)} km/h` : 'N/A'}
                  </span>
                </div>

                {/* Heading */}
                <div className="bg-[#070b14] p-2.5 rounded-lg border border-[#1f2d4d]">
                  <span className="text-slate-500 text-[10px] uppercase block">Heading</span>
                  <span className="text-white font-bold text-sm">
                    {gps?.fix_valid && gps.heading_deg != null ? `${Math.round(gps.heading_deg)}°` : 'N/A'}
                  </span>
                </div>

                {/* App Mode */}
                <div className="bg-[#070b14] p-2.5 rounded-lg border border-[#1f2d4d]">
                  <span className="text-slate-500 text-[10px] uppercase block">App Mode</span>
                  <span className="text-cyan-400 font-semibold text-xs capitalize">
                    {mode === 'wheel' ? 'Wheel Mode' : 'Integrated Mode'}
                  </span>
                </div>

                {/* Robot Hardware Locomotion Mode (Firmware Status) */}
                <div className="bg-[#070b14] p-2.5 rounded-lg border border-[#1f2d4d]">
                  <span className="text-slate-500 text-[10px] uppercase block">Robot Locomotion</span>
                  <span className="text-slate-400 font-normal text-xs" title="Motor driver feedback placeholder">
                    Not Connected
                  </span>
                </div>

                {/* Satellites */}
                <div className="bg-[#070b14] p-2.5 rounded-lg border border-[#1f2d4d]">
                  <span className="text-slate-500 text-[10px] uppercase block">Sats (View/Used)</span>
                  <span className="text-slate-200 font-bold text-xs">
                    {gps ? `${gps.satellites_in_view} / ${gps.satellites_used}` : '0 / 0'}
                  </span>
                </div>

                {/* Last Update */}
                <div className="bg-[#070b14] p-2.5 rounded-lg border border-[#1f2d4d]">
                  <span className="text-slate-500 text-[10px] uppercase block">Last Update</span>
                  <span className="text-slate-300 text-xs">
                    {lastFixTime || 'N/A'}
                  </span>
                </div>

              </div>
            </div>

            <div className="text-[10px] text-slate-500 font-mono mt-1 pt-1 border-t border-[#1f2d4d]/60 flex items-center justify-between">
              <span>Hardware Link: ESP32 COM3 & NEO-M9N COM10</span>
              <span>Manual Coordinate Fallback Active</span>
            </div>
          </div>

        </div>

        {/* ========================================================= */}
        {/* RIGHT HALF: NAVIGATION INSTRUCTIONS PANEL                 */}
        {/* ========================================================= */}
        <div className="w-full lg:w-1/2 bg-[#070b14] flex flex-col h-1/2 lg:h-full overflow-hidden">
          
          {/* Top Maneuver Banner */}
          <div className="p-6 bg-[#0d1527] border-b border-[#1f2d4d] shadow-lg shrink-0">
            <div className="flex items-start gap-5">
              <div className="p-4 rounded-2xl bg-cyan-950/70 border border-cyan-700/50 flex items-center justify-center shrink-0">
                {currentStep ? getManeuverIcon(currentStep.type) : <ArrowUp className="w-8 h-8 text-cyan-400" />}
              </div>

              <div className="flex-1 space-y-1">
                <div className="text-xs font-mono text-cyan-400 uppercase tracking-widest font-bold">
                  Next Maneuver
                </div>

                <div className="text-2xl sm:text-3xl font-black text-white tracking-tight uppercase leading-tight">
                  {currentStep?.instruction || 'Proceed along path'}
                </div>

                <div className="flex items-baseline gap-2 pt-1">
                  <span className="text-3xl font-black font-mono text-cyan-400">
                    {currentStep ? `${Math.round(currentStep.distance_m)}` : '0'}
                  </span>
                  <span className="text-sm font-mono text-slate-400 uppercase">meters</span>
                </div>

                {nextStep && (
                  <p className="text-xs text-slate-400 pt-1 font-sans">
                    Then: <span className="text-slate-200 font-medium">{nextStep.instruction}</span>
                  </p>
                )}
              </div>
            </div>

            {/* Total Remaining Distance & Time */}
            <div className="mt-5 pt-4 border-t border-[#1f2d4d] flex items-center justify-between text-xs font-mono">
              <div className="text-slate-400">
                Total Route Distance:
                <span className="text-white font-bold ml-1.5">
                  {route.distance_m >= 1000
                    ? `${(route.distance_m / 1000).toFixed(2)} km`
                    : `${Math.round(route.distance_m)} m`}
                </span>
              </div>
              <div className="text-slate-400">
                Est. Duration:
                <span className="text-white font-bold ml-1.5">
                  {Math.ceil(route.duration_s / 60)} min
                </span>
              </div>
            </div>
          </div>

          {/* Full Route-Step List (Scrollable) */}
          <div className="flex-1 p-6 overflow-y-auto space-y-3">
            <div className="flex items-center justify-between text-xs font-mono text-slate-400 uppercase pb-1">
              <span>Turn-by-Turn Route Execution</span>
              <span>{route.steps.length} Maneuvers</span>
            </div>

            <div className="space-y-2.5">
              {route.steps.map((step, idx) => {
                const isCurrent = idx === currentStepIndex;
                const isPast = idx < currentStepIndex;

                return (
                  <div
                    key={idx}
                    className={`p-4 rounded-xl border transition-all ${
                      isCurrent
                        ? 'bg-cyan-950/40 border-cyan-500 shadow-[0_0_15px_rgba(6,182,212,0.15)] ring-1 ring-cyan-500/50'
                        : isPast
                        ? 'bg-[#0d1527]/40 border-[#1f2d4d]/40 opacity-50'
                        : 'bg-[#0d1527] border-[#1f2d4d] text-slate-300'
                    }`}
                  >
                    <div className="flex items-start gap-3.5">
                      <div className="mt-0.5 shrink-0">
                        {getManeuverIcon(step.type)}
                      </div>

                      <div className="flex-1">
                        <div className="flex items-center justify-between text-xs">
                          <span
                            className={`font-mono font-bold ${
                              isCurrent ? 'text-cyan-400' : 'text-slate-400'
                            }`}
                          >
                            Step {idx + 1}
                          </span>
                          {step.distance_m > 0 && (
                            <span className="font-mono text-slate-400 text-[11px]">
                              {Math.round(step.distance_m)} m
                            </span>
                          )}
                        </div>

                        <div
                          className={`mt-1 font-semibold text-sm ${
                            isCurrent ? 'text-white text-base' : 'text-slate-300'
                          }`}
                        >
                          {step.instruction}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="p-3 rounded-xl bg-[#0d1527] border border-[#1f2d4d] text-[11px] text-slate-400 leading-relaxed font-sans mt-4">
              <span className="font-bold text-slate-300">Live GPS Notice:</span> Because satellite fix on COM10 is currently offline, navigation progress is maintained in manual coordinate mode without fabricated vehicle movements. When you have arrived at your destination, click the green <strong className="text-emerald-400">Reached Location</strong> button above.
            </div>
          </div>

        </div>

      </div>

      {/* Confirmation Modal for Reached Location (Manual Finish) */}
      <ConfirmationModal
        isOpen={showCompleteModal}
        title="Confirm Arrival at Destination"
        message="Are you sure you have arrived at your target location? This will record the session as manually completed and return to the locomotion mode selection screen."
        confirmLabel="Yes, Reached Destination"
        cancelLabel="Continue Navigating"
        variant="success"
        onConfirm={handleConfirmCompletion}
        onCancel={() => setShowCompleteModal(false)}
      />

      {/* Confirmation Modal for Stop Navigation (Cancel) */}
      <ConfirmationModal
        isOpen={showCancelModal}
        title="Stop Navigation Session?"
        message="Do you want to cancel the active navigation session? The session will be terminated and marked as cancelled."
        confirmLabel="Stop Session"
        cancelLabel="Keep Going"
        variant="danger"
        onConfirm={handleConfirmCancel}
        onCancel={() => setShowCancelModal(false)}
      />

    </div>
  );
};

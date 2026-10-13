import React, { useState } from 'react';
import { Layers, HelpCircle, X, CheckCircle, Info, MapPin } from 'lucide-react';
import { MapTileProvider } from '../types';

export const MAP_PROVIDERS: Record<MapTileProvider, {
  name: string;
  shortName: string;
  url: string;
  attribution: string;
  maxZoom: number;
}> = {
  google: {
    name: 'Google Maps (Roadmap)',
    shortName: 'Google Maps',
    url: 'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
    attribution: '&copy; Google Maps',
    maxZoom: 20,
  },
  'google-hybrid': {
    name: 'Google Satellite (Hybrid)',
    shortName: 'Satellite',
    url: 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
    attribution: '&copy; Google Maps Imagery',
    maxZoom: 20,
  },
  'carto-voyager': {
    name: 'CartoDB Voyager (Clean Open Maps)',
    shortName: 'Carto Voyager',
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; CARTO',
    maxZoom: 19,
  },
  'carto-dark': {
    name: 'CartoDB Dark Matter (High-Tech Dark)',
    shortName: 'Dark Matter',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; CARTO',
    maxZoom: 19,
  },
  local: {
    name: 'Local MBTiles Cache (/tiles/{z}/{x}/{y})',
    shortName: 'Local Cache',
    url: '/tiles/{z}/{x}/{y}.png',
    attribution: 'Local Offline Tile Cache',
    maxZoom: 18,
  },
};

interface Props {
  hasLocalTiles: boolean;
  tileSource: MapTileProvider;
  onChangeSource: (provider: MapTileProvider) => void;
}

export const OfflineTileBanner: React.FC<Props> = ({
  hasLocalTiles,
  tileSource,
  onChangeSource,
}) => {
  const [showDocs, setShowDocs] = useState(false);

  const currentProvider = MAP_PROVIDERS[tileSource] || MAP_PROVIDERS.google;

  return (
    <>
      <div className="bg-[#0b1324] border-b border-[#1f2d4d] px-4 py-2 flex flex-wrap items-center justify-between text-xs gap-3">
        
        {/* Left: Current Active Provider & Status */}
        <div className="flex items-center gap-2 text-slate-300">
          <Layers className="w-4 h-4 text-cyan-400" />
          <span className="font-mono text-slate-400">Map Layer:</span>
          <span className="font-semibold text-white">
            {currentProvider.name}
          </span>
          {tileSource === 'local' && !hasLocalTiles && (
            <span className="px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800/40 text-[10px] font-mono">
              Offline Tiles Not Cached
            </span>
          )}
        </div>

        {/* Right: Quick Map Layer Selector + Setup Guide */}
        <div className="flex items-center flex-wrap gap-2">
          
          <div className="flex items-center bg-[#13203c] rounded-lg p-0.5 border border-[#273a62]">
            {(Object.keys(MAP_PROVIDERS) as MapTileProvider[]).map((key) => {
              const prov = MAP_PROVIDERS[key];
              const isSelected = tileSource === key;
              return (
                <button
                  key={key}
                  onClick={() => onChangeSource(key)}
                  className={`px-2.5 py-1 rounded text-[11px] font-mono transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-cyan-500 text-black font-bold shadow-sm'
                      : 'text-slate-300 hover:text-white hover:bg-[#1a2d54]'
                  }`}
                  title={`Switch to ${prov.name}`}
                >
                  {prov.shortName}
                </button>
              );
            })}
          </div>

          <button
            onClick={() => setShowDocs(true)}
            className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-mono transition-colors cursor-pointer px-2 py-1"
          >
            <HelpCircle className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Offline Guide</span>
          </button>
        </div>
      </div>

      {/* Setup Guide Modal */}
      {showDocs && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="max-w-xl w-full bg-[#0d1527] border border-[#1f2d4d] rounded-2xl p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-[#1f2d4d] pb-3">
              <div className="flex items-center gap-2 text-cyan-400">
                <Info className="w-5 h-5" />
                <h3 className="font-bold text-white text-base">Map Providers & Offline Setup</h3>
              </div>
              <button
                onClick={() => setShowDocs(false)}
                className="text-slate-400 hover:text-white transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs text-slate-300 leading-relaxed font-sans">
              <p>
                Track Guard supports multiple high-reliability tile engines designed for uninterrupted robot monitoring without rate-limits or 403 policy blocks:
              </p>

              <div className="space-y-2">
                <div className="p-2.5 rounded-lg bg-[#070b14] border border-[#1f2d4d]">
                  <span className="font-bold text-cyan-400 font-mono">1. Google Maps (Roadmap & Satellite)</span>
                  <p className="text-slate-300 text-[11px] mt-0.5">
                    Fast, detailed road networks, building outlines, and photorealistic satellite imagery served via Google's high-speed CDN without requiring an API key.
                  </p>
                </div>

                <div className="p-2.5 rounded-lg bg-[#070b14] border border-[#1f2d4d]">
                  <span className="font-bold text-cyan-400 font-mono">2. CartoDB Voyager & Dark Matter</span>
                  <p className="text-slate-300 text-[11px] mt-0.5">
                    OpenStreetMap geographic data hosted on Carto's global CDN, providing clean street maps or native dark mode with zero 403 policy errors.
                  </p>
                </div>

                <div className="p-2.5 rounded-lg bg-[#070b14] border border-[#1f2d4d]">
                  <span className="font-bold text-cyan-400 font-mono">3. Local MBTiles Offline Cache</span>
                  <p className="text-slate-300 text-[11px] mt-0.5">
                    Stored locally in <code className="text-cyan-300">c:\final_review\tiles\{'{z}'}/{'{x}'}/{'{y}'}.png</code> for 100% offline air-gapped environments.
                  </p>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-cyan-950/40 border border-cyan-800/40 space-y-1">
                <div className="font-semibold text-cyan-300 flex items-center gap-1.5">
                  <CheckCircle className="w-3.5 h-3.5" />
                  Shortest-Distance Robot Routing (OSRM)
                </div>
                <p className="text-slate-300 text-[11px]">
                  Routing remains 100% local through your Python Flask OSRM engine at <code className="text-cyan-200">http://127.0.0.1:5000/api/route</code>, computing true shortest-distance pedestrian/robot pathway networks regardless of the visual map layer selected.
                </p>
              </div>
            </div>

            <div className="pt-2 text-right border-t border-[#1f2d4d]">
              <button
                onClick={() => setShowDocs(false)}
                className="px-4 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-black font-semibold text-xs cursor-pointer"
              >
                Close Guide
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

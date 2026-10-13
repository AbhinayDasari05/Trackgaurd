export type LocomotionMode = 'wheel' | 'integrated';
export type MapTileProvider = 'google' | 'google-hybrid' | 'carto-voyager' | 'carto-dark' | 'local';

export interface Coordinate {
  lat: number;
  lng: number;
}

export interface RouteStep {
  distance_m: number;
  duration_s: number;
  instruction: string;
  location: [number, number]; // [lat, lon]
  type: string;
}

export interface RouteData {
  coordinates: [number, number][]; // [[lat, lon], ...]
  distance_m: number;
  duration_s: number;
  source: string;
  steps: RouteStep[];
}

export interface GpsStatus {
  connected: boolean;
  fix_state: string; // e.g. "DISCONNECTED", "NO FIX", "3D FIX"
  fix_valid: boolean;
  latitude: number | null;
  longitude: number | null;
  speed_kmh: number | null;
  heading_deg: number | null;
  altitude_m: number | null;
  satellites_in_view: number;
  satellites_used: number;
  last_update: string | null;
  error?: string | null;
  source?: string;
  baud?: number;
  port?: string;
}

export interface NavigationSession {
  session_id: string | null;
  mode: LocomotionMode;
  start_lat: number | null;
  start_lon: number | null;
  dest_lat: number | null;
  dest_lon: number | null;
  start_source: 'gnss' | 'manual';
  status: 'planned' | 'active' | 'completed' | 'cancelled';
  completion_source?: 'manual' | 'gps';
  start_time: string | null;
  end_time: string | null;
  route_data?: RouteData | null;
  points?: [number, number][];
}

export interface HistorySession {
  id?: number;
  session_id: string | null;
  start_time: string | null;
  end_time?: string | null;
  start_lat: number | null;
  start_lon: number | null;
  dest_lat: number | null;
  dest_lon: number | null;
  mode: LocomotionMode;
  status: string;
  distance_traveled_km?: number;
  avg_speed_kmh?: number;
  max_speed_kmh?: number;
  points_count?: number;
  planned_route_json?: string;
  source?: string;
  completion_source?: string;
}

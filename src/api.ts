import { GpsStatus, LocomotionMode, RouteData, NavigationSession, HistorySession } from './types';

const API_BASE = '/api';
const LOCAL_STORAGE_KEY = 'trackguard_sessions_history';

// ───── Helpers ─────

/** Detect if the Flask backend is reachable (running locally) */
async function isBackendAvailable(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/status`, { cache: 'no-store', signal: AbortSignal.timeout(2000) });
    return res.ok && res.headers.get('content-type')?.includes('json') === true;
  } catch {
    return false;
  }
}

function generateSessionId(): string {
  const ts = Math.floor(Date.now() / 1000);
  const hex = Math.random().toString(16).substring(2, 8);
  return `TG-${ts}-${hex}`;
}

// ───── GPS & Status ─────

export async function fetchStatus(): Promise<any> {
  try {
    const res = await fetch(`${API_BASE}/status`, { cache: 'no-store', signal: AbortSignal.timeout(3000) });
    if (!res.ok) throw new Error('not ok');
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('json')) throw new Error('not json');
    return res.json();
  } catch {
    return { connected: false, fix_state: 'DISCONNECTED', error: 'Backend not reachable' };
  }
}

export async function fetchGps(): Promise<GpsStatus> {
  try {
    const res = await fetch(`${API_BASE}/gps`, { cache: 'no-store', signal: AbortSignal.timeout(3000) });
    if (!res.ok) throw new Error('not ok');
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('json')) throw new Error('not json');
    const data = await res.json();
    return data.status || data;
  } catch {
    return {
      connected: false,
      fix_state: 'DISCONNECTED',
      fix_valid: false,
      latitude: null,
      longitude: null,
      speed_kmh: null,
      heading_deg: null,
      altitude_m: null,
      satellites_in_view: 0,
      satellites_used: 0,
      last_update: null,
      error: 'Backend not reachable — operating in standalone web mode',
      source: 'standalone'
    };
  }
}

export async function setRobotMode(mode: LocomotionMode): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
      signal: AbortSignal.timeout(3000)
    });
    return res.ok;
  } catch {
    // Backend not available — mode stored in frontend state, no error
    return true;
  }
}

// ───── Route Calculation ─────

/**
 * Calculate route using:
 * 1. Local Flask backend (if available — connects to local OSRM)
 * 2. OSRM public demo API (fallback for Vercel / mobile deployments)
 */
export async function calculateRoute(
  startLat: number,
  startLon: number,
  destLat: number,
  destLon: number
): Promise<{ success: boolean; route?: RouteData; error?: string }> {
  // Try Flask backend first
  const backendResult = await tryFlaskRoute(startLat, startLon, destLat, destLon);
  if (backendResult !== null) return backendResult;

  // Fallback: OSRM public routing API (foot profile for robot/pedestrian)
  return tryOsrmPublicRoute(startLat, startLon, destLat, destLon);
}

async function tryFlaskRoute(
  startLat: number, startLon: number, destLat: number, destLon: number
): Promise<{ success: boolean; route?: RouteData; error?: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/route`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        start_lat: startLat,
        start_lon: startLon,
        dest_lat: destLat,
        dest_lon: destLon
      }),
      signal: AbortSignal.timeout(5000)
    });
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('json')) return null; // Not Flask — probably Vercel HTML 404
    const data = await res.json();
    if (!res.ok || !data.success) {
      return {
        success: false,
        error: data.error || 'No traversable path found between points.'
      };
    }
    const source = data.route?.source || '';
    if (source.includes('Geodesic') || source.includes('Fallback')) {
      return {
        success: false,
        error: 'No traversable road network route exists between these coordinates.'
      };
    }
    return { success: true, route: data.route };
  } catch {
    return null; // Backend unavailable — will use OSRM fallback
  }
}

async function tryOsrmPublicRoute(
  startLat: number, startLon: number, destLat: number, destLon: number
): Promise<{ success: boolean; route?: RouteData; error?: string }> {
  try {
    // OSRM public demo server — foot (pedestrian/robot) profile, shortest distance
    const url = `https://router.project-osrm.org/route/v1/foot/${startLon},${startLat};${destLon},${destLat}?overview=full&geometries=geojson&steps=true&annotations=distance`;
    const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) {
      return { success: false, error: `OSRM routing server returned ${res.status}. Try a different destination.` };
    }
    const data = await res.json();
    if (data.code !== 'Ok' || !data.routes || data.routes.length === 0) {
      return { success: false, error: 'No traversable route found between these coordinates.' };
    }

    const osrmRoute = data.routes[0];
    const legs = osrmRoute.legs || [];

    // Convert GeoJSON coordinates [lon, lat] to our format [lat, lon]
    const coordinates: [number, number][] = osrmRoute.geometry.coordinates.map(
      (c: [number, number]) => [c[1], c[0]]
    );

    // Validate route is an actual road network path (not just 2 endpoints)
    if (coordinates.length <= 2) {
      return {
        success: false,
        error: 'No traversable road network path exists. Only straight-line connections are available, which are not permitted.'
      };
    }

    // Extract turn-by-turn steps
    const steps: any[] = [];
    for (const leg of legs) {
      for (const step of (leg.steps || [])) {
        const maneuver = step.maneuver || {};
        const loc = maneuver.location || [startLon, startLat];
        const modifier = maneuver.modifier || '';
        const stepType = maneuver.type || 'continue';

        let instruction = '';
        if (stepType === 'depart') {
          instruction = 'Start navigation and head forward';
        } else if (stepType === 'arrive') {
          instruction = 'Arrive at destination';
        } else if (stepType === 'turn') {
          instruction = `Turn ${modifier}`;
          if (step.name) instruction += ` onto ${step.name}`;
        } else if (stepType === 'new name' || stepType === 'continue') {
          instruction = `Continue`;
          if (step.name) instruction += ` on ${step.name}`;
        } else if (stepType === 'roundabout' || stepType === 'rotary') {
          instruction = `Enter the roundabout`;
          if (maneuver.exit) instruction += ` and take exit ${maneuver.exit}`;
        } else if (stepType === 'fork') {
          instruction = `Keep ${modifier || 'straight'} at the fork`;
        } else if (stepType === 'end of road') {
          instruction = `Turn ${modifier || 'ahead'} at end of road`;
        } else {
          instruction = `${stepType.replace(/_/g, ' ')}`;
          if (modifier) instruction += ` ${modifier}`;
          if (step.name) instruction += ` onto ${step.name}`;
        }

        steps.push({
          distance_m: Math.round(step.distance || 0),
          duration_s: Math.round(step.duration || 0),
          instruction: instruction.charAt(0).toUpperCase() + instruction.slice(1),
          location: [loc[1], loc[0]], // [lat, lon]
          type: stepType
        });
      }
    }

    const routeData: RouteData = {
      coordinates,
      distance_m: Math.round(osrmRoute.distance || 0),
      duration_s: Math.round(osrmRoute.duration || 0),
      source: 'OSRM (Road Network)',
      steps
    };

    return { success: true, route: routeData };
  } catch (err: any) {
    return {
      success: false,
      error: err.message || 'Route calculation failed. Check your internet connection and try again.'
    };
  }
}

// ───── Navigation Session Management ─────

export async function startNavigationSession(
  mode: LocomotionMode,
  startLat: number,
  startLon: number,
  destLat: number,
  destLon: number,
  startSource: 'gnss' | 'manual' = 'manual',
  routeData?: RouteData | null
): Promise<{ success: boolean; session_id?: string; error?: string }> {
  // Try Flask backend first
  try {
    const res = await fetch(`${API_BASE}/navigation/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode,
        start_lat: startLat,
        start_lon: startLon,
        dest_lat: destLat,
        dest_lon: destLon,
        start_source: startSource,
        route_data: routeData
      }),
      signal: AbortSignal.timeout(3000)
    });
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('json')) {
      const data = await res.json();
      return data;
    }
  } catch {}

  // Standalone mode: generate session locally
  const sessionId = generateSessionId();
  return { success: true, session_id: sessionId };
}

export async function stopNavigationSession(
  sessionId?: string | null
): Promise<{ success: boolean }> {
  try {
    const res = await fetch(`${API_BASE}/navigation/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        status: 'cancelled'
      }),
      signal: AbortSignal.timeout(3000)
    });
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('json')) {
      return res.json();
    }
  } catch {}
  // Standalone: always succeed
  return { success: true };
}

export async function completeNavigationSession(
  sessionId: string | null
): Promise<{ success: boolean; completion?: string }> {
  try {
    const res = await fetch(`${API_BASE}/navigation/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        completion_method: 'manual',
        status: 'completed'
      }),
      signal: AbortSignal.timeout(3000)
    });
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('json') && res.ok) {
      return res.json();
    }
  } catch {}
  // Standalone: always succeed with manual completion
  return { success: true, completion: 'manual' };
}

export async function fetchNavigationSession(): Promise<{ success: boolean; session?: NavigationSession }> {
  try {
    const res = await fetch(`${API_BASE}/navigation/session`, { signal: AbortSignal.timeout(3000) });
    const ct = res.headers.get('content-type') || '';
    if (res.ok && ct.includes('json')) {
      return res.json();
    }
  } catch {}
  return { success: false };
}

export async function fetchHistory(): Promise<HistorySession[]> {
  try {
    const res = await fetch(`${API_BASE}/history`, { cache: 'no-store', signal: AbortSignal.timeout(3000) });
    const ct = res.headers.get('content-type') || '';
    if (res.ok && ct.includes('json')) {
      const data = await res.json();
      return data.sessions || [];
    }
  } catch {}
  return [];
}

// ───── Tiles ─────

export async function checkLocalTiles(): Promise<boolean> {
  try {
    const res = await fetch('/tiles/0/0/0.png', { method: 'HEAD', signal: AbortSignal.timeout(2000) });
    return res.ok && res.headers.get('content-type')?.includes('image') === true;
  } catch {
    return false;
  }
}

// ───── Local Storage Persistence ─────

export function saveLocalSession(session: NavigationSession): void {
  try {
    const existing = getLocalSessions();
    const filtered = existing.filter(s => s.session_id !== session.session_id);
    filtered.unshift(session);
    localStorage.setItem(LOCAL_STORAGE_KEY, JSON.stringify(filtered.slice(0, 50)));
  } catch (e) {
    console.warn('Local storage save error:', e);
  }
}

export function getLocalSessions(): NavigationSession[] {
  try {
    const raw = localStorage.getItem(LOCAL_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

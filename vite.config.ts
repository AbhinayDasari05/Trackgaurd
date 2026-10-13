import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';

// Active navigation session state tracker in Vite middleware
interface NavSessionState {
  session_id: string | null;
  mode: 'wheel' | 'integrated';
  start_lat: number | null;
  start_lon: number | null;
  dest_lat: number | null;
  dest_lon: number | null;
  start_source: 'gnss' | 'manual';
  status: 'planned' | 'active' | 'completed' | 'cancelled';
  completion_source?: 'manual' | 'gps';
  start_time: string | null;
  end_time: string | null;
  route_data?: any;
}

let activeNavigationSession: NavSessionState = {
  session_id: null,
  mode: 'wheel',
  start_lat: null,
  start_lon: null,
  dest_lat: null,
  dest_lon: null,
  start_source: 'manual',
  status: 'planned',
  start_time: null,
  end_time: null,
};

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'trackguard-api-bridge',
      configureServer(server) {
        server.middlewares.use(async (req, res, next) => {
          const url = req.url?.split('?')[0];

          // 1. Handle POST /api/navigation/start
          if (url === '/api/navigation/start' && req.method === 'POST') {
            try {
              let bodyStr = '';
              req.on('data', chunk => { bodyStr += chunk; });
              req.on('end', async () => {
                let parsed: any = {};
                try { parsed = JSON.parse(bodyStr || '{}'); } catch {}

                // Forward to Flask backend
                let flaskResData: any = {};
                try {
                  const flaskResp = await fetch('http://127.0.0.1:5000/api/navigation/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(parsed)
                  });
                  flaskResData = await flaskResp.json();
                } catch (err) {
                  console.warn('Flask start forward warning:', err);
                }

                const sessionId = flaskResData?.session_id || `TG-${Date.now()}`;
                activeNavigationSession = {
                  session_id: sessionId,
                  mode: parsed.mode || 'wheel',
                  start_lat: parsed.start_lat ?? null,
                  start_lon: parsed.start_lon ?? null,
                  dest_lat: parsed.dest_lat ?? null,
                  dest_lon: parsed.dest_lon ?? null,
                  start_source: parsed.start_source || 'manual',
                  status: 'active',
                  start_time: new Date().toISOString(),
                  end_time: null,
                  route_data: parsed.route_data || null
                };

                res.setHeader('Content-Type', 'application/json');
                res.writeHead(200);
                res.end(JSON.stringify({
                  success: true,
                  message: 'Navigation session started and logged.',
                  session_id: sessionId,
                  session: activeNavigationSession
                }));
              });
              return;
            } catch (err: any) {
              res.setHeader('Content-Type', 'application/json');
              res.writeHead(500);
              res.end(JSON.stringify({ success: false, error: err.message }));
              return;
            }
          }

          // 2. Handle POST /api/navigation/stop (Cancellation)
          if (url === '/api/navigation/stop' && req.method === 'POST') {
            try {
              let bodyStr = '';
              req.on('data', chunk => { bodyStr += chunk; });
              req.on('end', async () => {
                let parsed: any = {};
                try { parsed = JSON.parse(bodyStr || '{}'); } catch {}

                activeNavigationSession.status = 'cancelled';
                activeNavigationSession.end_time = new Date().toISOString();

                // Forward stop to Flask backend
                try {
                  await fetch('http://127.0.0.1:5000/api/navigation/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      session_id: activeNavigationSession.session_id,
                      status: 'cancelled'
                    })
                  });
                } catch (err) {
                  console.warn('Flask stop forward warning:', err);
                }

                res.setHeader('Content-Type', 'application/json');
                res.writeHead(200);
                res.end(JSON.stringify({
                  success: true,
                  message: 'Navigation cancelled and session state updated.',
                  session_id: activeNavigationSession.session_id,
                  status: 'cancelled'
                }));
              });
              return;
            } catch (err: any) {
              res.setHeader('Content-Type', 'application/json');
              res.writeHead(500);
              res.end(JSON.stringify({ success: false, error: err.message }));
              return;
            }
          }

          // 3. Handle POST /api/navigation/complete (Manual Arrival Completion)
          if (url === '/api/navigation/complete' && req.method === 'POST') {
            try {
              let bodyStr = '';
              req.on('data', chunk => { bodyStr += chunk; });
              req.on('end', async () => {
                let parsed: any = {};
                try { parsed = JSON.parse(bodyStr || '{}'); } catch {}

                activeNavigationSession.status = 'completed';
                activeNavigationSession.completion_source = 'manual';
                activeNavigationSession.end_time = new Date().toISOString();

                // Stop backend session on Flask port 5000 if active
                try {
                  await fetch('http://127.0.0.1:5000/api/navigation/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      session_id: parsed.session_id || activeNavigationSession.session_id,
                      completion_source: 'manual',
                      status: 'completed'
                    })
                  });
                } catch (err) {
                  console.warn('Flask stop call warning:', err);
                }

                res.setHeader('Content-Type', 'application/json');
                res.writeHead(200);
                res.end(JSON.stringify({
                  success: true,
                  message: 'Navigation manually marked as completed.',
                  completion: 'manual',
                  session: activeNavigationSession
                }));
              });
              return;
            } catch (err: any) {
              res.setHeader('Content-Type', 'application/json');
              res.writeHead(500);
              res.end(JSON.stringify({ success: false, error: err.message }));
              return;
            }
          }

          // 4. Handle GET /api/navigation/session
          if (url === '/api/navigation/session' && req.method === 'GET') {
            let backendRoute: any = null;
            try {
              const resp = await fetch('http://127.0.0.1:5000/api/route');
              if (resp.ok) {
                backendRoute = await resp.json();
              }
            } catch {}

            res.setHeader('Content-Type', 'application/json');
            res.writeHead(200);
            res.end(JSON.stringify({
              success: true,
              session: {
                ...activeNavigationSession,
                backend_active: backendRoute?.navigation_active ?? (activeNavigationSession.status === 'active'),
                current_metrics: backendRoute?.metrics ?? null,
                instruction: backendRoute?.instruction ?? null
              }
            }));
            return;
          }

          // 5. Handle POST /api/route (Validate & Reject Straight-line Fallback)
          if (url === '/api/route' && req.method === 'POST') {
            try {
              let bodyStr = '';
              req.on('data', chunk => { bodyStr += chunk; });
              req.on('end', async () => {
                try {
                  const flaskResp = await fetch('http://127.0.0.1:5000/api/route', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: bodyStr
                  });
                  const routeData = await flaskResp.json();

                  // Requirement 4: Reject fabricated straight-line geodesic fallback!
                  const source = routeData?.route?.source || '';
                  if (source.includes('Geodesic') || source.includes('Fallback')) {
                    res.setHeader('Content-Type', 'application/json');
                    res.writeHead(400);
                    res.end(JSON.stringify({
                      success: false,
                      error: 'No traversable network route exists between the selected points. Direct geodesic straight lines are not permitted for robot navigation.'
                    }));
                    return;
                  }

                  res.setHeader('Content-Type', 'application/json');
                  res.writeHead(flaskResp.status);
                  res.end(JSON.stringify(routeData));
                  return;
                } catch (err: any) {
                  res.setHeader('Content-Type', 'application/json');
                  res.writeHead(500);
                  res.end(JSON.stringify({ success: false, error: err.message }));
                  return;
                }
              });
              return;
            } catch (err: any) {
              res.setHeader('Content-Type', 'application/json');
              res.writeHead(500);
              res.end(JSON.stringify({ success: false, error: err.message }));
              return;
            }
          }

          // 6. Local offline map tile serving: /tiles/{z}/{x}/{y}.png
          if (url?.startsWith('/tiles/')) {
            const parts = url.replace('/tiles/', '').replace('.png', '').split('/');
            if (parts.length === 3) {
              const [z, x, y] = parts;
              const tilePath = path.resolve(process.cwd(), 'tiles', z, x, `${y}.png`);
              if (fs.existsSync(tilePath)) {
                res.setHeader('Content-Type', 'image/png');
                res.setHeader('Cache-Control', 'public, max-age=86400');
                fs.createReadStream(tilePath).pipe(res);
                return;
              }

              // On-demand fetch and cache to disk for offline persistence (using high-reliability CartoDB CDN)
              try {
                const upstreamUrl = `https://a.basemaps.cartocdn.com/rastertiles/voyager/${z}/${x}/${y}.png`;
                const osmResp = await fetch(upstreamUrl, {
                  headers: { 'User-Agent': 'Mozilla/5.0 TrackGuard-Robot' }
                });
                if (osmResp.ok) {
                  const buffer = Buffer.from(await osmResp.arrayBuffer());
                  fs.mkdirSync(path.dirname(tilePath), { recursive: true });
                  fs.writeFileSync(tilePath, buffer);
                  res.setHeader('Content-Type', 'image/png');
                  res.setHeader('Cache-Control', 'public, max-age=86400');
                  res.writeHead(200);
                  res.end(buffer);
                  return;
                }
              } catch (proxyErr) {
                // Offline fallback if fetch fails
              }

              res.setHeader('X-Tile-Status', 'offline-tile-missing');
              res.writeHead(404);
              res.end('Local offline tile not found.');
              return;
            }
          }

          next();
        });
      }
    }
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      }
    }
  }
});

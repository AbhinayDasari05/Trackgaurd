import React, { useState } from 'react';
import { LocomotionMode, Coordinate, RouteData, MapTileProvider } from './types';
import { Screen1ModeSelection } from './components/Screen1ModeSelection';
import { Screen2MapSelection } from './components/Screen2MapSelection';
import { Screen3ActiveNavigation } from './components/Screen3ActiveNavigation';
import { setRobotMode, startNavigationSession } from './api';

export function App() {
  const [currentScreen, setCurrentScreen] = useState<1 | 2 | 3>(1);
  const [selectedMode, setSelectedMode] = useState<LocomotionMode>('wheel');
  const [mapTileProvider, setMapTileProvider] = useState<MapTileProvider>('google');
  const [startCoordinate, setStartCoordinate] = useState<Coordinate | null>(null);
  const [destCoordinate, setDestCoordinate] = useState<Coordinate | null>(null);
  const [startLocationSource, setStartLocationSource] = useState<'gnss' | 'manual'>('manual');
  const [activeRoute, setActiveRoute] = useState<RouteData | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Transition: Screen 1 -> Screen 2
  const handleSelectMode = async (mode: LocomotionMode) => {
    setSelectedMode(mode);
    await setRobotMode(mode);
    setCurrentScreen(2);
  };

  // Transition: Screen 2 -> Screen 1 (Back)
  const handleBackToModeSelection = () => {
    setCurrentScreen(1);
    setActiveRoute(null);
  };

  // Transition: Screen 2 -> Screen 3 (Start Locomotion)
  const handleStartLocomotion = async (
    startCoord: Coordinate,
    destCoord: Coordinate,
    startSource: 'gnss' | 'manual',
    route: RouteData
  ) => {
    setStartCoordinate(startCoord);
    setDestCoordinate(destCoord);
    setStartLocationSource(startSource);
    setActiveRoute(route);

    // Call backend start API
    try {
      const startRes = await startNavigationSession(
        selectedMode,
        startCoord.lat,
        startCoord.lng,
        destCoord.lat,
        destCoord.lng,
        startSource,
        route
      );
      if (startRes.success && startRes.session_id) {
        setActiveSessionId(startRes.session_id);
      }
    } catch (err) {
      console.warn('Failed to start backend navigation session:', err);
    }

    setCurrentScreen(3);
  };

  // Transition: Screen 3 -> Screen 1 (Reached Location / Finish)
  const handleFinishNavigation = () => {
    // Clear session state
    setActiveRoute(null);
    setStartCoordinate(null);
    setDestCoordinate(null);
    setActiveSessionId(null);
    // Directly navigate back to Screen 1 (Initial mode selection)
    setCurrentScreen(1);
  };

  // Transition: Screen 3 -> Screen 1 (Cancel / Stop)
  const handleCancelNavigation = () => {
    setActiveRoute(null);
    setDestCoordinate(null);
    setActiveSessionId(null);
    setCurrentScreen(1);
  };

  return (
    <div className="w-full h-screen bg-[#070b14] overflow-hidden">
      {currentScreen === 1 && (
        <Screen1ModeSelection onSelectMode={handleSelectMode} />
      )}

      {currentScreen === 2 && (
        <Screen2MapSelection
          mode={selectedMode}
          tileProvider={mapTileProvider}
          onChangeTileProvider={setMapTileProvider}
          onBack={handleBackToModeSelection}
          onStartLocomotion={handleStartLocomotion}
        />
      )}

      {currentScreen === 3 && startCoordinate && destCoordinate && activeRoute && (
        <Screen3ActiveNavigation
          mode={selectedMode}
          tileProvider={mapTileProvider}
          onChangeTileProvider={setMapTileProvider}
          startCoord={startCoordinate}
          destCoord={destCoordinate}
          startSource={startLocationSource}
          route={activeRoute}
          sessionId={activeSessionId}
          onFinishNavigation={handleFinishNavigation}
          onCancelNavigation={handleCancelNavigation}
        />
      )}
    </div>
  );
}

export default App;

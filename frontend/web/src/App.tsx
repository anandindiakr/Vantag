import { Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import StoreDetail from './pages/StoreDetail';
import CameraView from './pages/CameraView';
import WatchlistPage from './pages/WatchlistPage';
import IncidentsPage from './pages/IncidentsPage';
import { useWebSocket } from './hooks/useWebSocket';
import { useMQTT } from './hooks/useMQTT';

export default function App() {
  // Bootstrap global real-time connections at app level
  useWebSocket();
  useMQTT();

  return (
    <div className="flex h-screen overflow-hidden bg-vantag-dark text-slate-100">
      {/* Sidebar navigation */}
      <Sidebar />

      {/* Main content area */}
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        <Routes>
          <Route path="/"                                    element={<Dashboard />} />
          <Route path="/store/:storeId"                      element={<StoreDetail />} />
          <Route path="/store/:storeId/camera/:cameraId"     element={<CameraView />} />
          <Route path="/watchlist"                           element={<WatchlistPage />} />
          <Route path="/incidents"                           element={<IncidentsPage />} />
          {/* Catch-all */}
          <Route path="*"                                    element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

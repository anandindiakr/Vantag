import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import './i18n/index';
import Sidebar from './components/Sidebar';
import { useWebSocket } from './hooks/useWebSocket';

// ── React Query client ──────────────────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

// ── Lazy-loaded pages ───────────────────────────────────────────────────────
const Landing      = lazy(() => import('./pages/Landing'));
const Login        = lazy(() => import('./pages/auth/Login'));
const Register     = lazy(() => import('./pages/auth/Register'));
const VerifyEmail  = lazy(() => import('./pages/auth/VerifyEmail'));
const Onboarding   = lazy(() => import('./pages/onboarding/Onboarding'));
const Dashboard    = lazy(() => import('./pages/Dashboard'));
const CamerasPage  = lazy(() => import('./pages/CamerasPage'));
const CameraView   = lazy(() => import('./pages/CameraView'));
const IncidentsPage = lazy(() => import('./pages/IncidentsPage'));
const WatchlistPage = lazy(() => import('./pages/WatchlistPage'));
const StoreDetail  = lazy(() => import('./pages/StoreDetail'));

// ── Auth helper ─────────────────────────────────────────────────────────────
function isAuthenticated() {
  return !!localStorage.getItem('vantag_token');
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  return isAuthenticated() ? <>{children}</> : <Navigate to="/login" replace />;
}

// ── Loading spinner ─────────────────────────────────────────────────────────
function Loading() {
  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
      <div className="w-8 h-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

// ── App shell with sidebar (authenticated pages) ────────────────────────────
function AppLayout() {
  // Initialise WebSocket connection once for all dashboard pages
  useWebSocket();
  return (
    <div className="flex min-h-screen bg-vantag-dark">
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

// ── Root App ────────────────────────────────────────────────────────────────
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Toaster
          position="top-right"
          toastOptions={{
            style: { background: '#1a1a2e', color: '#fff', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px' },
            success: { iconTheme: { primary: '#8b5cf6', secondary: '#fff' } },
          }}
        />
        <Suspense fallback={<Loading />}>
          <Routes>
            {/* Public */}
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/verify-email" element={<VerifyEmail />} />

            {/* Onboarding — auth required, no sidebar */}
            <Route path="/onboarding" element={<PrivateRoute><Onboarding /></PrivateRoute>} />

            {/* App shell — auth required, with sidebar + WebSocket */}
            <Route element={<PrivateRoute><AppLayout /></PrivateRoute>}>
              <Route path="/dashboard"              element={<Dashboard />} />
              <Route path="/cameras"               element={<CamerasPage />} />
              <Route path="/cameras/:storeId/:cameraId" element={<CameraView />} />
              <Route path="/incidents"  element={<IncidentsPage />} />
              <Route path="/watchlist"  element={<WatchlistPage />} />
              <Route path="/stores/:id" element={<StoreDetail />} />
            </Route>

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

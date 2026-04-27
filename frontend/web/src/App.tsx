import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import './i18n/index';
import Sidebar from './components/Sidebar';
import SupportChat from './components/SupportChat';
import { useWebSocket } from './hooks/useWebSocket';
import { useMQTT } from './hooks/useMQTT';

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
const ForgotPassword = lazy(() => import('./pages/auth/ForgotPassword'));
const ResetPassword  = lazy(() => import('./pages/auth/ResetPassword'));
const Onboarding   = lazy(() => import('./pages/onboarding/Onboarding'));
const Dashboard    = lazy(() => import('./pages/Dashboard'));
const CamerasPage   = lazy(() => import('./pages/CamerasPage'));
const CamerasManage = lazy(() => import('./pages/CamerasManage'));
const DemoCenter    = lazy(() => import('./pages/DemoCenter'));
const ZoneEditor    = lazy(() => import('./pages/ZoneEditorPage'));
const CameraView   = lazy(() => import('./pages/CameraView'));
const IncidentsPage = lazy(() => import('./pages/IncidentsPage'));
const WatchlistPage = lazy(() => import('./pages/WatchlistPage'));
const StoreDetail  = lazy(() => import('./pages/StoreDetail'));
const DownloadPage = lazy(() => import('./pages/DownloadPage'));
const HowItWorks   = lazy(() => import('./pages/HowItWorks'));
const FAQ          = lazy(() => import('./pages/FAQ'));
const HelpCenter   = lazy(() => import('./pages/HelpCenter'));
const HealthCheck  = lazy(() => import('./pages/HealthCheck'));

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
  // Initialise WebSocket + MQTT connections once for all dashboard pages
  useWebSocket();
  useMQTT();
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
            <Route path="/how-it-works" element={<HowItWorks />} />
            <Route path="/faq" element={<FAQ />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />

            {/* Onboarding — auth required, no sidebar */}
            <Route path="/onboarding" element={<PrivateRoute><Onboarding /></PrivateRoute>} />

            {/* App shell — auth required, with sidebar + WebSocket */}
            <Route element={<PrivateRoute><AppLayout /></PrivateRoute>}>
              <Route path="/dashboard"              element={<Dashboard />} />
              <Route path="/cameras"               element={<CamerasPage />} />
              <Route path="/cameras/manage"        element={<CamerasManage />} />
              <Route path="/demo"                  element={<DemoCenter />} />
              <Route path="/zone-editor"           element={<ZoneEditor />} />
              <Route path="/cameras/:storeId/:cameraId" element={<CameraView />} />
              <Route path="/incidents"  element={<IncidentsPage />} />
              <Route path="/watchlist"  element={<WatchlistPage />} />
              <Route path="/stores/:id" element={<StoreDetail />} />
              <Route path="/download"   element={<DownloadPage />} />
              <Route path="/help"       element={<HelpCenter />} />
              <Route path="/health-check" element={<HealthCheck />} />
            </Route>

            {/* Fallback */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
        <SupportChat />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

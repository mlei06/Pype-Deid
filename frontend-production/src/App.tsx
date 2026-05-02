import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ProductionShell from './components/layout/ProductionShell';
import LibraryView from './components/production/LibraryView';
import WorkspaceView from './components/production/WorkspaceView';
import SettingsView from './components/production/SettingsView';
import AuditView from './components/audit/AuditView';
import RequireDatasetParam from './components/production/RequireDatasetParam';
import {
  WorkspaceLegacyRedirect,
  SettingsLegacyRedirect,
} from './components/production/LegacyRedirects';
import { ConfirmProvider } from './components/shared/ConfirmDialog';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ConfirmProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<ProductionShell />}>
              <Route path="/" element={<Navigate to="/library" replace />} />
              <Route path="/library" element={<LibraryView />} />
              <Route path="/audit" element={<AuditView />} />

              <Route
                path="/datasets/:id/files"
                element={
                  <RequireDatasetParam>
                    <WorkspaceView />
                  </RequireDatasetParam>
                }
              />
              <Route
                path="/datasets/:id/detect"
                element={<Navigate to="../files" replace />}
              />
              <Route
                path="/datasets/:id/review"
                element={<Navigate to="../files" replace />}
              />
              <Route
                path="/datasets/:id/review/:fileId"
                element={<Navigate to="../../files" replace />}
              />
              <Route
                path="/datasets/:id/export"
                element={
                  <RequireDatasetParam>
                    <SettingsView />
                  </RequireDatasetParam>
                }
              />

              <Route path="/workspace" element={<WorkspaceLegacyRedirect />} />
              <Route path="/settings" element={<SettingsLegacyRedirect />} />
              <Route path="*" element={<Navigate to="/library" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ConfirmProvider>
    </QueryClientProvider>
  );
}

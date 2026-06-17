import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AdminAuthProvider, useAdminAuth } from "./lib/auth";
import Login from "./pages/Login";
import Layout from "./pages/Layout";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import KYC from "./pages/KYC";
import Transactions from "./pages/Transactions";
import Wallet from "./pages/Wallet";
import { Notifications, InvestmentManager, ContentManager, Reports, Settings } from "./pages/AdminExtras";
import AdminUsers from "./pages/AdminUsers";
import ApiManagement from "./pages/ApiManagement";
import AdminTravel from "./pages/AdminTravel";
import AdminInsurance from "./pages/AdminInsurance";
import AdminRewards from "./pages/AdminRewards";
import AdminAuditLogs from "./pages/AdminAuditLogs";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

function Protected({ children }: { children: JSX.Element }) {
  const { admin, loading } = useAdminAuth();
  if (loading) return <div className="h-screen grid place-items-center text-slate-500">Loading…</div>;
  if (!admin) return <Navigate to="/login" replace />;
  return children;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AdminAuthProvider>
        <HashRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Protected><Layout /></Protected>}>
              <Route index element={<Dashboard />} />
              <Route path="users" element={<Users />} />
              <Route path="kyc" element={<KYC />} />
              <Route path="transactions" element={<Transactions />} />
              <Route path="wallet" element={<Wallet />} />
              <Route path="notifications" element={<Notifications />} />
              <Route path="investments" element={<InvestmentManager />} />
              <Route path="content" element={<ContentManager />} />
              <Route path="reports" element={<Reports />} />
              <Route path="travel" element={<AdminTravel />} />
              <Route path="insurance" element={<AdminInsurance />} />
              <Route path="rewards" element={<AdminRewards />} />
              <Route path="audit" element={<AdminAuditLogs />} />
              <Route path="api-management" element={<ApiManagement />} />
              <Route path="settings" element={<Settings />} />
              <Route path="admins" element={<AdminUsers />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </HashRouter>
      </AdminAuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);

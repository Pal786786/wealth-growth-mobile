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
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </HashRouter>
      </AdminAuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);

import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Show, SignIn, SignUp, useAuth } from "@clerk/react";
import { useMemo } from "react";
import ClerkAuthProvider from "@/components/auth/ClerkAuthProvider";
import SelfHostAuthProvider from "@/components/auth/SelfHostAuthProvider";
import { MeProvider } from "@/lib/api";
import { AUTH_MODE, AuthBridge } from "@/lib/authContext";
import { Toaster } from "@/components/ui/sonner";
import Landing from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import Workspace from "@/pages/Workspace";
import Settings from "@/pages/Settings";
import Admin from "@/pages/Admin";
import LivePreview from "@/pages/LivePreview";

function ClerkBridge({ children }) {
  const { getToken, signOut } = useAuth();
  const value = useMemo(() => ({ getToken, signOut, email: "" }), [getToken, signOut]);
  return <AuthBridge.Provider value={value}>{children}</AuthBridge.Provider>;
}

const Protected = ({ children }) => (
  <>
    <Show when="signed-in"><MeProvider>{children}</MeProvider></Show>
    <Show when="signed-out"><Navigate to="/sign-in" replace /></Show>
  </>
);

const AuthPage = ({ children }) => (
  <div className="min-h-screen grid-lines flex items-center justify-center p-4">{children}</div>
);

function ClerkApp() {
  return (
    <ClerkAuthProvider>
      <ClerkBridge>
        <Routes>
          <Route path="/p/:id/live" element={<LivePreview />} />
          <Route path="/" element={<><Show when="signed-out"><Landing /></Show><Show when="signed-in"><MeProvider><Dashboard /></MeProvider></Show></>} />
          <Route path="/sign-in/*" element={<AuthPage><SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" withSignUp /></AuthPage>} />
          <Route path="/sign-up/*" element={<AuthPage><SignUp routing="path" path="/sign-up" signInUrl="/sign-in" /></AuthPage>} />
          <Route path="/p/:id" element={<Protected><Workspace /></Protected>} />
          <Route path="/settings" element={<Protected><Settings /></Protected>} />
          <Route path="/admin" element={<Protected><Admin /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ClerkBridge>
    </ClerkAuthProvider>
  );
}

function SelfHostApp() {
  return (
    <Routes>
      <Route path="/p/:id/live" element={<LivePreview />} />
      <Route path="*" element={
        <SelfHostAuthProvider>
          <MeProvider>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/p/:id" element={<Workspace />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/admin" element={<Admin />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </MeProvider>
        </SelfHostAuthProvider>
      } />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      {AUTH_MODE === "selfhost" ? <SelfHostApp /> : <ClerkApp />}
      <Toaster theme="dark" position="bottom-right" />
    </BrowserRouter>
  );
}

export default App;

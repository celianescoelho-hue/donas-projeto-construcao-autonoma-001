import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Show, SignIn, SignUp } from "@clerk/react";
import ClerkAuthProvider from "@/components/auth/ClerkAuthProvider";
import { MeProvider } from "@/lib/api";
import { Toaster } from "@/components/ui/sonner";
import Landing from "@/pages/Landing";
import Dashboard from "@/pages/Dashboard";
import Workspace from "@/pages/Workspace";
import Settings from "@/pages/Settings";
import Admin from "@/pages/Admin";
import LivePreview from "@/pages/LivePreview";

const Protected = ({ children }) => (
  <>
    <Show when="signed-in"><MeProvider>{children}</MeProvider></Show>
    <Show when="signed-out"><Navigate to="/sign-in" replace /></Show>
  </>
);

const AuthPage = ({ children }) => (
  <div className="min-h-screen grid-lines flex items-center justify-center p-4">{children}</div>
);

function App() {
  return (
    <BrowserRouter>
      <ClerkAuthProvider>
        <Routes>
          <Route path="/" element={<><Show when="signed-out"><Landing /></Show><Show when="signed-in"><MeProvider><Dashboard /></MeProvider></Show></>} />
          <Route path="/sign-in/*" element={<AuthPage><SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" withSignUp /></AuthPage>} />
          <Route path="/sign-up/*" element={<AuthPage><SignUp routing="path" path="/sign-up" signInUrl="/sign-in" /></AuthPage>} />
          <Route path="/p/:id/live" element={<LivePreview />} />
          <Route path="/p/:id" element={<Protected><Workspace /></Protected>} />
          <Route path="/settings" element={<Protected><Settings /></Protected>} />
          <Route path="/admin" element={<Protected><Admin /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <Toaster theme="dark" position="bottom-right" />
      </ClerkAuthProvider>
    </BrowserRouter>
  );
}

export default App;

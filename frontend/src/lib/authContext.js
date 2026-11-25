import { createContext, useContext } from "react";

export const AUTH_MODE = (process.env.REACT_APP_AUTH_MODE || "clerk").toLowerCase();

export const AuthBridge = createContext({ getToken: async () => null, signOut: () => {}, email: "" });
export const useAuthBridge = () => useContext(AuthBridge);

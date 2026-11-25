import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { useAuth } from "@clerk/react";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const errMsg = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg).join(", ");
  return e?.message || "Erro inesperado";
};

export function useApi() {
  const { getToken } = useAuth();
  return useMemo(() => {
    const inst = axios.create({ baseURL: API });
    inst.interceptors.request.use(async (c) => {
      const t = await getToken();
      if (t) c.headers.Authorization = `Bearer ${t}`;
      return c;
    });
    inst.token = getToken;
    return inst;
  }, [getToken]);
}

const MeContext = createContext(null);

export function MeProvider({ children }) {
  const api = useApi();
  const [me, setMe] = useState(null);
  const reload = useCallback(() => api.get("/me").then((r) => setMe(r.data)).catch(() => setMe(null)), [api]);
  useEffect(() => { reload(); }, [reload]);
  return <MeContext.Provider value={{ me, reload }}>{children}</MeContext.Provider>;
}

export const useMe = () => useContext(MeContext);

export async function streamChat(token, projectId, body, onEvent, signal) {
  const res = await fetch(`${API}/projects/${projectId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let msg = `Erro ${res.status}`;
    try {
      const d = (await res.json()).detail;
      if (Array.isArray(d)) msg = d.map((x) => x.msg || JSON.stringify(x)).join("; ");
      else if (d) msg = d;
    } catch {}
    if (res.status === 413) msg = "Mensagem grande demais. Anexe o conteúdo como arquivo (📎) em vez de colar no chat.";
    throw new Error(msg);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((x) => x.startsWith("data:"));
      if (!line) continue;
      try { onEvent(JSON.parse(line.slice(5))); } catch {}
    }
  }
}

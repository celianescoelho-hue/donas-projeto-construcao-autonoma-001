import { useEffect, useRef, useState } from "react";
import { RotateCw, Monitor, Smartphone, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

const PHONE_W = 375;
const PHONE_H = 812;
const BEZEL = 12;

function useFitScale(ref, active) {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    if (!active || !ref.current) return;
    const ro = new ResizeObserver(([e]) => {
      const { width, height } = e.contentRect;
      setScale(Math.min(1, (height - 32) / (PHONE_H + BEZEL * 2), (width - 32) / (PHONE_W + BEZEL * 2)));
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [ref, active]);
  return scale;
}

function DeviceToggle({ mode, setMode }) {
  const item = (m, Icon, label) => (
    <button onClick={() => setMode(m)} data-testid={`preview-${m}-btn`}
      className={`flex items-center gap-1.5 rounded-md px-2.5 h-6 text-[11px] font-medium transition-colors duration-150 ${mode === m ? "bg-primary text-white" : "text-muted-foreground hover:text-foreground"}`}>
      <Icon className="h-3.5 w-3.5" />{label}
    </button>
  );
  return (
    <div className="flex items-center gap-0.5 rounded-lg bg-secondary p-0.5" data-testid="preview-device-toggle">
      {item("desktop", Monitor, "Desktop")}
      {item("mobile", Smartphone, "Celular")}
    </div>
  );
}

export default function PreviewPanel({ html, building }) {
  const [key, setKey] = useState(0);
  const [mode, setMode] = useState("desktop");
  const [errors, setErrors] = useState(0);
  const stage = useRef(null);
  const scale = useFitScale(stage, mode === "mobile");
  useEffect(() => {
    const h = (e) => { if (e.origin === "null" && e.data?.donasLog?.level === "error") setErrors((n) => n + 1); };
    window.addEventListener("message", h);
    return () => window.removeEventListener("message", h);
  }, []);
  useEffect(() => { setErrors(0); }, [html, key]);
  const frame = <iframe key={key} title="Prévia" srcDoc={html} data-testid="preview-iframe" sandbox="allow-scripts allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer" className="h-full w-full bg-white border-0" />;

  return (
    <div className="h-full flex flex-col" data-testid="preview-panel">
      <div className="h-9 shrink-0 flex items-center gap-2 px-2 border-b">
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground px-1">Prévia</span>
        {building && <span className="h-1.5 w-1.5 rounded-full bg-primary pulse-dot" />}
        {errors > 0 && <span className="flex items-center gap-1 text-[11px] text-red-300 font-mono" data-testid="preview-errors"><AlertTriangle className="h-3 w-3" />{errors}</span>}
        <div className="ml-auto flex items-center gap-1">
          <DeviceToggle mode={mode} setMode={setMode} />
          <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setKey((k) => k + 1)} data-testid="preview-reload-btn"><RotateCw className="h-3.5 w-3.5" /></Button>
        </div>
      </div>
      <div ref={stage} className="flex-1 min-h-0 bg-[#111116] grid-lines relative overflow-hidden">
        {mode === "desktop" ? frame : (
          <div className="absolute left-1/2 top-1/2" style={{ transform: `translate(-50%, -50%) scale(${scale})` }}>
            <div className="relative rounded-[48px] bg-[#1b1b22] border border-white/10 shadow-[0_30px_80px_rgba(0,0,0,0.6)]"
              style={{ width: PHONE_W + BEZEL * 2, height: PHONE_H + BEZEL * 2, padding: BEZEL }} data-testid="preview-phone-frame">
              <div className="absolute left-1/2 -translate-x-1/2 top-[18px] h-[22px] w-[96px] rounded-full bg-black z-10" />
              <div className="h-full w-full rounded-[38px] overflow-hidden bg-white">{frame}</div>
            </div>
            <p className="text-center font-mono text-[11px] text-muted-foreground mt-3">{PHONE_W} × {PHONE_H} · Android / iOS</p>
          </div>
        )}
      </div>
    </div>
  );
}

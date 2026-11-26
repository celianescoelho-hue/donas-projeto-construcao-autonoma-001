# Iteration 13 UI setup: creates TEST_ fullstack project (backend /api/ping + router frontend). Usage: python iter12_ui_setup.py [create|delete <pid>]
import sys, subprocess, requests
from dotenv import load_dotenv
import os
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
tok = subprocess.run(["python", "/app/backend/tests/clerk_token.py", "forja.member+clerk_test@example.com"], capture_output=True, text=True).stdout.strip()
s = requests.Session(); s.headers["Authorization"] = "Bearer " + tok

SERVER = '''import os
from fastapi import FastAPI
app = FastAPI()
@app.get("/api/ping")
async def ping():
    return {"msg": "pong do backend UI", "db": os.environ.get("DB_NAME")}
'''
APP = '''import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
function Home(){
  const [m,setM]=useState("carregando");
  useEffect(()=>{fetch("/api/ping").then(r=>r.json()).then(d=>setM(d.msg)).catch(e=>setM("ERR "+e.message));},[]);
  return <div><h1 data-testid="home">Home page</h1><p id="msg">{m}</p><Link to="/sobre">sobre</Link></div>;
}
function Sobre(){ return <h1>Sobre page</h1>; }
export default function App(){
  return <BrowserRouter><Routes><Route path="/" element={<Home/>}/><Route path="/sobre" element={<Sobre/>}/></Routes></BrowserRouter>;
}
'''
if sys.argv[1] == "create":
    pid = s.post(f"{API}/projects", json={"name": "TEST_iter14_ui_fullstack"}).json()["id"]
    for p, c in [("backend/server.py", SERVER), ("backend/requirements.txt", "fastapi\nuvicorn\n"), ("frontend/src/App.js", APP)]:
        assert s.put(f"{API}/projects/{pid}/files", json={"path": p, "content": c}).status_code == 200
    s.patch(f"{API}/projects/{pid}", json={"public_preview": True})
    print(pid)
else:
    print(s.delete(f"{API}/projects/{sys.argv[2]}").status_code)

import sys
from datetime import datetime, timezone
from pathlib import Path
PROJECT_ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(PROJECT_ROOT))
from fastapi.testclient import TestClient
from api import app
def main():
 c=TestClient(app);t="2026-01-02T13:14:00+00:00";base={"instrument":"JARVIS","exchange":"NSE","token":"000001","timestamp":t}
 assert c.get("/health").json()["live_execution_supported"] is False and c.get("/api/v1/status").status_code==200;print("[PASS] Health Status")
 for route in ("/api/v1/analysis/market-context","/api/v1/analysis/underlying","/api/v1/analysis/full"):
  body=c.post(route,json=base).json();assert body["status"]=="OK" and "T" in body["result"]["started_at"]
 print("[PASS] Analysis API Serialization")
 assert c.post("/api/v1/analysis/full",json={"execution_mode":"LIVE","timestamp":t}).json()["code"]=="LIVE_EXECUTION_UNSUPPORTED";print("[PASS] Invalid Live Rejected")
 proposal={"instrument":"JARVIS","direction":"LONG","proposed_entry":"100","proposed_stop":"98","proposed_target":"104","capital_available":"100000","risk_per_trade_percent":"1","lot_size":25,"quantity_requested":125,"timestamp":datetime.now(timezone.utc).isoformat()}
 assert c.post("/api/v1/risk/validate",json=proposal).json()["status"]=="OK";assert c.post("/api/v1/risk/validate",json={}).status_code==400;print("[PASS] Risk Validation")
 assert c.post("/api/v1/paper/execute",json=proposal).json()["code"]=="AUTHORIZATION_REQUIRED";assert c.post("/api/v1/paper/execute",json={**proposal,"explicit_user_authorization":True}).json()["status"]=="OK";print("[PASS] Paper Authorization")
 assert c.get("/api/v1/portfolio").json()["status"]=="OK" and c.get("/api/v1/automation/jobs").json()["status"]=="OK" and c.get("/api/v1/automation/history").json()["status"]=="OK";assert c.post("/api/v1/automation/tick",json={"timestamp":t}).json()["status"]=="OK";assert c.post("/api/v1/backtest",json={}).json()["code"]=="INVALID_REQUEST";print("[PASS] Portfolio Automation Backtest")
 candles=[{"symbol":"RELIANCE","exchange":"NSE","timestamp":"2026-01-01T09:15:00+05:30","open":100,"high":102,"low":99,"close":101,"volume":1000,"source":"LOCAL_BACKTEST"}]
 backtest=c.post("/api/v1/backtest",json={"candles":candles,"warmup_candles":1}).json();result=backtest["result"]["backtest_result"];assert backtest["status"]=="OK" and result["execution_mode"]=="HISTORICAL_REPLAY" and result["metrics"]["total_trades"]==0
 assert c.post("/api/v1/backtest",json={"candles":[{**candles[0],"timestamp":"2026-01-01T09:15:00"}]}).status_code==400
 assert c.post("/api/v1/backtest",json={"candles":candles*2}).status_code==400
 assert c.post("/api/v1/backtest",json={"candles":[{**candles[0],"low":103}]}).status_code==400;print("[PASS] Historical Backtest Schema")
 assert c.post("/api/v1/backtest",json={"candles":candles*501}).json()["code"]=="RATE_LIMITED";print("[PASS] Request Size Guardrail")
 assert "ANGEL_ONE_API_KEY" not in str(c.post("/api/v1/analysis/full",json={"timestamp":t,"request_type":"FULL_ANALYSIS"}).json());print("[PASS] Safe Errors")
 return 0
if __name__=="__main__":sys.exit(main())
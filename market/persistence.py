import json, os, sqlite3
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import SimpleNamespace

SCHEMA_VERSION = 1
SECRET_KEYS=("angel_one_api_key","angel_one_client_code","angel_one_pin","angel_one_totp","access_token","refresh_token","authorization","session_token")
def encode(value):
    if is_dataclass(value): return {k:encode(v) for k,v in asdict(value).items()}
    if isinstance(value,(datetime,date)): return value.isoformat()
    if isinstance(value,time): return value.isoformat()
    if isinstance(value,timedelta): return {"seconds":value.total_seconds()}
    if isinstance(value,Decimal): return str(value)
    if isinstance(value,dict): return {k:encode(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [encode(v) for v in value]
    return value
def sanitize(value):
    if isinstance(value,dict):return {key:("<redacted>" if key.lower() in SECRET_KEYS else sanitize(item)) for key,item in value.items()}
    if isinstance(value,(tuple,list)):return [sanitize(item) for item in value]
    if isinstance(value,str):
        lowered=value.lower()
        if any(term in lowered for term in ("bearer ","authorization:","access_token=","refresh_token=","session_token=")):return "<redacted>"
    return value

class SQLiteStore:
    """Optional local store. Domain engines never call this class directly."""
    def __init__(self,path=None,observability=None):
        self.path=path or os.getenv("JARVIS_DB_PATH","data/jarvis.db"); parent=os.path.dirname(self.path)
        if parent: os.makedirs(parent,exist_ok=True)
        self.observability=observability;self.connection=sqlite3.connect(self.path);self.connection.row_factory=sqlite3.Row;self.initialize()
    def initialize(self):
        with self.connection:
            self.connection.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
            row=self.connection.execute("SELECT version FROM schema_version").fetchone()
            if not row:self.connection.execute("INSERT INTO schema_version VALUES (?)",(SCHEMA_VERSION,))
            elif row[0]!=SCHEMA_VERSION:raise ValueError("Unsupported SQLite schema version.")
            for table in ("orders","fills","positions","journal","automation_jobs","automation_runs","automation_occurrences","backtests","portfolio_snapshots","audit_events"):
                self.connection.execute(f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    def version(self): return self.connection.execute("SELECT version FROM schema_version").fetchone()[0]
    def save(self,table,identifier,value):
        try:
            with self.connection:self.connection.execute(f"INSERT INTO {table} VALUES (?,?)",(identifier,json.dumps(sanitize(encode(value)))))
        except sqlite3.IntegrityError as error:
            if self.observability:self.observability.counters["persistence_errors"]=self.observability.counters.get("persistence_errors",0)+1
            raise ValueError(f"Duplicate {table} ID.") from error
    def read_all(self,table):
        try:return [json.loads(row["payload"]) for row in self.connection.execute(f"SELECT payload FROM {table} ORDER BY id")]
        except (json.JSONDecodeError, TypeError) as error:raise ValueError("Malformed persisted record.") from error
    def get(self,table,identifier):
        row=self.connection.execute(f"SELECT payload FROM {table} WHERE id=?",(identifier,)).fetchone()
        if not row:return None
        try:return json.loads(row["payload"])
        except json.JSONDecodeError as error:raise ValueError("Malformed persisted record.") from error
    def update(self,table,identifier,value):
        with self.connection:
            if not self.connection.execute(f"UPDATE {table} SET payload=? WHERE id=?",(json.dumps(sanitize(encode(value))),identifier)).rowcount:raise ValueError(f"Unknown {table} ID.")
    def persist_paper_execution(self,order,fill,position,journal=None,fail_after_order=False):
        try:
            with self.connection:
                self.connection.execute("INSERT INTO orders VALUES (?,?)",(order.order_id,json.dumps(encode(order))))
                if fail_after_order: raise RuntimeError("Injected paper persistence failure.")
                self.connection.execute("INSERT INTO fills VALUES (?,?)",(fill.fill_id,json.dumps(encode(fill))))
                self.connection.execute("INSERT INTO positions VALUES (?,?)",(position.position_id,json.dumps(encode(position))))
                if journal:self.connection.execute("INSERT INTO journal VALUES (?,?)",(journal.position_id,json.dumps(encode(journal))))
        except sqlite3.IntegrityError as error:raise ValueError("Paper execution persistence failed.") from error
    def close(self): self.connection.close()

class Repository:
    table=""
    def __init__(self,store):self.store=store
    def save(self,identifier,value):self.store.save(self.table,identifier,value)
    def get(self,identifier):return self.store.get(self.table,identifier)
    def list(self):return self.store.read_all(self.table)
    def update(self,identifier,value):self.store.update(self.table,identifier,value)
class PaperOrderRepository(Repository):table="orders"
class PaperFillRepository(Repository):table="fills"
class PaperPositionRepository(Repository):table="positions"
class TradeJournalRepository(Repository):table="journal"
class AutomationJobRepository(Repository):table="automation_jobs"
class AutomationRunRepository(Repository):table="automation_runs"
class AutomationOccurrenceRepository(Repository):table="automation_occurrences"
class BacktestResultRepository(Repository):table="backtests"
class PortfolioSnapshotRepository(Repository):table="portfolio_snapshots"
class AuditEventRepository(Repository):table="audit_events"

class TypedRecordRepository(Repository):
    required=()
    modes=()
    def restore(self,identifier):
        data=self.get(identifier)
        if data is None:return None
        if any(key not in data for key in self.required):raise ValueError("Malformed persisted record.")
        if self.modes and data.get("execution_mode") not in self.modes:raise ValueError("Unsupported persisted execution mode.")
        for key in ("timestamp","start_timestamp","end_timestamp","created_at"):
            if key in data and data[key] is not None:
                try:
                    if datetime.fromisoformat(data[key]).tzinfo is None:raise ValueError
                except (TypeError,ValueError) as error:raise ValueError("Persisted timestamp must be timezone-aware.") from error
        return data
class TypedBacktestResultRepository(TypedRecordRepository):
    table="backtests";required=("instrument","start_timestamp","end_timestamp","starting_capital","ending_capital","metrics","execution_mode");modes=("HISTORICAL_REPLAY",)
    def restore_result(self,identifier):
        from market.backtest import BacktestConfig, BacktestMetrics, BacktestResult, BacktestTrade, EquityPoint
        data=self.restore(identifier); config=data.get("configuration"); metrics=data["metrics"]
        if not isinstance(config,dict) or not isinstance(metrics,dict):raise ValueError("Malformed persisted backtest record.")
        dt=lambda value:datetime.fromisoformat(value); dec=lambda value:Decimal(value) if value is not None else None
        try:
            configuration=BacktestConfig(config["warmup_candles"],dec(config["starting_capital"]),config["evaluation_frequency"],config["execution_timing"],config["same_candle_policy"],config["fees_enabled"],config["slippage_enabled"],config["close_at_end"])
            metric=BacktestMetrics(metrics["total_trades"],metrics["winning_trades"],metrics["losing_trades"],metrics["breakeven_trades"],dec(metrics["gross_profit"]),dec(metrics["gross_loss"]),dec(metrics["net_pnl"]),dec(metrics["win_rate"]),dec(metrics["average_win"]),dec(metrics["average_loss"]),dec(metrics["expectancy"]),dec(metrics["profit_factor"]),dec(metrics["maximum_drawdown"]),dec(metrics["maximum_drawdown_percent"]),dec(metrics["average_r_multiple"]),dec(metrics["total_return_percent"]))
            trades=tuple(BacktestTrade(item["instrument"],item["direction"],item["quantity"],dec(item["entry_price"]),dec(item["exit_price"]),dec(item["realized_pnl"]),item["exit_reason"],dec(item["r_multiple"]),dt(item["opened_at"]),dt(item["closed_at"]),item.get("execution_mode","HISTORICAL_REPLAY")) for item in data.get("trades",()))
            curve=tuple(EquityPoint(dt(item["timestamp"]),dec(item["cash"]),dec(item["unrealized_pnl"]),dec(item["total_equity"])) for item in data.get("equity_curve",()))
            return BacktestResult(data["instrument"],dt(data["start_timestamp"]),dt(data["end_timestamp"]),dec(data["starting_capital"]),dec(data["ending_capital"]),trades,curve,metric,configuration,data["source"],data["execution_mode"],data.get("data_status","HISTORICAL"))
        except (KeyError,TypeError,ValueError) as error:raise ValueError("Malformed persisted backtest record.") from error
class TypedPortfolioSnapshotRepository(TypedRecordRepository):
    table="portfolio_snapshots";required=("timestamp","execution_mode","total_equity","available_cash");modes=("PAPER","HISTORICAL_REPLAY")
    def restore_analysis(self,identifier):
        from market.portfolio import PortfolioAnalysis
        data=self.restore(identifier); decimals={"starting_capital","available_cash","capital_in_use","total_equity","realized_pnl","unrealized_pnl","total_pnl","total_return_percent","gross_exposure","long_exposure","short_exposure","net_exposure","gross_exposure_percent","net_exposure_percent","aggregate_initial_risk","current_portfolio_risk_percent","win_rate","average_win","average_loss","profit_factor","expectancy","current_drawdown","current_drawdown_percent","maximum_drawdown"}
        try:
            values=[]
            for name in PortfolioAnalysis.__dataclass_fields__:
                value=data[name]
                if name=="timestamp":value=datetime.fromisoformat(value)
                elif name in decimals and value is not None:value=Decimal(value)
                elif name in {"underlying_exposure","underlying_exposure_percent","sector_exposure","sector_exposure_percent","source_summary","observations"} and value is not None:value=tuple(tuple(item) if isinstance(item,list) else item for item in value)
                values.append(value)
            if values[1] not in self.modes:raise ValueError
            return PortfolioAnalysis(*values)
        except (KeyError,TypeError,ValueError) as error:raise ValueError("Malformed persisted portfolio snapshot.") from error
class TypedAuditEventRepository(TypedRecordRepository):
    table="audit_events";required=("timestamp","request_id","stage","status","message","execution_mode");modes=("ANALYSIS_ONLY","PAPER","HISTORICAL_REPLAY")

class PersistenceRestoreService:
    """State hydration only; it never invokes risk, strategies, brokers, or automation."""
    def __init__(self,store):self.store=store
    def restore_paper_account(self,starting_cash,available_cash=None,realized_pnl="0"):
        from market.paper_trading import PaperAccount, PaperPosition, TradeJournalEntry, VirtualFill, VirtualOrder
        account=PaperAccount(Decimal(str(starting_cash)),available_cash=Decimal(str(available_cash or starting_cash)),realized_pnl=Decimal(str(realized_pnl)))
        for data in self.store.read_all("positions"):
            required=("position_id","order_id","instrument","direction","quantity","entry_price","stop","target","opened_at","source")
            if any(key not in data for key in required):raise ValueError("Malformed persisted position.")
            opened=datetime.fromisoformat(data["opened_at"])
            if opened.tzinfo is None:raise ValueError("Persisted timestamp must be timezone-aware.")
            position=PaperPosition(data["position_id"],data["order_id"],data["instrument"],data["direction"],int(data["quantity"]),Decimal(data["entry_price"]),Decimal(data["stop"]),Decimal(data["target"]),opened,data["source"],data.get("status","OPEN"),Decimal(data["current_price"]) if data.get("current_price") is not None else None,Decimal(data.get("unrealized_pnl","0")),Decimal(data.get("realized_pnl","0")),datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None,Decimal(data["exit_price"]) if data.get("exit_price") is not None else None,data.get("exit_reason"),Decimal(data.get("reserved_capital","0")))
            (account.open_positions if position.status=="OPEN" else account.closed_positions)[position.position_id]=position
        for data in self.store.read_all("orders"):
            if data.get("execution_mode","PAPER")!="PAPER":raise ValueError("Unsupported persisted execution mode.")
            timestamp=datetime.fromisoformat(data["timestamp"])
            if timestamp.tzinfo is None:raise ValueError("Persisted timestamp must be timezone-aware.")
            account.order_history[data["order_id"]]=VirtualOrder(data["order_id"],data["instrument"],data["direction"],int(data["quantity"]),Decimal(data["requested_entry"]),Decimal(data["stop"]),Decimal(data["target"]),int(data["lot_size"]),timestamp,data["source"],data["status"],SimpleNamespace(**(data.get("risk_decision") or {})),data.get("evidence_reference"),"PAPER")
        for data in self.store.read_all("fills"):
            if data.get("execution_mode","PAPER")!="PAPER":raise ValueError("Unsupported persisted execution mode.")
            timestamp=datetime.fromisoformat(data["timestamp"])
            if timestamp.tzinfo is None:raise ValueError("Persisted timestamp must be timezone-aware.")
            account.fill_history[data["fill_id"]]=VirtualFill(data["fill_id"],data["order_id"],data["instrument"],data["direction"],int(data["quantity"]),Decimal(data["fill_price"]),timestamp,data["source"],data["fill_reason"],"PAPER")
        for data in self.store.read_all("journal"):
            if data.get("execution_mode","PAPER")!="PAPER":raise ValueError("Unsupported persisted execution mode.")
            opened,closed=datetime.fromisoformat(data["opened_at"]),datetime.fromisoformat(data["closed_at"])
            if opened.tzinfo is None or closed.tzinfo is None:raise ValueError("Persisted timestamp must be timezone-aware.")
            account.journal.append(TradeJournalEntry(data["order_id"],data["position_id"],data["instrument"],data["direction"],int(data["quantity"]),Decimal(data["entry_price"]),Decimal(data["exit_price"]),Decimal(data["stop"]),Decimal(data["target"]),Decimal(data["realized_pnl"]),opened,closed,data["exit_reason"],SimpleNamespace(**(data.get("risk_decision") or {})),data.get("evidence_reference"),data["source"],"PAPER"))
        account.unrealized_pnl=sum((position.unrealized_pnl for position in account.open_positions.values()),Decimal("0"))
        return account
    def restore_automation(self,controller):
        from core.automation import AutomationJob, AutomationRunResult
        from core.orchestrator import JarvisRequest
        for data in self.store.read_all("automation_jobs"):
            request=data["request_template"]; timestamp=datetime.fromisoformat(data["created_at"])
            if timestamp.tzinfo is None or data["execution_mode"] not in {"ANALYSIS_ONLY","PAPER","HISTORICAL_REPLAY"} or data["schedule_type"] not in {"ONCE","INTERVAL","DAILY_TIME"} or data["max_retries"]<0:raise ValueError("Malformed persisted automation job.")
            template=JarvisRequest(request["request_id"],request["request_type"],datetime.fromisoformat(request["timestamp"]),request.get("instrument"),request.get("exchange","NSE"),request.get("token"),request.get("interval","15m"),request.get("data_source","PROVIDER"),request.get("execution_mode","ANALYSIS_ONLY"),request.get("parameters"),request.get("explicit_user_authorization",False),request.get("source","AUTOMATION"))
            interval=data.get("interval"); daily=data.get("daily_time")
            controller.register(AutomationJob(data["job_id"],data["name"],data["job_type"],data["enabled"],data["execution_mode"],data["schedule_type"],template,timestamp,timedelta(seconds=interval["seconds"]) if interval else None,time.fromisoformat(daily) if daily else None,datetime.fromisoformat(data["last_run_at"]) if data.get("last_run_at") else None,datetime.fromisoformat(data["next_run_at"]) if data.get("next_run_at") else None,data["max_retries"],data["timeout_seconds"],data["requires_market_hours"],data["requires_user_authorization"],data["source"],data["max_instruments_per_run"],data["batch_size"],data["continue_on_error"]))
        runs=[]
        for data in self.store.read_all("automation_runs"):
            started,completed,occurrence=(datetime.fromisoformat(data[key]) for key in ("started_at","completed_at","occurrence"))
            if any(value.tzinfo is None for value in (started,completed,occurrence)) or data["execution_mode"]=="LIVE" or data["retry_count"]<0:raise ValueError("Malformed persisted automation run.")
            runs.append(AutomationRunResult(data["run_id"],data["job_id"],occurrence,started,completed,data["status"],None,(),tuple(data.get("warnings",())),tuple(data.get("errors",())),data["retry_count"],data["execution_mode"],data["source"],data.get("is_fresh")))
        occurrences=self.store.read_all("automation_occurrences")
        controller.hydrate_state(history=runs,occurrences=[item["key"] for item in occurrences if not item.get("retry_pending",False)],retries=[(item["key"],item.get("retry_count",0)) for item in occurrences])
        return controller
#!/usr/bin/env python3
"""Smart Healthcare Project Management System - backend (Python stdlib + SQLite).
Run:  python app.py [port]   -> opens http://127.0.0.1:8000"""
import sqlite3, json, os, sys, threading, webbrowser
from datetime import date, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("SHPM_DB", os.path.join(HERE, "shpm.db"))

SCHEMA = """
CREATE TABLE charter(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT NOT NULL,objectives TEXT,stakeholders TEXT,scope_boundaries TEXT,
 budget REAL NOT NULL CHECK(budget>0),deadline_weeks INTEGER NOT NULL CHECK(deadline_weeks>0),start_date TEXT NOT NULL,status_date TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'Planning',cpi_threshold REAL NOT NULL DEFAULT 0.95,spi_threshold REAL NOT NULL DEFAULT 0.95,closure_notes TEXT DEFAULT '');
CREATE TABLE plan(id INTEGER PRIMARY KEY CHECK(id=1),scope TEXT,schedule TEXT,cost TEXT,quality TEXT);
CREATE TABLE team(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,role TEXT NOT NULL);
CREATE TABLE requirements(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,priority TEXT NOT NULL DEFAULT 'Medium'
 CHECK(priority IN('Critical','High','Medium','Low')),status TEXT NOT NULL DEFAULT 'Proposed' CHECK(status IN('Proposed','Approved','Rejected')),
 source TEXT NOT NULL DEFAULT 'Original');
CREATE TABLE wbs(id INTEGER PRIMARY KEY AUTOINCREMENT,parent_id INTEGER REFERENCES wbs(id),code TEXT NOT NULL,name TEXT NOT NULL,
 req_id INTEGER NOT NULL REFERENCES requirements(id));
CREATE TABLE tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,wbs_id INTEGER NOT NULL REFERENCES wbs(id),
 assignee_id INTEGER REFERENCES team(id),duration INTEGER NOT NULL CHECK(duration>0),depends_on TEXT NOT NULL DEFAULT '',
 planned_cost REAL NOT NULL DEFAULT 0 CHECK(planned_cost>=0),actual_cost REAL NOT NULL DEFAULT 0 CHECK(actual_cost>=0),
 percent INTEGER NOT NULL DEFAULT 0 CHECK(percent BETWEEN 0 AND 100),delay_days INTEGER NOT NULL DEFAULT 0 CHECK(delay_days>=0));
CREATE TABLE milestones(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,due_date TEXT NOT NULL,owner_id INTEGER REFERENCES team(id),
 task_id INTEGER REFERENCES tasks(id),status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN('Pending','Achieved')));
CREATE TABLE change_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT,justification TEXT NOT NULL,
 cost_impact REAL NOT NULL DEFAULT 0 CHECK(cost_impact>=0),schedule_impact_weeks INTEGER NOT NULL DEFAULT 0 CHECK(schedule_impact_weeks>=0),
 status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN('Pending','Approved','Rejected')),req_id INTEGER REFERENCES requirements(id),decided_on TEXT);
CREATE TABLE defects(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,severity TEXT NOT NULL CHECK(severity IN('Critical','High','Medium','Low')),
 module TEXT,assignee_id INTEGER REFERENCES team(id),task_id INTEGER REFERENCES tasks(id),
 status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN('Open','In Progress','Resolved','Closed')));
CREATE TABLE checklist(id INTEGER PRIMARY KEY AUTOINCREMENT,deliverable TEXT NOT NULL,item TEXT NOT NULL,
 result TEXT NOT NULL DEFAULT 'Pending' CHECK(result IN('Pending','Pass','Fail')),notes TEXT,inspector_id INTEGER REFERENCES team(id));
CREATE TABLE risks(id INTEGER PRIMARY KEY AUTOINCREMENT,description TEXT NOT NULL,likelihood INTEGER NOT NULL CHECK(likelihood BETWEEN 1 AND 5),
 impact INTEGER NOT NULL CHECK(impact BETWEEN 1 AND 5),preventive TEXT,corrective TEXT);
"""
TABLES = "charter plan team requirements wbs tasks milestones change_requests defects checklist risks".split()

# (column, label, type, required) -- drives validation AND the GUI forms
SPEC = {
 'charter': [('name','Project name','text',1),('objectives','Objectives','area',1),('stakeholders','Stakeholders','area',1),
  ('scope_boundaries','Scope boundaries','area',1),('budget','Approved budget (PKR)','num',1),('deadline_weeks','Deadline (weeks)','int',1),
  ('start_date','Start date','date',1),('status_date','Status date','date',1),
  ('status','Project status','sel:Initiating|Planning|Executing|On Hold|Closed',1),('cpi_threshold','CPI warning threshold','num',1),
  ('spi_threshold','SPI warning threshold','num',1),('closure_notes','Closure notes','area',0)],
 'plan': [('scope','Scope plan','area',1),('schedule','Schedule plan','area',1),('cost','Cost plan','area',1),('quality','Quality plan','area',1)],
 'team': [('name','Name','text',1),('role','Role','text',1)],
 'milestones': [('name','Milestone','text',1),('due_date','Due date','date',1),('owner_id','Owner','ref:team',0),
  ('task_id','Linked activity','ref:tasks',0),('status','Status','sel:Pending|Achieved',1)],
 'requirements': [('title','Requirement','text',1),('priority','Priority','sel:Critical|High|Medium|Low',1),
  ('status','Status','sel:Proposed|Approved|Rejected',1)],
 'wbs': [('parent_id','Parent node','ref:wbs',0),('code','WBS code (auto if blank)','text',0),('name','Deliverable / work package','text',1),
  ('req_id','Requirement','ref:requirements',1)],
 'tasks': [('name','Activity','text',1),('wbs_id','WBS work package','ref:wbs',1),('assignee_id','Assignee','ref:team',0),
  ('duration','Duration (days)','int',1),('depends_on','Depends on (task ids, e.g. 3,4)','text',0),('planned_cost','Planned cost (PKR)','num',1),
  ('actual_cost','Actual cost (PKR)','num',0),('percent','% complete','int',0),('delay_days','Delay (days)','int',0)],
 'change_requests': [('title','Proposed change','text',1),('description','Description','area',0),('justification','Justification','area',1),
  ('cost_impact','Cost impact (PKR)','num',1),('schedule_impact_weeks','Schedule impact (weeks)','int',1)],
 'defects': [('title','Defect','text',1),('severity','Severity','sel:Critical|High|Medium|Low',1),('module','Module','text',0),
  ('assignee_id','Assigned to','ref:team',0),('task_id','Related activity','ref:tasks',0),
  ('status','Status','sel:Open|In Progress|Resolved|Closed',1)],
 'checklist': [('deliverable','Deliverable','text',1),('item','Checklist item','text',1),('result','Inspection result','sel:Pending|Pass|Fail',1),
  ('notes','Notes','text',0),('inspector_id','Inspector','ref:team',0)],
 'risks': [('description','Risk / problem','text',1),('likelihood','Likelihood (1-5)','int',1),('impact','Impact (1-5)','int',1),
  ('preventive','Preventive action','text',0),('corrective','Corrective action','text',0)],
}
LIMITS = {'percent':(0,100),'likelihood':(1,5),'impact':(1,5),'duration':(1,10000),'budget':(1,1e12),'deadline_weeks':(1,520),
          'cpi_threshold':(0.01,2),'spi_threshold':(0.01,2),'delay_days':(0,10000),'schedule_impact_weeks':(0,520)}

# ------------------------------------------------------------------ database
def connect(path=None):
    c = sqlite3.connect(path or DB); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    if not c.execute("select 1 from sqlite_master where name='charter'").fetchone(): reset(c)
    return c

def reset(c):
    c.executescript("PRAGMA foreign_keys=OFF;" + "".join(f"DROP TABLE IF EXISTS {t};" for t in TABLES) + SCHEMA)
    m = lambda sql, rows: c.executemany(sql, rows)
    c.execute("insert into charter values(1,?,?,?,?,?,?,?,?,?,?,?,?)", (
     "Smart Healthcare Project Management System",
     "Deliver an integrated system for 5 hospitals (appointments, lab reports, doctor schedules, online consultations, billing) in 16 weeks within PKR 5,000,000.",
     "Hospital management board (sponsor); 5 hospital administrators; doctors and lab staff; patients; software company PM and development team.",
     "In scope: appointments, lab reports, doctor schedules, online consultation, billing. Out of scope until approved via change control: AI diagnosis, mobile app.",
     5000000, 16, "2026-08-31", "2026-10-16", "Executing", 0.95, 0.95, ""))
    c.execute("insert into plan values(1,?,?,?,?)", (
     "Only approved requirements enter the WBS; changes go through the change-request process.",
     "16-week baseline, 9 activities with finish-to-start dependencies; delays tracked per activity.",
     "Baseline PKR 4,500,000 planned cost + PKR 500,000 reserve; EVM reviewed at each status date; warn when CPI/SPI < threshold.",
     "Defects tracked by severity; critical defects block closure; deliverable checklists inspected before sign-off."))
    m("insert into team(name,role) values(?,?)", [("Ayesha Khan","Project Manager"),("Bilal Ahmed","Backend Developer"),
      ("Hamza Riaz","Backend Developer"),("Sana Malik","Frontend Developer"),("Usman Tariq","Frontend Developer"),
      ("Imran Shah","Database Developer"),("Nida Farooq","QA Engineer")])
    m("insert into requirements(title,priority,status) values(?,?,'Approved')", [("Patient appointment management","Critical"),
      ("Patient record management and laboratory reports","Critical"),("Doctor schedules and online consultations","High"),
      ("Hospital billing","High"),("Multi-hospital web portal and access control","Medium"),("Project-level design, integration, testing, deployment","High")])
    m("insert into wbs(id,parent_id,code,name,req_id) values(?,?,?,?,?)", [
      (1,None,"1","Smart Healthcare System",6),(2,1,"1.1","Planning & Design",6),(3,2,"1.1.1","Requirements & Analysis",6),
      (4,2,"1.1.2","System Design & DB Schema",6),(5,1,"1.2","Core Modules",1),(6,5,"1.2.1","Appointment Scheduling",1),
      (7,5,"1.2.2","Patient Records & Lab Reports",2),(8,5,"1.2.3","Doctor Schedule & Online Consultation",3),(9,5,"1.2.4","Billing",4),
      (10,5,"1.2.5","Web Portal",5),(11,1,"1.3","Testing & Deployment",6),(12,11,"1.3.1","Integration & System Testing",6),
      (13,11,"1.3.2","UAT & Deployment",6)])
    m("insert into tasks(id,name,wbs_id,assignee_id,duration,depends_on,planned_cost,actual_cost,percent,delay_days) values(?,?,?,?,?,?,?,?,?,?)", [
      (1,"Requirements & Analysis",3,1,14,"",300000,310000,100,0),(2,"System Design & DB Schema",4,6,14,"1",400000,420000,100,0),
      (3,"Appointment Scheduling Module",6,2,21,"2",600000,520000,70,7),(4,"Patient Records & Lab Reports",7,3,21,"2",600000,600000,90,0),
      (5,"Doctor Schedule & Online Consultation",8,2,21,"2",600000,480000,80,0),(6,"Billing Module",9,3,14,"3,4",450000,0,0,0),
      (7,"Frontend Web Portal",10,4,28,"2",650000,300000,50,0),(8,"Integration & System Testing",12,7,14,"3,4,5,6,7",500000,0,0,0),
      (9,"UAT & Deployment",13,1,14,"8",400000,0,0,0)])
    m("insert into milestones(name,due_date,owner_id,task_id,status) values(?,?,?,?,?)", [
      ("Requirements signed off","2026-09-14",1,1,"Achieved"),("Design approved","2026-09-28",6,2,"Achieved"),
      ("Core modules complete","2026-11-02",2,6,"Pending"),("System testing complete","2026-11-16",7,8,"Pending"),("Go-live","2026-11-30",1,9,"Pending")])
    m("insert into defects(title,severity,module,assignee_id,task_id,status) values(?,?,?,?,?,?)", [
      ("Double booking of same doctor slot","Critical","Appointment scheduling",2,3,"Open"),
      ("Patient record overwritten on concurrent edit","Critical","Patient records",3,4,"In Progress"),
      ("Lab report PDF header misaligned","Low","Lab reports",4,4,"Resolved"),
      ("Slow appointment search (>5s)","Medium","Appointment scheduling",2,3,"Open")])
    m("insert into checklist(deliverable,item,result,notes,inspector_id) values(?,?,?,?,?)", [
      ("Requirements Specification","All requirements reviewed and signed by sponsor","Pass","Signed 14 Sep",1),
      ("Database Schema","Normalised to 3NF, constraints defined","Pass","",7),
      ("Appointment Module","No double booking under concurrent use","Fail","Critical defect #1",7),
      ("Appointment Module","Reminders sent to patients","Pending","",7),
      ("Patient Records","Record versioning prevents data loss","Fail","Critical defect #2",7),
      ("Billing Module","Invoice totals match tariff tables","Pending","",7)])
    m("insert into risks(description,likelihood,impact,preventive,corrective) values(?,?,?,?,?)", [
      ("Scope creep from new hospital requirements (AI module, mobile app)",5,4,"Formal change control; board approves every change","Re-baseline schedule and budget after approval"),
      ("Critical defects in appointment scheduling and patient records",4,5,"Code reviews, integration tests, QA gates","Dedicated fix sprint and regression suite"),
      ("Schedule delay propagates to go-live",4,4,"Weekly critical-path review","Fast-track or add overtime on critical activities"),
      ("Budget overrun (CPI below 1)",3,4,"Fortnightly earned value review","Use reserve; descope low-priority features"),
      ("Patient data privacy or security breach",2,5,"Role-based access, encryption, audit logs","Incident response plan; notify hospitals"),
      ("Key team member unavailable (small team)",3,3,"Cross-training and documentation","Reassign tasks or add contract developer"),
      ("Integration problems with hospital legacy systems",3,4,"Early interface prototypes","Build adapter layer; extend integration testing")])
    for t, d, j, cost, wk in [("AI-based preliminary diagnosis module","Symptom-based preliminary diagnosis to assist doctors","Requested by hospital management to reduce triage time",500000,2),
                              ("Mobile application for patients and doctors","Android/iOS app for appointments and reports","Requested by hospital management to improve patient access",300000,1)]:
        create_cr(c, dict(title=t, description=d, justification=j, cost_impact=cost, schedule_impact_weeks=wk))
    c.commit(); c.execute("PRAGMA foreign_keys=ON")

# ------------------------------------------------------------------ scheduling
def parse(s): return [int(x) for x in str(s or '').replace(' ', '').split(',') if x]

def compute(durs, deps):
    """Forward pass: {id:(start_offset,end_offset)} in days; raises ValueError on circular dependencies."""
    res, state = {}, {}
    def visit(i):
        if i in res: return res[i]
        if state.get(i) == 1: raise ValueError("Circular dependency detected between activities")
        state[i] = 1
        s = max([visit(d)[1] for d in deps[i] if d in durs], default=0)
        res[i] = (s, s + durs[i]); state[i] = 2
        return res[i]
    for i in durs: visit(i)
    return res

def load(c):
    ts = [dict(r) for r in c.execute("select * from tasks order by id")]
    return ts, {t['id']: parse(t['depends_on']) for t in ts}

def summary(c):
    ch = c.execute("select * from charter").fetchone()
    cost, wk = c.execute("select coalesce(sum(cost_impact),0),coalesce(sum(schedule_impact_weeks),0) from change_requests where status='Approved'").fetchone()
    ts, dp = load(c)
    cur = compute({t['id']: t['duration'] + t['delay_days'] for t in ts}, dp)
    sd = date.fromisoformat(ch['start_date']); end = max([e for _, e in cur.values()], default=0)
    q = lambda s: c.execute(s).fetchone()[0]
    return dict(approved_requirements=q("select count(*) from requirements where status='Approved'"), wbs_nodes=q("select count(*) from wbs"),
        activities=len(ts), planned_cost=sum(t['planned_cost'] for t in ts), baseline_budget=ch['budget'], approved_changes_cost=cost,
        budget=ch['budget'] + cost, baseline_weeks=ch['deadline_weeks'], deadline_weeks=ch['deadline_weeks'] + wk,
        deadline=(sd + timedelta(days=7 * (ch['deadline_weeks'] + wk))).isoformat(), projected_finish=(sd + timedelta(days=end)).isoformat())

def analysis(c):
    ch = c.execute("select * from charter").fetchone(); sm = summary(c)
    sd = date.fromisoformat(ch['start_date']); asof = (date.fromisoformat(ch['status_date']) - sd).days
    ts, dp = load(c); names = {t['id']: t['name'] for t in ts}
    base = compute({t['id']: t['duration'] for t in ts}, dp)
    cur = compute({t['id']: t['duration'] + t['delay_days'] for t in ts}, dp)
    succ = {i: [] for i in dp}
    for i, ds in dp.items():
        for d in ds:
            if d in succ: succ[d].append(i)
    def desc(i, seen):
        for s in succ[i]:
            if s not in seen: seen.add(s); desc(s, seen)
        return seen
    D = lambda n: (sd + timedelta(days=n)).isoformat()
    rows, pv, ev, ac, bac = [], 0.0, 0.0, 0.0, 0.0
    for t in ts:
        i = t['id']; b, k = base[i], cur[i]; cost = t['planned_cost']
        tpv = cost * min(1, max(0, (asof - b[0]) / (b[1] - b[0]))); tev = cost * t['percent'] / 100
        pv += tpv; ev += tev; ac += t['actual_cost']; bac += cost
        imp = sorted(names[j] for j in desc(i, set()) if cur[j][1] > base[j][1]) if t['delay_days'] > 0 else []
        rows.append(dict(id=i, name=t['name'], base_start=b[0], base_end=b[1], start=k[0], end=k[1], start_date=D(k[0]), end_date=D(k[1]),
            delay_days=t['delay_days'], slip=k[1] - b[1], pushed=t['delay_days'] == 0 and k[0] > b[0], impacted=imp, percent=t['percent'],
            cost=cost, pv=tpv, ev=tev, ac=t['actual_cost'], depends_on=dp[i]))
    be = max([r['base_end'] for r in rows], default=0); ce = max([r['end'] for r in rows], default=0)
    dl = sm['deadline_weeks'] * 7
    cpi = ev / ac if ac else None; spi = ev / pv if pv else None
    eac = bac / cpi if cpi else bac
    evm = dict(pv=pv, ev=ev, ac=ac, bac=bac, cpi=cpi, spi=spi, cv=ev - ac, sv=ev - pv, eac=eac, etc=eac - ac, vac=bac - eac,
               cpi_threshold=ch['cpi_threshold'], spi_threshold=ch['spi_threshold'], status_offset=asof)
    ms = []
    for r in c.execute("select * from milestones order by due_date"):
        p = cur[r['task_id']][1] if r['task_id'] in cur else (date.fromisoformat(r['due_date']) - sd).days
        due = (date.fromisoformat(r['due_date']) - sd).days
        ms.append(dict(dict(r), due_offset=due, projected_offset=p, projected_date=D(p), late_days=max(0, p - due) if r['status'] != 'Achieved' else 0))
    W = []
    w = lambda lv, m: W.append({'level': lv, 'msg': m})
    if cpi is not None and cpi < ch['cpi_threshold']:
        w('critical' if cpi < 0.85 else 'warning', f"COST OVERRUN: CPI {cpi:.2f} is below threshold {ch['cpi_threshold']:.2f} (cost variance PKR {ev-ac:,.0f})")
    if spi is not None and spi < ch['spi_threshold']:
        w('critical' if spi < 0.85 else 'warning', f"SCHEDULE DEVIATION: SPI {spi:.2f} is below threshold {ch['spi_threshold']:.2f} (schedule variance PKR {ev-pv:,.0f})")
    if eac > sm['budget']: w('critical', f"Forecast cost (EAC) PKR {eac:,.0f} exceeds approved budget PKR {sm['budget']:,.0f}")
    if bac > sm['budget']: w('critical', f"Planned cost PKR {bac:,.0f} exceeds approved budget PKR {sm['budget']:,.0f}")
    if ac > sm['budget']: w('critical', "Actual cost already exceeds the approved budget")
    if ce > be: w('warning', f"Delayed activities push the final finish by {ce-be} day(s) ({D(be)} -> {D(ce)})")
    if ce > dl: w('critical', f"Projected finish {D(ce)} is {ce-dl} day(s) after the deadline {D(dl)}")
    q = lambda s: c.execute(s).fetchone()[0]
    nc = q("select count(*) from defects where severity='Critical' and status in('Open','In Progress')")
    if nc: w('critical', f"{nc} unresolved critical defect(s)")
    for r in c.execute("select title from requirements where status='Approved' and id not in(select req_id from wbs)"):
        w('warning', f"Approved requirement not covered by the WBS: {r[0]}")
    npend = q("select count(*) from change_requests where status='Pending'")
    if npend: w('info', f"{npend} change request(s) awaiting a decision")
    return dict(tasks=rows, evm=evm, warnings=W, milestones=ms, summary=sm,
        project=dict(base_end=be, current_end=ce, deadline_offset=dl, finish_slip=ce - be, days_past_deadline=max(0, ce - dl),
                     start=ch['start_date'], base_finish=D(be), projected_finish=D(ce), deadline=D(dl)))

def dashboard(c):
    a = analysis(c); q = lambda s: [dict(r) for r in c.execute(s)]
    e = a['evm']; sm = a['summary']
    cl = {r['result']: r['n'] for r in c.execute("select result,count(*) n from checklist group by result")}
    return dict(summary=sm, evm=e, warnings=a['warnings'], project=a['project'], progress=round(100 * e['ev'] / e['bac'], 1) if e['bac'] else 0,
        budget=dict(approved=sm['budget'], planned=e['bac'], actual=e['ac'], remaining=sm['budget'] - e['ac']),
        pending_crs=q("select id,title,cost_impact,schedule_impact_weeks from change_requests where status='Pending'"),
        delayed=[t for t in a['tasks'] if t['delay_days'] > 0],
        critical_defects=q("select id,title,status from defects where severity='Critical' and status in('Open','In Progress')"),
        requirements={r['status']: r['n'] for r in c.execute("select status,count(*) n from requirements group by status")},
        checklist=cl, top_risks=q("select id,description,likelihood*impact score from risks order by score desc limit 3"),
        status=c.execute("select status from charter").fetchone()[0])

def wbs_tree(c):
    n = {r['id']: dict(dict(r), req=r['req'], children=[], tasks=[]) for r in
         c.execute("select w.*,r.title req from wbs w join requirements r on r.id=w.req_id order by w.code")}
    for t in c.execute("select id,name,wbs_id from tasks order by id"): n[t['wbs_id']]['tasks'].append(dict(t))
    roots = []
    for x in n.values(): (n[x['parent_id']]['children'] if x['parent_id'] in n else roots).append(x)
    return roots

# ------------------------------------------------------------------ validation / CRUD
def clean(c, t, d):
    o = {}
    for col, label, typ, req in SPEC[t]:
        v = d.get(col)
        if v is None or (isinstance(v, str) and not v.strip()):
            if req: raise ValueError(f"{label} is required")
            o[col] = None if typ.startswith('ref') else (0 if typ in ('int', 'num') else ''); continue
        try:
            if typ == 'int':
                if float(v) != int(float(v)): raise ValueError()
                v = int(float(v))
            elif typ == 'num': v = float(v)
        except (TypeError, ValueError): raise ValueError(f"{label} must be a valid number")
        if typ in ('int', 'num'):
            lo, hi = LIMITS.get(col, (0, 1e15))
            if not lo <= v <= hi: raise ValueError(f"{label} must be between {lo:g} and {hi:g}")
        if typ == 'date':
            try: date.fromisoformat(str(v))
            except ValueError: raise ValueError(f"{label} must be a valid date (YYYY-MM-DD)")
        if typ.startswith('sel:') and v not in typ[4:].split('|'): raise ValueError(f"{label} must be one of: {typ[4:].replace('|', ', ')}")
        if typ.startswith('ref:'):
            try: v = int(v)
            except (TypeError, ValueError): raise ValueError(f"{label} is invalid")
            if not c.execute(f"select 1 from {typ[4:]} where id=?", (v,)).fetchone(): raise ValueError(f"{label}: record {v} does not exist")
        o[col] = v.strip() if isinstance(v, str) else v
    return o

def gen_code(c, parent):
    pc = c.execute("select code from wbs where id=?", (parent,)).fetchone()[0] if parent else ''
    n = c.execute("select count(*) from wbs where parent_id is ?", (parent,)).fetchone()[0] + 1
    return f"{pc}.{n}" if pc else str(n)

def check(c, t, o, rid):
    q = lambda s, *a: c.execute(s, a).fetchone()
    if t == 'charter':
        if date.fromisoformat(o['status_date']) < date.fromisoformat(o['start_date']): raise ValueError("Status date cannot be before the start date")
        if o['status'] == 'Closed':
            if not o['closure_notes']: raise ValueError("Closure notes are required to close the project")
            if q("select count(*) from defects where severity='Critical' and status in('Open','In Progress')")[0]: raise ValueError("Cannot close: unresolved critical defects")
            if q("select count(*) from change_requests where status='Pending'")[0]: raise ValueError("Cannot close: pending change requests")
    if t == 'requirements' and rid:
        old = q("select * from requirements where id=?", rid)
        if o['status'] == 'Approved' and old['source'] != 'Original':
            cr = q("select status from change_requests where req_id=?", rid)
            if not cr or cr[0] != 'Approved': raise ValueError("A change-request requirement can only be approved by approving its change request")
        if o['status'] != 'Approved' and q("select count(*) from wbs where req_id=?", rid)[0]:
            raise ValueError("Requirement is already used in the WBS; remove those WBS items before un-approving it")
    if t == 'wbs':
        if q("select status from requirements where id=?", o['req_id'])[0] != 'Approved':
            raise ValueError("Unapproved requirements cannot be included in the project scope (WBS)")
        if rid and o['parent_id'] == rid: raise ValueError("A WBS node cannot be its own parent")
        if not o['code']: o['code'] = gen_code(c, o['parent_id'])
    if t == 'tasks':
        if q("select r.status from wbs w join requirements r on r.id=w.req_id where w.id=?", o['wbs_id'])[0] != 'Approved':
            raise ValueError("Activity is linked to an unapproved requirement")
        try: deps = parse(o['depends_on'])
        except ValueError: raise ValueError("Dependencies must be task ids separated by commas")
        ts, dp = load(c); durs = {x['id']: x['duration'] for x in ts}
        for d in deps:
            if d not in durs: raise ValueError(f"Dependency activity {d} does not exist")
            if d == rid: raise ValueError("An activity cannot depend on itself")
        k = rid or -1; durs[k] = o['duration'] + o['delay_days']; dp[k] = deps
        for x in ts:
            if x['id'] != k: durs[x['id']] += x['delay_days']
        compute(durs, dp)
        o['depends_on'] = ','.join(map(str, deps))
        total = q("select coalesce(sum(planned_cost),0) from tasks where id is not ?", rid)[0] + o['planned_cost']
        bud = summary(c)['budget']
        if total > bud: raise ValueError(f"Total planned cost PKR {total:,.0f} would exceed the approved budget PKR {bud:,.0f}")

def create_cr(c, o):
    cid = c.execute("insert into change_requests(title,description,justification,cost_impact,schedule_impact_weeks) values(?,?,?,?,?)",
        (o['title'], o['description'], o['justification'], o['cost_impact'], o['schedule_impact_weeks'])).lastrowid
    rid = c.execute("insert into requirements(title,priority,status,source) values(?,?,?,?)", (o['title'], 'High', 'Proposed', f'CR-{cid}')).lastrowid
    c.execute("update change_requests set req_id=? where id=?", (rid, cid)); return {'id': cid}

def decide(c, cid, status):
    cr = c.execute("select * from change_requests where id=?", (cid,)).fetchone()
    if not cr: raise ValueError("Change request not found")
    if cr['status'] != 'Pending': raise ValueError("This change request has already been decided")
    if status not in ('Approved', 'Rejected'): raise ValueError("Decision must be Approved or Rejected")
    before = summary(c)
    c.execute("update change_requests set status=?,decided_on=? where id=?", (status, date.today().isoformat(), cid))
    if status == 'Rejected':
        c.execute("update requirements set status='Rejected' where id=?", (cr['req_id'],))
    else:
        c.execute("update requirements set status='Approved' where id=?", (cr['req_id'],))
        g = c.execute("select id from wbs where name='Approved Change Requests'").fetchone()
        if g: gid = g[0]
        else:
            root = c.execute("select id,req_id from wbs where parent_id is null order by id").fetchone()
            pid = root['id'] if root else None
            gid = c.execute("insert into wbs(parent_id,code,name,req_id) values(?,?,?,?)",
                (pid, gen_code(c, pid), 'Approved Change Requests', root['req_id'] if root else cr['req_id'])).lastrowid
        wp = c.execute("insert into wbs(parent_id,code,name,req_id) values(?,?,?,?)", (gid, gen_code(c, gid), cr['title'], cr['req_id'])).lastrowid
        ts, dp = load(c)
        sinks = [t['id'] for t in ts if not any(t['id'] in d for d in dp.values())]
        c.execute("insert into tasks(name,wbs_id,duration,depends_on,planned_cost) values(?,?,?,?,?)",
            (cr['title'], wp, max(1, cr['schedule_impact_weeks'] * 7), ','.join(map(str, sinks)), cr['cost_impact']))
    return {'before': before, 'after': summary(c), 'status': status}

def rows(c, t):
    q = {'wbs': "select * from wbs order by code", 'risks': "select *,likelihood*impact score from risks order by score desc,id",
         'checklist': "select * from checklist order by deliverable,id"}.get(t, f"select * from {t} order by id")
    return [dict(r) for r in c.execute(q)]

def route(c, m, p, b):
    if p == ['schema']: return SPEC
    if p == ['reset'] and m == 'POST': reset(c); return {'ok': True}
    if p == ['analysis']: return analysis(c)
    if p == ['dashboard']: return dashboard(c)
    if p == ['wbs_tree']: return wbs_tree(c)
    if len(p) == 3 and p[0] == 'change_requests' and p[2] == 'decide' and m == 'POST': return decide(c, int(p[1]), b.get('status'))
    t = p[0] if p else ''
    if t not in SPEC: raise ValueError("Unknown resource")
    if t in ('charter', 'plan'):
        if m == 'GET': return dict(c.execute(f"select * from {t}").fetchone())
        o = clean(c, t, b); check(c, t, o, 1)
        c.execute(f"update {t} set " + ",".join(f"{k}=?" for k in o) + " where id=1", list(o.values())); return {'ok': True}
    if len(p) == 1 and m == 'GET': return rows(c, t)
    if len(p) == 1 and m == 'POST':
        o = clean(c, t, b); check(c, t, o, None)
        if t == 'change_requests': return create_cr(c, o)
        return {'id': c.execute(f"insert into {t}({','.join(o)}) values({','.join('?' * len(o))})", list(o.values())).lastrowid}
    rid = int(p[1])
    old = c.execute(f"select * from {t} where id=?", (rid,)).fetchone()
    if not old: raise ValueError("Record not found")
    if m == 'PUT':
        if t == 'change_requests' and old['status'] != 'Pending': raise ValueError("Only pending change requests can be edited")
        o = clean(c, t, b); check(c, t, o, rid)
        c.execute(f"update {t} set " + ",".join(f"{k}=?" for k in o) + " where id=?", list(o.values()) + [rid])
        if t == 'change_requests': c.execute("update requirements set title=? where id=?", (o['title'], old['req_id']))
        return {'ok': True}
    if m == 'DELETE':
        if t == 'tasks' and any(rid in d for i, d in load(c)[1].items() if i != rid): raise ValueError("Other activities depend on this activity")
        if t == 'change_requests':
            if old['status'] != 'Pending': raise ValueError("Only pending change requests can be deleted")
            c.execute("delete from change_requests where id=?", (rid,)); c.execute("delete from requirements where id=?", (old['req_id'],))
        else: c.execute(f"delete from {t} where id=?", (rid,))
        return {'ok': True}
    raise ValueError("Unsupported operation")

def call(c, m, p, b=None):
    """Transactional entry point used by the HTTP server and the tests."""
    try:
        r = route(c, m, p, b or {}); c.commit(); return r
    except sqlite3.IntegrityError:
        c.rollback(); raise ValueError("Operation rejected: record is in use by other records or violates a data constraint")
    except Exception:
        c.rollback(); raise

# ------------------------------------------------------------------ HTTP server
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ct="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def handle_any(self):
        path = self.path.split('?')[0]
        if not path.startswith('/api/'):
            return self.send(200, open(os.path.join(HERE, 'index.html'), 'rb').read(), 'text/html; charset=utf-8')
        n = int(self.headers.get('Content-Length') or 0)
        try: body = json.loads(self.rfile.read(n)) if n else {}
        except ValueError: return self.send(400, {'error': 'Invalid JSON'})
        c = connect()
        try: self.send(200, call(c, self.command, [x for x in path[5:].split('/') if x], body))
        except ValueError as e: self.send(400, {'error': str(e)})
        except Exception as e: self.send(500, {'error': 'Server error: ' + str(e)})
        finally: c.close()
    do_GET = do_POST = do_PUT = do_DELETE = handle_any

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    connect().close()
    srv = ThreadingHTTPServer(('127.0.0.1', port), H)
    print(f"Smart Healthcare PMS running at http://127.0.0.1:{port}  (Ctrl+C to stop)")
    threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
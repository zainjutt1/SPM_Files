BEGIN TRANSACTION;
CREATE TABLE change_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,description TEXT,justification TEXT NOT NULL,
 cost_impact REAL NOT NULL DEFAULT 0 CHECK(cost_impact>=0),schedule_impact_weeks INTEGER NOT NULL DEFAULT 0 CHECK(schedule_impact_weeks>=0),
 status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN('Pending','Approved','Rejected')),req_id INTEGER REFERENCES requirements(id),decided_on TEXT);
INSERT INTO "change_requests" VALUES(1,'AI-based preliminary diagnosis module','Symptom-based preliminary diagnosis to assist doctors','Requested by hospital management to reduce triage time',500000.0,2,'Pending',7,NULL);
INSERT INTO "change_requests" VALUES(2,'Mobile application for patients and doctors','Android/iOS app for appointments and reports','Requested by hospital management to improve patient access',300000.0,1,'Pending',8,NULL);
CREATE TABLE charter(id INTEGER PRIMARY KEY CHECK(id=1),name TEXT NOT NULL,objectives TEXT,stakeholders TEXT,scope_boundaries TEXT,
 budget REAL NOT NULL CHECK(budget>0),deadline_weeks INTEGER NOT NULL CHECK(deadline_weeks>0),start_date TEXT NOT NULL,status_date TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'Planning',cpi_threshold REAL NOT NULL DEFAULT 0.95,spi_threshold REAL NOT NULL DEFAULT 0.95,closure_notes TEXT DEFAULT '');
INSERT INTO "charter" VALUES(1,'Smart Healthcare Project Management System','Deliver an integrated system for 5 hospitals (appointments, lab reports, doctor schedules, online consultations, billing) in 16 weeks within PKR 5,000,000.','Hospital management board (sponsor); 5 hospital administrators; doctors and lab staff; patients; software company PM and development team.','In scope: appointments, lab reports, doctor schedules, online consultation, billing. Out of scope until approved via change control: AI diagnosis, mobile app.',5000000.0,16,'2026-08-31','2026-10-16','Executing',0.95,0.95,'');
CREATE TABLE checklist(id INTEGER PRIMARY KEY AUTOINCREMENT,deliverable TEXT NOT NULL,item TEXT NOT NULL,
 result TEXT NOT NULL DEFAULT 'Pending' CHECK(result IN('Pending','Pass','Fail')),notes TEXT,inspector_id INTEGER REFERENCES team(id));
INSERT INTO "checklist" VALUES(1,'Requirements Specification','All requirements reviewed and signed by sponsor','Pass','Signed 14 Sep',1);
INSERT INTO "checklist" VALUES(2,'Database Schema','Normalised to 3NF, constraints defined','Pass','',7);
INSERT INTO "checklist" VALUES(3,'Appointment Module','No double booking under concurrent use','Fail','Critical defect #1',7);
INSERT INTO "checklist" VALUES(4,'Appointment Module','Reminders sent to patients','Pending','',7);
INSERT INTO "checklist" VALUES(5,'Patient Records','Record versioning prevents data loss','Fail','Critical defect #2',7);
INSERT INTO "checklist" VALUES(6,'Billing Module','Invoice totals match tariff tables','Pending','',7);
CREATE TABLE defects(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,severity TEXT NOT NULL CHECK(severity IN('Critical','High','Medium','Low')),
 module TEXT,assignee_id INTEGER REFERENCES team(id),task_id INTEGER REFERENCES tasks(id),
 status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN('Open','In Progress','Resolved','Closed')));
INSERT INTO "defects" VALUES(1,'Double booking of same doctor slot','Critical','Appointment scheduling',2,3,'Open');
INSERT INTO "defects" VALUES(2,'Patient record overwritten on concurrent edit','Critical','Patient records',3,4,'In Progress');
INSERT INTO "defects" VALUES(3,'Lab report PDF header misaligned','Low','Lab reports',4,4,'Resolved');
INSERT INTO "defects" VALUES(4,'Slow appointment search (>5s)','Medium','Appointment scheduling',2,3,'Open');
CREATE TABLE milestones(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,due_date TEXT NOT NULL,owner_id INTEGER REFERENCES team(id),
 task_id INTEGER REFERENCES tasks(id),status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN('Pending','Achieved')));
INSERT INTO "milestones" VALUES(1,'Requirements signed off','2026-09-14',1,1,'Achieved');
INSERT INTO "milestones" VALUES(2,'Design approved','2026-09-28',6,2,'Achieved');
INSERT INTO "milestones" VALUES(3,'Core modules complete','2026-11-02',2,6,'Pending');
INSERT INTO "milestones" VALUES(4,'System testing complete','2026-11-16',7,8,'Pending');
INSERT INTO "milestones" VALUES(5,'Go-live','2026-11-30',1,9,'Pending');
CREATE TABLE plan(id INTEGER PRIMARY KEY CHECK(id=1),scope TEXT,schedule TEXT,cost TEXT,quality TEXT);
INSERT INTO "plan" VALUES(1,'Only approved requirements enter the WBS; changes go through the change-request process.','16-week baseline, 9 activities with finish-to-start dependencies; delays tracked per activity.','Baseline PKR 4,500,000 planned cost + PKR 500,000 reserve; EVM reviewed at each status date; warn when CPI/SPI < threshold.','Defects tracked by severity; critical defects block closure; deliverable checklists inspected before sign-off.');
CREATE TABLE requirements(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,priority TEXT NOT NULL DEFAULT 'Medium'
 CHECK(priority IN('Critical','High','Medium','Low')),status TEXT NOT NULL DEFAULT 'Proposed' CHECK(status IN('Proposed','Approved','Rejected')),
 source TEXT NOT NULL DEFAULT 'Original');
INSERT INTO "requirements" VALUES(1,'Patient appointment management','Critical','Approved','Original');
INSERT INTO "requirements" VALUES(2,'Patient record management and laboratory reports','Critical','Approved','Original');
INSERT INTO "requirements" VALUES(3,'Doctor schedules and online consultations','High','Approved','Original');
INSERT INTO "requirements" VALUES(4,'Hospital billing','High','Approved','Original');
INSERT INTO "requirements" VALUES(5,'Multi-hospital web portal and access control','Medium','Approved','Original');
INSERT INTO "requirements" VALUES(6,'Project-level design, integration, testing, deployment','High','Approved','Original');
INSERT INTO "requirements" VALUES(7,'AI-based preliminary diagnosis module','High','Proposed','CR-1');
INSERT INTO "requirements" VALUES(8,'Mobile application for patients and doctors','High','Proposed','CR-2');
CREATE TABLE risks(id INTEGER PRIMARY KEY AUTOINCREMENT,description TEXT NOT NULL,likelihood INTEGER NOT NULL CHECK(likelihood BETWEEN 1 AND 5),
 impact INTEGER NOT NULL CHECK(impact BETWEEN 1 AND 5),preventive TEXT,corrective TEXT);
INSERT INTO "risks" VALUES(1,'Scope creep from new hospital requirements (AI module, mobile app)',5,4,'Formal change control; board approves every change','Re-baseline schedule and budget after approval');
INSERT INTO "risks" VALUES(2,'Critical defects in appointment scheduling and patient records',4,5,'Code reviews, integration tests, QA gates','Dedicated fix sprint and regression suite');
INSERT INTO "risks" VALUES(3,'Schedule delay propagates to go-live',4,4,'Weekly critical-path review','Fast-track or add overtime on critical activities');
INSERT INTO "risks" VALUES(4,'Budget overrun (CPI below 1)',3,4,'Fortnightly earned value review','Use reserve; descope low-priority features');
INSERT INTO "risks" VALUES(5,'Patient data privacy or security breach',2,5,'Role-based access, encryption, audit logs','Incident response plan; notify hospitals');
INSERT INTO "risks" VALUES(6,'Key team member unavailable (small team)',3,3,'Cross-training and documentation','Reassign tasks or add contract developer');
INSERT INTO "risks" VALUES(7,'Integration problems with hospital legacy systems',3,4,'Early interface prototypes','Build adapter layer; extend integration testing');
CREATE TABLE tasks(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,wbs_id INTEGER NOT NULL REFERENCES wbs(id),
 assignee_id INTEGER REFERENCES team(id),duration INTEGER NOT NULL CHECK(duration>0),depends_on TEXT NOT NULL DEFAULT '',
 planned_cost REAL NOT NULL DEFAULT 0 CHECK(planned_cost>=0),actual_cost REAL NOT NULL DEFAULT 0 CHECK(actual_cost>=0),
 percent INTEGER NOT NULL DEFAULT 0 CHECK(percent BETWEEN 0 AND 100),delay_days INTEGER NOT NULL DEFAULT 0 CHECK(delay_days>=0));
INSERT INTO "tasks" VALUES(1,'Requirements & Analysis',3,1,14,'',300000.0,310000.0,100,0);
INSERT INTO "tasks" VALUES(2,'System Design & DB Schema',4,6,14,'1',400000.0,420000.0,100,0);
INSERT INTO "tasks" VALUES(3,'Appointment Scheduling Module',6,2,21,'2',600000.0,520000.0,70,7);
INSERT INTO "tasks" VALUES(4,'Patient Records & Lab Reports',7,3,21,'2',600000.0,600000.0,90,0);
INSERT INTO "tasks" VALUES(5,'Doctor Schedule & Online Consultation',8,2,21,'2',600000.0,480000.0,80,0);
INSERT INTO "tasks" VALUES(6,'Billing Module',9,3,14,'3,4',450000.0,0.0,0,0);
INSERT INTO "tasks" VALUES(7,'Frontend Web Portal',10,4,28,'2',650000.0,300000.0,50,0);
INSERT INTO "tasks" VALUES(8,'Integration & System Testing',12,7,14,'3,4,5,6,7',500000.0,0.0,0,0);
INSERT INTO "tasks" VALUES(9,'UAT & Deployment',13,1,14,'8',400000.0,0.0,0,0);
CREATE TABLE team(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,role TEXT NOT NULL);
INSERT INTO "team" VALUES(1,'Ayesha Khan','Project Manager');
INSERT INTO "team" VALUES(2,'Bilal Ahmed','Backend Developer');
INSERT INTO "team" VALUES(3,'Hamza Riaz','Backend Developer');
INSERT INTO "team" VALUES(4,'Sana Malik','Frontend Developer');
INSERT INTO "team" VALUES(5,'Usman Tariq','Frontend Developer');
INSERT INTO "team" VALUES(6,'Imran Shah','Database Developer');
INSERT INTO "team" VALUES(7,'Nida Farooq','QA Engineer');
CREATE TABLE wbs(id INTEGER PRIMARY KEY AUTOINCREMENT,parent_id INTEGER REFERENCES wbs(id),code TEXT NOT NULL,name TEXT NOT NULL,
 req_id INTEGER NOT NULL REFERENCES requirements(id));
INSERT INTO "wbs" VALUES(1,NULL,'1','Smart Healthcare System',6);
INSERT INTO "wbs" VALUES(2,1,'1.1','Planning & Design',6);
INSERT INTO "wbs" VALUES(3,2,'1.1.1','Requirements & Analysis',6);
INSERT INTO "wbs" VALUES(4,2,'1.1.2','System Design & DB Schema',6);
INSERT INTO "wbs" VALUES(5,1,'1.2','Core Modules',1);
INSERT INTO "wbs" VALUES(6,5,'1.2.1','Appointment Scheduling',1);
INSERT INTO "wbs" VALUES(7,5,'1.2.2','Patient Records & Lab Reports',2);
INSERT INTO "wbs" VALUES(8,5,'1.2.3','Doctor Schedule & Online Consultation',3);
INSERT INTO "wbs" VALUES(9,5,'1.2.4','Billing',4);
INSERT INTO "wbs" VALUES(10,5,'1.2.5','Web Portal',5);
INSERT INTO "wbs" VALUES(11,1,'1.3','Testing & Deployment',6);
INSERT INTO "wbs" VALUES(12,11,'1.3.1','Integration & System Testing',6);
INSERT INTO "wbs" VALUES(13,11,'1.3.2','UAT & Deployment',6);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('team',7);
INSERT INTO "sqlite_sequence" VALUES('requirements',8);
INSERT INTO "sqlite_sequence" VALUES('wbs',13);
INSERT INTO "sqlite_sequence" VALUES('tasks',9);
INSERT INTO "sqlite_sequence" VALUES('milestones',5);
INSERT INTO "sqlite_sequence" VALUES('defects',4);
INSERT INTO "sqlite_sequence" VALUES('checklist',6);
INSERT INTO "sqlite_sequence" VALUES('risks',7);
INSERT INTO "sqlite_sequence" VALUES('change_requests',2);
COMMIT;
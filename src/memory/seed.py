from __future__ import annotations

from src.memory.database import Database

CUSTOMERS = [
 ("CUST-101","Avery North","active","Pro","Gold","2023-02-10",0,1,"email"),
 ("CUST-102","Jordan Vale","active","Basic","Standard","2024-04-12",1,2,"email"),
 ("CUST-103","Morgan Cedar","inactive","Basic","Standard","2022-08-05",0,1,"phone"),
 ("CUST-104","Riley Quill","active","Enterprise","Platinum","2021-01-20",1,3,"email"),
 ("CUST-105","Casey Ember","active","Pro","Gold","2023-11-01",0,1,"chat"),
 ("CUST-106","Taylor Brook","active","Basic","Standard","2025-01-04",0,1,"email"),
 ("CUST-107","Skyler Finch","inactive","Pro","Gold","2020-06-14",2,0,"phone"),
 ("CUST-108","Quinn Harbor","active","Enterprise","Platinum","2022-09-30",0,1,"email"),
]
ORDERS = [
 ("ORD-501","CUST-101","120.00","2026-01-08","5","5.00","0",0),
 ("ORD-502","CUST-102","75.00","2025-11-01","12","0","0",0),
 ("ORD-503","CUST-103","49.00","2025-12-20","60","0","0",0),
 ("ORD-504","CUST-104","980.00","2026-01-02","8","20.00","0",0),
 ("ORD-505","CUST-105","180.00","2025-12-25","20","0","0",0),
 ("ORD-506","CUST-106","35.00","2026-01-10","0","0","0",0),
 ("ORD-507","CUST-107","225.00","2025-10-01","4","0","225.00",1),
 ("ORD-508","CUST-108","1500.00","2026-01-05","10","50.00","0",0),
 ("ORD-509","CUST-104","340.00","2025-12-24","24","10.00","0",0),
 ("ORD-510","CUST-102","60.00",None,None,"0","0",0),
]
CASES = [
 ("CASE-220","CUST-101","ORD-501","refund","Duplicate purchase","2026-01-14T06:00:00+00:00","open",1,"full refund","Please refund the duplicate charge."),
 ("CASE-221","CUST-102","ORD-502","refund","Old purchase","2026-01-12T10:00:00+00:00","open",2,"refund","I no longer need this."),
 ("CASE-222","CUST-103","ORD-503","refund","Heavy usage","2026-01-10T10:00:00+00:00","open",1,"refund","The product was not right for me."),
 ("CASE-223","CUST-105","ORD-505","refund","Within manual review window","2026-01-13T12:00:00+00:00","open",2,"partial refund","Could you review my request?"),
 ("CASE-224","CUST-107","ORD-507","refund","Previously refunded","2026-01-14T12:00:00+00:00","closed",1,"refund","I need another refund."),
 ("CASE-225","CUST-104","ORD-504","refund","High value repeated contact","2026-01-12T00:00:00+00:00","open",5,"full refund","URGENT: still waiting after several contacts."),
 ("CASE-226","CUST-106","ORD-506","complaint","Billing question","2026-01-15T08:00:00+00:00","open",1,"explanation","Please explain this charge."),
 ("CASE-227","CUST-108","ORD-508","refund","Enterprise high value","2026-01-14T00:00:00+00:00","open",2,"refund","This is urgent and blocking our team."),
 ("CASE-228","CUST-104","ORD-509","refund","Moderate usage","2026-01-13T00:00:00+00:00","open",3,"partial refund","Please review the amount."),
 ("CASE-229","CUST-102","ORD-510","refund","Missing purchase facts","2026-01-14T18:00:00+00:00","open",1,"refund","I cannot find the purchase details."),
]


def seed_database(db: Database) -> None:
    db.initialize()
    with db.connect() as conn:
        conn.executemany("INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?,?,?,?)", CUSTOMERS)
        conn.executemany("INSERT OR IGNORE INTO orders VALUES (?,?,?,?,?,?,?,?)", ORDERS)
        conn.executemany("INSERT OR IGNORE INTO cases VALUES (?,?,?,?,?,?,?,?,?,?)", CASES)
        conn.executemany("INSERT OR IGNORE INTO refund_policies VALUES (?,?,?)", [
            (1,"Standard refund policy","<=14 days and <=10% usage: eligible; 15-30 days and <=25%: manual review; otherwise not eligible."),
        ])
        conn.executemany("INSERT OR IGNORE INTO sla_rules VALUES (?,?)", [("Low",72),("Medium",48),("High",24)])


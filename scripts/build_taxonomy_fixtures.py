"""Generate backend/fixtures/taxonomy/*.json from compact lists (source of the platform taxonomy).

    python scripts/build_taxonomy_fixtures.py backend/fixtures/taxonomy

Line format: "Canonical Name|alias 1|alias 2". Bump VERSION when the data changes; then run
`python manage.py load_taxonomy` (idempotent, versioned).
"""

import json
import sys
from pathlib import Path

VERSION = "2026.11.1"

SKILLS = {
    "software_it": """
Python|py|python3
Java|java se|java ee|j2ee
JavaScript|JS|ECMAScript|ES6
TypeScript|TS
C|c language|ansi c
C++|cpp|c plus plus
C#|c sharp|csharp
Go|golang
Rust|rust lang
Kotlin
Swift
Objective-C|objc
PHP
Ruby
Scala
R|r language|r programming
MATLAB
Perl
Dart
Elixir
Haskell
Lua
Shell scripting|bash scripting|shell script
Bash|bourne again shell
PowerShell
SQL|structured query language
PL/SQL|plsql
T-SQL|tsql|transact-sql
HTML|html5
CSS|css3
Sass|scss
Tailwind CSS|tailwind|tailwindcss
Bootstrap|twitter bootstrap
React|ReactJS|React.js
Next.js|nextjs|next js
Angular|angularjs|angular js
Vue.js|vue|vuejs
Svelte
jQuery
Redux
Node.js|node|nodejs|node js
Express.js|express|expressjs
NestJS|nest.js
Django|django framework
Django REST Framework|DRF|django rest
Flask
FastAPI|fast api
Spring Boot|springboot
Spring Framework|spring
Hibernate
.NET|dotnet|.net framework
ASP.NET|asp.net core|aspnet
Entity Framework|ef core
Laravel
Symfony
Ruby on Rails|rails|RoR
Flutter
React Native|react-native
Android development|android sdk|android
iOS development|ios
Xamarin
Ionic
GraphQL
REST APIs|REST|RESTful APIs|restful
gRPC
WebSockets|websocket
OAuth 2.0|oauth|oauth2
OpenAPI|swagger
Microservices|microservice architecture
Event-driven architecture
Domain-driven design|DDD
Object-oriented programming|OOP
Functional programming
Design patterns
Data structures and algorithms|DSA|algorithms
Unit testing
Test-driven development|TDD
Behaviour-driven development|BDD|behavior-driven development
Integration testing
End-to-end testing|e2e testing
Pytest
JUnit
Jest
Cypress
Selenium
Playwright
Postman
Git|git version control
GitHub|github.com
GitLab
Bitbucket
Continuous integration|CI
Continuous delivery|CD|CI/CD|cicd
GitHub Actions
Jenkins
Docker|docker containers
Kubernetes|k8s
Helm
Terraform
Ansible
Linux|gnu/linux
Ubuntu
Windows Server
Nginx
Apache HTTP Server|apache
AWS|amazon web services
Amazon EC2|ec2
Amazon S3|s3
AWS Lambda|lambda
Microsoft Azure|azure
Google Cloud Platform|GCP|google cloud
Serverless
Cloud computing
PostgreSQL|Postgres|psql
MySQL
MariaDB
Microsoft SQL Server|MSSQL|SQL Server
Oracle Database|oracle db
SQLite
MongoDB|mongo
Redis
Elasticsearch|elastic search
Apache Kafka|kafka
RabbitMQ
Celery
Firebase
Database design|data modelling|data modeling
Database administration|DBA
Data engineering
ETL|extract transform load
Data warehousing
Apache Spark|spark|pyspark
Hadoop
Airflow|apache airflow
dbt|data build tool
Pandas
NumPy
Data analysis|data analytics
Data visualisation|data visualization|dataviz
Power BI|powerbi|microsoft power bi
Tableau
Looker
Business intelligence|BI
Statistics|statistical analysis
Machine learning|ML
Deep learning
Natural language processing|NLP
Computer vision
TensorFlow
PyTorch
scikit-learn|sklearn
Large language models|LLM|LLMs
MLOps
Data science
Cybersecurity|cyber security|information security|infosec
Network security
Penetration testing|pen testing|ethical hacking
Security operations|SOC
Identity and access management|IAM
ISO 27001
OWASP|owasp top 10
Firewall configuration|firewalls
Computer networking|networking
TCP/IP
CCNA|cisco ccna
Cisco networking
Routing and switching
VPN
Active Directory|AD
Microsoft 365|office 365|o365
System administration|sysadmin
IT support|technical support|helpdesk|help desk
ITIL
Virtualisation|virtualization|vmware
Hardware troubleshooting
Software development|software engineering|programming
Web development|web dev
Frontend development|front-end development|front end
Backend development|back-end development|back end
Full-stack development|full stack|fullstack
Mobile app development|mobile development
API design|api development
System design|systems design
Software architecture
DevOps
Site reliability engineering|SRE
Agile|agile methodology
Scrum
Kanban
Jira
Confluence
UI design|user interface design
UX design|user experience design|UX
Figma
Accessibility (WCAG)|wcag|web accessibility|a11y
Responsive web design|responsive design
Search engine optimisation|SEO|search engine optimization
WordPress
Drupal
ERP systems|erp
SAP
Odoo
Salesforce
Blockchain
Embedded systems
Internet of Things|IoT
Technical writing
Code review
Performance optimisation|performance optimization
Monitoring and observability|observability
Sentry
Prometheus
Grafana
USSD development|ussd
Mobile money integration|ecocash integration|paynow integration
""",
    "finance": """
Financial accounting
Management accounting
Bookkeeping|book keeping
Accounts payable|AP
Accounts receivable|AR
General ledger|GL
Bank reconciliation|bank reconciliations|reconciliations
Financial reporting
IFRS|international financial reporting standards
IPSAS|international public sector accounting standards
GAAP
Budgeting|budget preparation
Forecasting|financial forecasting
Financial analysis
Financial modelling|financial modeling
Cost accounting|costing
Payroll|payroll administration
Taxation|tax
Corporate tax
VAT|value added tax
PAYE|pay as you earn
ZIMRA compliance|zimra
Tax compliance
External audit
Internal audit
Audit|auditing
Risk management
Credit analysis
Credit control
Treasury management|treasury
Cash flow management|cash management
Working capital management
Investment analysis
Portfolio management
Corporate finance
Mergers and acquisitions|M&A
Valuation|business valuation
Banking operations|banking
Microfinance
Insurance underwriting|underwriting
Actuarial science|actuarial
Anti-money laundering|AML|AML/CFT
Know your customer|KYC
Regulatory compliance|compliance
Fixed asset management|fixed assets
Inventory accounting|stock control
Variance analysis
Month-end close|month end close|period close
Consolidation|financial consolidation
Pastel|sage pastel|pastel accounting
Sage|sage accounting
QuickBooks|quickbooks online
Xero
Microsoft Excel|Excel|MS Excel|advanced excel
VLOOKUP|xlookup
Pivot tables|pivot table
Grant financial management|donor funds accounting
Public financial management|PFM
Procurement accounting
Fraud investigation|forensic accounting
Multi-currency accounting|USD and ZWG accounting|multicurrency
Sarbanes-Oxley|SOX
Financial statements preparation|financial statements
""",
    "engineering": """
AutoCAD|auto cad
Civil 3D|autocad civil 3d
Revit
SolidWorks|solid works
CATIA
ANSYS
MATLAB Simulink|simulink
Structural engineering|structural design
Civil engineering
Mechanical engineering
Electrical engineering
Electronic engineering|electronics
Chemical engineering
Mechatronics
Process engineering
Industrial engineering
Geotechnical engineering
Water and wastewater engineering|water engineering
Road design|highway engineering
Surveying|land surveying
GIS|geographic information systems|ArcGIS|QGIS
Project management|PM
PRINCE2|prince 2
PMP|project management professional
Construction management
Quantity surveying|QS|bill of quantities
Site supervision
Health and safety|HSE|SHE|OHS|occupational health and safety
ISO 9001|quality management system
ISO 14001|environmental management system
ISO 45001
Maintenance planning|planned maintenance
Preventive maintenance
Reliability engineering
PLC programming|PLC|programmable logic controllers
SCADA
Instrumentation
HVAC
Electrical installation|electrical wiring
Power systems
Renewable energy
Solar PV installation|solar installation|solar pv
Transformer maintenance
Motor control
Welding|arc welding|mig welding|tig welding
Fabrication|metal fabrication
Machining|lathe operation|cnc machining
Hydraulics
Pneumatics
Diesel mechanics|diesel engine maintenance
Auto electrics|auto electrical
Plumbing
Building inspection
Technical drawing|engineering drawing
Material science
Root cause analysis|RCA
Lean manufacturing|lean
Six Sigma|lean six sigma
Total productive maintenance|TPM
Commissioning
Feasibility studies
Environmental impact assessment|EIA
Contract management|FIDIC
Estimating|cost estimating
Primavera P6|primavera
Microsoft Project|ms project
""",
    "health": """
Patient care
Nursing|registered nursing|general nursing
Midwifery
Clinical assessment|patient assessment
Triage
Wound care|wound management
Medication administration|drug administration
Infection prevention and control|IPC|infection control
Basic life support|BLS|CPR
Advanced cardiac life support|ACLS
Paediatric care|pediatric care|paediatrics
Maternal and child health|MCH
Antenatal care|ANC
Intensive care nursing|ICU nursing|critical care
Theatre nursing|operating theatre|perioperative nursing
Emergency care|emergency nursing
Mental health nursing|psychiatric nursing
Community health
Primary health care|PHC
HIV care and treatment|HIV management|ART
Tuberculosis management|TB care
Immunisation|immunization|vaccination
Health education|health promotion
Public health
Epidemiology
Health information systems|HMIS|DHIS2
Electronic medical records|EMR|EHR
Medical records management|health records
Pharmacy practice|pharmacy|dispensing
Clinical pharmacology
Laboratory testing|medical laboratory|lab testing
Phlebotomy
Radiography|x-ray
Physiotherapy|physical therapy
Nutrition and dietetics|nutrition|dietetics
Counselling|counseling
Palliative care
Geriatric care|elderly care
Home-based care
Health facility management|hospital administration
Clinical governance
Patient safety
Medical coding|ICD-10
Health insurance claims|medical aid claims
Biomedical equipment maintenance|biomedical engineering
Occupational health
Sterilisation|sterilization|CSSD
Quality improvement in healthcare|clinical audit
Research ethics
Clinical trials
Case management
""",
    "sales_marketing": """
Sales|selling
B2B sales|business to business sales
B2C sales|retail sales
Key account management|account management
Business development
Lead generation
Sales prospecting|prospecting|cold calling
Negotiation|negotiation skills
Sales forecasting
Customer relationship management|CRM
HubSpot
Customer service|customer care|customer support
Telesales|telemarketing
Merchandising
Retail management
Marketing|marketing strategy
Digital marketing|online marketing
Social media marketing|social media
Content marketing
Copywriting
Email marketing
Google Ads|adwords|ppc|pay per click
Facebook Ads|meta ads
Google Analytics|GA4
Brand management|branding
Market research
Product marketing
Public relations|PR
Event management|events
Graphic design
Adobe Photoshop|photoshop
Adobe Illustrator|illustrator
Canva
Video editing
Photography
Trade marketing
Channel management|distribution management
Pricing strategy
Campaign management
Community management
Influencer marketing
WhatsApp Business|whatsapp marketing
Customer experience|CX
Loyalty programmes|loyalty programs
""",
    "logistics": """
Supply chain management|SCM
Logistics management|logistics
Procurement|purchasing
Strategic sourcing
Vendor management|supplier management
Inventory management|inventory control
Warehouse management|warehousing
Warehouse management systems|WMS
Stores management|storekeeping
Fleet management
Transport management|transport planning
Route planning|route optimisation
Freight forwarding
Customs clearing|customs clearance
Import and export|import/export|international trade
Incoterms
Cold chain management|cold chain
Distribution
Demand planning
Production planning
Materials requirements planning|MRP
Order fulfilment|order fulfillment
Forklift operation|forklift
Heavy vehicle driving|class 2 driving|truck driving
Defensive driving
Dispatch management|dispatching
Tender management|tendering|bids
PRAZ procurement regulations|praz|public procurement
Contract negotiation
Shipping documentation
Stock taking|stocktake|cycle counting
Last-mile delivery
Reverse logistics
Barcode and RFID systems|barcoding|rfid
""",
    "education": """
Teaching|classroom teaching
Lesson planning
Curriculum development
Classroom management
Assessment and evaluation|student assessment
Early childhood development|ECD
Primary school teaching
Secondary school teaching
Special needs education|special education|SEN
Inclusive education
Mathematics teaching|maths teaching
Science teaching
English language teaching|ELT|TEFL
ZIMSEC syllabus|zimsec curriculum
Cambridge curriculum|cambridge igcse curriculum
Competence-based curriculum|CBC
E-learning|elearning|online learning
Learning management systems|LMS|moodle
Instructional design
Training delivery|training|facilitation
Training needs analysis|TNA
Mentoring
Coaching
Academic research
Research methods|research methodology
Educational leadership|school leadership
Student counselling|guidance and counselling
Adult education
Vocational training|TVET
Examinations administration|exam invigilation
""",
    "agriculture": """
Agronomy
Crop production|crop management
Horticulture
Irrigation management|irrigation
Soil science|soil management
Pest and disease management|pest control|IPM
Livestock production|animal husbandry
Dairy farming|dairy management
Poultry production|poultry farming
Beef cattle production|cattle ranching
Veterinary services|veterinary medicine
Animal health
Agricultural extension|extension services
Farm management
Agribusiness
Agricultural economics
Conservation agriculture
Climate-smart agriculture|CSA
Tobacco production|tobacco farming
Cotton production
Maize production
Seed production|seed multiplication
Fertiliser application|fertilizer application
Post-harvest handling|post harvest management
Agro-processing
Food safety|HACCP
Greenhouse management
Aquaculture|fish farming
Forestry
Natural resource management
Agricultural mechanisation|farm machinery
Value chain development|agricultural value chains
""",
    "mining": """
Mining engineering
Mine planning|mine design
Mine surveying
Geology|exploration geology
Mineral processing|metallurgical processing
Metallurgy|extractive metallurgy
Gold processing|gold metallurgy
Carbon-in-leach|CIL|CIP
Underground mining
Open pit mining|open cast mining|surface mining
Drilling and blasting|blasting
Explosives handling|blasting certificate
Mine ventilation|ventilation
Ground control|rock mechanics
Mine safety|mine health and safety
Mine rescue
Mine Health and Safety Act compliance|mining regulations
Ore reserve estimation|resource estimation
Grade control
Surpac|geovia surpac
Datamine
Leapfrog
Mineral exploration|mineral prospecting
Assaying|fire assay
Crushing and milling|comminution
Flotation
Tailings management|tailings dam
Heavy equipment operation|earthmoving equipment
Load haul dump|LHD operation
Shaft sinking
Environmental management in mining|mine rehabilitation
Platinum group metals processing|PGM
Lithium processing|lithium
Chrome mining
""",
    "ngo": """
Project cycle management|PCM
Monitoring and evaluation|M&E|MEAL
Logframe development|logical framework|logframe
Theory of change
Proposal writing|grant writing|fundraising proposals
Donor relations|donor management
Grants management|grant management
Community development
Community mobilisation|community mobilization
Stakeholder engagement
Humanitarian response|emergency response
Livelihoods programming|livelihoods
Food security
WASH|water sanitation and hygiene
Gender mainstreaming|gender and development
Child protection
Safeguarding|PSEA
Advocacy
Policy analysis
Capacity building
Participatory approaches|PRA
Data collection|survey design
KoboToolbox|kobo
ODK|open data kit
SPSS
Stata
NVivo
Qualitative research
Quantitative research
Report writing
USAID compliance|usaid rules and regulations
""",
    "business": """
Human resource management|HRM|HR
Recruitment|talent acquisition|recruiting
Interviewing|competency-based interviewing
Onboarding|induction
Employee relations
Labour law|labour act|labor law
Performance management
Learning and development|L&D
Compensation and benefits|reward management
HR information systems|HRIS
Organisational development|organizational development
Succession planning
Change management
Strategic planning|strategy
Business analysis|business analyst
Process improvement|business process improvement|BPM
Requirements gathering|requirements analysis
Operations management|operations
Office administration|administration
Executive assistance|personal assistance|PA
Records management|filing
Document control
Reception|front desk
Data entry
Minute taking|minutes
Diary management|calendar management
Microsoft Word|MS Word|word processing
Microsoft PowerPoint|PowerPoint|MS PowerPoint
Microsoft Outlook|outlook
Google Workspace|g suite|google docs
Corporate governance
Company secretarial|company secretary
Board administration
Policy development
Risk assessment
Business continuity planning|BCP
Quality assurance|QA
Customer complaints handling|complaints management
Facilities management
Security management
Hospitality management|hotel management
Food and beverage service|F&B
Housekeeping
Front office operations
Tourism management|tourism
Travel management
""",
    "legal": """
Contract drafting|drafting contracts
Legal research
Litigation
Conveyancing
Corporate law|commercial law
Labour relations|industrial relations
Legal compliance
Intellectual property|IP law
Data protection law|privacy law|CDPA compliance
Dispute resolution|arbitration|mediation
Due diligence|legal due diligence
Notary services|notary public
""",
    "language": """
English|english language
Shona|chishona
Ndebele|isindebele|sindebele
French
Portuguese
Swahili|kiswahili
Chinese (Mandarin)|mandarin
Zimbabwe Sign Language|sign language|ZSL
Tonga|chitonga
Venda|tshivenda
Kalanga
Afrikaans
""",
    "general": """
Communication|communication skills
Written communication|writing skills
Verbal communication|oral communication
Presentation skills|public speaking
Teamwork|team player|collaboration
Leadership
People management|team management|supervision
Problem solving|problem-solving
Critical thinking
Analytical skills|analytical thinking
Attention to detail
Time management
Organisational skills|organizational skills
Multitasking
Decision making
Conflict resolution
Emotional intelligence
Adaptability|flexibility
Initiative
Creativity|innovation
Interpersonal skills
Customer focus|customer orientation
Integrity|ethics
Report writing skills
Research skills
Computer literacy|computer skills|ICDL
Numeracy
Mentorship
Planning
Self-motivation|self motivated
""",
}

RELATIONS = [
    ("Django", "Python", "implies"),
    ("Django REST Framework", "Django", "implies"),
    ("Flask", "Python", "implies"),
    ("FastAPI", "Python", "implies"),
    ("Pandas", "Python", "implies"),
    ("NumPy", "Python", "implies"),
    ("Pytest", "Python", "implies"),
    ("scikit-learn", "Python", "implies"),
    ("PyTorch", "Python", "implies"),
    ("TensorFlow", "Python", "implies"),
    ("React", "JavaScript", "implies"),
    ("Next.js", "React", "implies"),
    ("Redux", "React", "implies"),
    ("React Native", "React", "implies"),
    ("Angular", "TypeScript", "implies"),
    ("Vue.js", "JavaScript", "implies"),
    ("Svelte", "JavaScript", "implies"),
    ("jQuery", "JavaScript", "implies"),
    ("Node.js", "JavaScript", "implies"),
    ("Express.js", "Node.js", "implies"),
    ("NestJS", "Node.js", "implies"),
    ("NestJS", "TypeScript", "implies"),
    ("TypeScript", "JavaScript", "implies"),
    ("Jest", "JavaScript", "implies"),
    ("Spring Boot", "Spring Framework", "implies"),
    ("Spring Framework", "Java", "implies"),
    ("Hibernate", "Java", "implies"),
    ("JUnit", "Java", "implies"),
    ("ASP.NET", ".NET", "implies"),
    (".NET", "C#", "related"),
    ("Entity Framework", ".NET", "implies"),
    ("Laravel", "PHP", "implies"),
    ("Symfony", "PHP", "implies"),
    ("WordPress", "PHP", "related"),
    ("Ruby on Rails", "Ruby", "implies"),
    ("Flutter", "Dart", "implies"),
    ("Kubernetes", "Docker", "related"),
    ("Helm", "Kubernetes", "implies"),
    ("Amazon EC2", "AWS", "narrower"),
    ("Amazon S3", "AWS", "narrower"),
    ("AWS Lambda", "AWS", "narrower"),
    ("AWS", "Cloud computing", "narrower"),
    ("Microsoft Azure", "Cloud computing", "narrower"),
    ("Google Cloud Platform", "Cloud computing", "narrower"),
    ("PostgreSQL", "SQL", "implies"),
    ("MySQL", "SQL", "implies"),
    ("MariaDB", "MySQL", "related"),
    ("Microsoft SQL Server", "SQL", "implies"),
    ("Oracle Database", "SQL", "implies"),
    ("T-SQL", "SQL", "narrower"),
    ("PL/SQL", "SQL", "narrower"),
    ("SQLite", "SQL", "implies"),
    ("Full-stack development", "Frontend development", "broader"),
    ("Full-stack development", "Backend development", "broader"),
    ("Frontend development", "Web development", "narrower"),
    ("Backend development", "Software development", "narrower"),
    ("Web development", "Software development", "narrower"),
    ("Mobile app development", "Software development", "narrower"),
    ("Android development", "Mobile app development", "narrower"),
    ("iOS development", "Mobile app development", "narrower"),
    ("Scrum", "Agile", "narrower"),
    ("Kanban", "Agile", "narrower"),
    ("Continuous delivery", "Continuous integration", "related"),
    ("GitHub Actions", "Continuous integration", "implies"),
    ("Jenkins", "Continuous integration", "implies"),
    ("GitHub", "Git", "implies"),
    ("GitLab", "Git", "implies"),
    ("Bitbucket", "Git", "implies"),
    ("Test-driven development", "Unit testing", "implies"),
    ("Deep learning", "Machine learning", "narrower"),
    ("Natural language processing", "Machine learning", "narrower"),
    ("Computer vision", "Machine learning", "narrower"),
    ("Machine learning", "Data science", "related"),
    ("Power BI", "Data visualisation", "implies"),
    ("Tableau", "Data visualisation", "implies"),
    ("Penetration testing", "Cybersecurity", "narrower"),
    ("Network security", "Cybersecurity", "narrower"),
    ("CCNA", "Computer networking", "implies"),
    ("Routing and switching", "Computer networking", "narrower"),
    ("Pivot tables", "Microsoft Excel", "implies"),
    ("VLOOKUP", "Microsoft Excel", "implies"),
    ("IFRS", "Financial reporting", "related"),
    ("Financial statements preparation", "Financial reporting", "related"),
    ("Pastel", "Bookkeeping", "related"),
    ("QuickBooks", "Bookkeeping", "related"),
    ("Xero", "Bookkeeping", "related"),
    ("Corporate tax", "Taxation", "narrower"),
    ("VAT", "Taxation", "narrower"),
    ("PAYE", "Taxation", "narrower"),
    ("Internal audit", "Audit", "narrower"),
    ("External audit", "Audit", "narrower"),
    ("Civil 3D", "AutoCAD", "related"),
    ("PRINCE2", "Project management", "implies"),
    ("PMP", "Project management", "implies"),
    ("Midwifery", "Nursing", "related"),
    ("Intensive care nursing", "Nursing", "narrower"),
    ("Theatre nursing", "Nursing", "narrower"),
    ("Mental health nursing", "Nursing", "narrower"),
    ("Advanced cardiac life support", "Basic life support", "implies"),
    ("Social media marketing", "Digital marketing", "narrower"),
    ("Google Ads", "Digital marketing", "narrower"),
    ("Email marketing", "Digital marketing", "narrower"),
    ("Key account management", "Sales", "narrower"),
    ("Warehouse management systems", "Warehouse management", "implies"),
    ("Strategic sourcing", "Procurement", "narrower"),
    ("Carbon-in-leach", "Gold processing", "narrower"),
    ("Gold processing", "Mineral processing", "narrower"),
    ("Flotation", "Mineral processing", "narrower"),
    ("Open pit mining", "Mining engineering", "narrower"),
    ("Underground mining", "Mining engineering", "narrower"),
    ("Recruitment", "Human resource management", "narrower"),
    ("Performance management", "Human resource management", "narrower"),
]

QUALIFICATION_LEVELS = [
    ("ZW_GRADE7", "Grade 7 certificate", 10, "ZW", ["grade 7", "primary school certificate"]),
    (
        "ZW_OLEVEL",
        "ZIMSEC O-Level",
        20,
        "ZW",
        [
            "O-Level",
            "O Level",
            "Ordinary Level",
            "5 O' Levels",
            "5 O Levels",
            "ZJC O-Level",
            "ZIMSEC Ordinary Level",
        ],
    ),
    ("INTL_IGCSE", "Cambridge IGCSE / O-Level", 20, "INTL", ["IGCSE", "Cambridge O Level", "GCSE"]),
    (
        "ZW_ALEVEL",
        "ZIMSEC A-Level",
        30,
        "ZW",
        ["A-Level", "A Level", "Advanced Level", "2 A Levels", "ZIMSEC Advanced Level"],
    ),
    (
        "INTL_AS_A",
        "Cambridge AS / A Level",
        30,
        "INTL",
        ["AS Level", "Cambridge A Level", "Cambridge AS"],
    ),
    (
        "ZW_CERT",
        "Certificate (vocational)",
        35,
        "ZW",
        ["Certificate", "Skills certificate", "Trade test", "Journeyman"],
    ),
    ("ZW_NC", "National Certificate (NC)", 40, "ZW", ["NC", "National Certificate"]),
    ("ZW_ND", "National Diploma (ND)", 50, "ZW", ["ND", "National Diploma", "Diploma"]),
    ("ZW_HND", "Higher National Diploma (HND)", 60, "ZW", ["HND", "Higher National Diploma"]),
    (
        "BACHELOR",
        "Bachelor's degree",
        70,
        "INTL",
        [
            "Bachelor",
            "Bachelors",
            "BSc",
            "B.Sc",
            "BA",
            "B.A",
            "BCom",
            "B.Com",
            "BEng",
            "B.Eng",
            "B.Tech",
            "BTech",
            "BBA",
            "LLB",
            "MBChB",
            "Degree",
            "Undergraduate degree",
            "Bachelor of Science",
            "Bachelor of Arts",
            "Bachelor of Commerce",
        ],
    ),
    (
        "HONOURS",
        "Bachelor's degree (Honours)",
        75,
        "INTL",
        [
            "Honours",
            "Hons",
            "BSc Hons",
            "BSc (Hons)",
            "BA Hons",
            "BCom Hons",
            "BEng Hons",
            "Honours degree",
        ],
    ),
    (
        "PGDIP",
        "Postgraduate Diploma",
        80,
        "INTL",
        ["PGD", "PGDip", "Postgraduate Diploma", "Graduate Diploma"],
    ),
    (
        "MASTERS",
        "Master's degree",
        90,
        "INTL",
        [
            "Masters",
            "Master's",
            "MSc",
            "M.Sc",
            "MA",
            "MBA",
            "MPhil",
            "MEng",
            "LLM",
            "MPH",
            "Master of Science",
            "Master of Business Administration",
        ],
    ),
    (
        "PHD",
        "Doctorate (PhD)",
        100,
        "INTL",
        ["PhD", "Ph.D", "DPhil", "Doctorate", "Doctor of Philosophy"],
    ),
]

PROFESSIONAL_BODIES = [
    (
        "ACCA",
        "Association of Chartered Certified Accountants",
        "GB",
        ["ACCA", "FCCA", "Chartered Certified Accountant"],
    ),
    ("CIMA", "Chartered Institute of Management Accountants", "GB", ["ACMA", "CGMA", "FCMA"]),
    (
        "ICAZ",
        "Institute of Chartered Accountants of Zimbabwe",
        "ZW",
        ["CA(Z)", "Chartered Accountant (Zimbabwe)"],
    ),
    ("CIS", "Chartered Governance Institute (ICSAZ)", "ZW", ["CIS", "Chartered Secretary"]),
    ("CIPS", "Chartered Institute of Procurement & Supply", "GB", ["MCIPS", "FCIPS"]),
    ("IODZ", "Institute of Directors Zimbabwe", "ZW", ["IoDZ member"]),
    ("ECZ", "Engineering Council of Zimbabwe", "ZW", ["Registered Engineer", "Pr.Eng"]),
    ("ZIE", "Zimbabwe Institution of Engineers", "ZW", ["MZIE", "FZIE"]),
    (
        "NCZ",
        "Nursing Council of Zimbabwe",
        "ZW",
        ["Registered General Nurse", "RGN", "State Certified Nurse", "Registered Midwife"],
    ),
    (
        "MDPCZ",
        "Medical and Dental Practitioners Council of Zimbabwe",
        "ZW",
        ["Registered Medical Practitioner"],
    ),
    ("PCZ", "Pharmacists Council of Zimbabwe", "ZW", ["Registered Pharmacist"]),
    ("LSZ", "Law Society of Zimbabwe", "ZW", ["Registered Legal Practitioner", "Attorney"]),
    ("IPMZ", "Institute of People Management of Zimbabwe", "ZW", ["MIPMZ", "IPMZ Diploma"]),
    ("CILT", "Chartered Institute of Logistics and Transport", "GB", ["MCILT"]),
    ("IIA", "Institute of Internal Auditors", "US", ["CIA", "Certified Internal Auditor"]),
    ("ISACA", "ISACA", "US", ["CISA", "CISM", "CRISC"]),
    ("PMI", "Project Management Institute", "US", ["PMP", "CAPM"]),
    ("ZIQS", "Zimbabwe Institute of Quantity Surveyors", "ZW", ["MZIQS"]),
    ("CMA", "Chartered Institute of Marketing", "GB", ["MCIM", "CIM Diploma"]),
    ("IBZ", "Institute of Bankers of Zimbabwe", "ZW", ["AIBZ", "Diploma in Banking"]),
]


def parse(block: str, category: str) -> list[dict]:
    out = []
    for line in block.strip().splitlines():
        parts = [p.strip() for p in line.split("|") if p.strip()]
        out.append({"name": parts[0], "category": category, "aliases": parts[1:]})
    return out


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/fixtures/taxonomy")
    skills = [s for cat, block in SKILLS.items() for s in parse(block, cat)]
    names = [s["name"].lower() for s in skills]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, dupes
    seen_alias: dict[str, str] = {}
    conflicts = []
    for s in skills:
        for a in [s["name"], *s["aliases"]]:
            key = a.lower()
            if seen_alias.get(key, s["name"]) != s["name"]:
                conflicts.append((a, seen_alias[key], s["name"]))
            seen_alias.setdefault(key, s["name"])
    assert not conflicts, "\n".join(map(str, conflicts))
    canon = {s["name"] for s in skills}
    for a, b, _ in RELATIONS:
        assert a in canon and b in canon, (a, b)
    out.mkdir(parents=True, exist_ok=True)
    (out / "skills.json").write_text(
        json.dumps(
            {
                "version": VERSION,
                "skills": skills,
                "relations": [{"from": a, "to": b, "relation": r} for a, b, r in RELATIONS],
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "qualifications.json").write_text(
        json.dumps(
            {
                "version": VERSION,
                "levels": [
                    {"code": c, "name": n, "rank": r, "framework": f, "aliases": al}
                    for c, n, r, f, al in QUALIFICATION_LEVELS
                ],
                "professional_bodies": [
                    {"code": c, "name": n, "country": co, "designations": d}
                    for c, n, co, d in PROFESSIONAL_BODIES
                ],
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    by_cat = {}
    for s in skills:
        by_cat[s["category"]] = by_cat.get(s["category"], 0) + 1
    print(len(skills), "skills", by_cat, len(RELATIONS), "relations")


if __name__ == "__main__":
    main()

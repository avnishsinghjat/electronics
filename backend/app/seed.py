"""Seed data so a fresh install is not empty.

Reference data (always needed): inventory locations and the default production stage
template. Sample data (flagged ``is_sample=True`` and labelled "Sample"): 2 divisions,
3 projects, 4 modules, 5 PCB assemblies, 60 parts and 5 vendors, plus one sample BOQ
(revision A released, revision B a draft with changes, so compare has something to show).
Vendor names, cities and GSTINs are invented for demonstration; they do not identify real
companies.

Idempotent: running it again adds nothing.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.core.models import utcnow
from app.core.numbering import next_number
from app.modules.boq.importer import split_ref_des
from app.modules.boq.models import Boq, BoqLine, BoqRevision, RevisionStatus
from app.modules.inventory.models import InventoryLocation, LocationKind
from app.modules.org.models import Division, Module, PcbAssembly, Project, ProjectStatus
from app.modules.parts.models import Part, PartCategory, PartPreferredVendor
from app.modules.procurement.models import Vendor
from app.modules.production.models import DEFAULT_STAGES, StageTemplate, StageTemplateStep
from app.modules.settings.models import DEFAULT_ATTRITION

SAMPLE_NOTE = "SAMPLE DATA: created by the seed script for demonstration. Safe to delete."

LOCATIONS: list[tuple[str, str, LocationKind, str | None]] = [
    ("STORES", "Main stores", LocationKind.STORES, None),
    ("STORES-A1", "Stores rack A, bin 1", LocationKind.BIN, "STORES"),
    ("STORES-A2", "Stores rack A, bin 2", LocationKind.BIN, "STORES"),
    ("MSL-DRY-1", "MSL dry cabinet 1", LocationKind.MSL_CABINET, None),
    ("WIP", "Production WIP", LocationKind.WIP, None),
    ("QUAR", "Quarantine", LocationKind.QUARANTINE, None),
    ("SCRAP", "Scrap", LocationKind.SCRAP, None),
]

VENDORS: list[dict[str, object]] = [
    {
        "code": "V-SAMPLE-01",
        "name": "Shree Ganesh Electronic Components (Sample)",
        "gstin": "27AABCS1234F1Z5",
        "city": "Mumbai",
        "state": "Maharashtra",
        "payment_terms": "30 days",
        "lead_time_days": 7,
        "rating": Decimal("4.2"),
    },
    {
        "code": "V-SAMPLE-02",
        "name": "Lakshmi Semiconductor Distributors (Sample)",
        "gstin": "29AAECL5678K1Z2",
        "city": "Bengaluru",
        "state": "Karnataka",
        "payment_terms": "45 days",
        "lead_time_days": 14,
        "rating": Decimal("4.6"),
    },
    {
        "code": "V-SAMPLE-03",
        "name": "Kaveri PCB Fabricators (Sample)",
        "gstin": "33AAGCK9012M1Z8",
        "city": "Chennai",
        "state": "Tamil Nadu",
        "payment_terms": "50% advance, 50% on delivery",
        "lead_time_days": 10,
        "rating": Decimal("3.9"),
    },
    {
        "code": "V-SAMPLE-04",
        "name": "Narmada Connectors and Cables (Sample)",
        "gstin": "24AAFCN3456P1Z1",
        "city": "Ahmedabad",
        "state": "Gujarat",
        "payment_terms": "30 days",
        "lead_time_days": 5,
        "rating": Decimal("4.0"),
    },
    {
        "code": "V-SAMPLE-05",
        "name": "Deccan Electro Mechanical Supplies (Sample)",
        "gstin": "36AAHCD7890Q1Z4",
        "city": "Hyderabad",
        "state": "Telangana",
        "payment_terms": "Net 60",
        "lead_time_days": 21,
        "rating": Decimal("3.5"),
    },
]

# (mpn, manufacturer, description, package, value, category, msl)
PARTS: list[tuple[str, str, str, str, str | None, PartCategory, int | None]] = [
    (
        "GRM188R71H104KA93D",
        "Murata",
        "Cap MLCC 100nF 50V X7R",
        "0603",
        "100nF",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "GRM188R61E105KA12D",
        "Murata",
        "Cap MLCC 1uF 25V X5R",
        "0603",
        "1uF",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "GRM21BR61E106KA73L",
        "Murata",
        "Cap MLCC 10uF 25V X5R",
        "0805",
        "10uF",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "GRM1885C1H220JA01D",
        "Murata",
        "Cap MLCC 22pF 50V C0G",
        "0603",
        "22pF",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "CL10A475KO8NNNC",
        "Samsung Electro-Mechanics",
        "Cap MLCC 4.7uF 16V X5R",
        "0603",
        "4.7uF",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "CL21A226MAQNNNE",
        "Samsung Electro-Mechanics",
        "Cap MLCC 22uF 25V X5R",
        "0805",
        "22uF",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "C0603C103K5RACTU",
        "KEMET",
        "Cap MLCC 10nF 50V X7R",
        "0603",
        "10nF",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "EEE-FK1V101P",
        "Panasonic",
        "Cap Alu Elec 100uF 35V SMD",
        "SMD-6.3x7.7",
        "100uF",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "T491A106K016AT",
        "KEMET",
        "Cap Tantalum 10uF 16V",
        "3216-18",
        "10uF",
        PartCategory.PASSIVE,
        None,
    ),
    ("RC0603FR-0710KL", "Yageo", "Res 10k 1% 0.1W", "0603", "10k", PartCategory.PASSIVE, None),
    ("RC0603FR-071KL", "Yageo", "Res 1k 1% 0.1W", "0603", "1k", PartCategory.PASSIVE, None),
    ("RC0603FR-07100RL", "Yageo", "Res 100R 1% 0.1W", "0603", "100R", PartCategory.PASSIVE, None),
    ("RC0603FR-074K7L", "Yageo", "Res 4.7k 1% 0.1W", "0603", "4.7k", PartCategory.PASSIVE, None),
    ("RC0603FR-0722RL", "Yageo", "Res 22R 1% 0.1W", "0603", "22R", PartCategory.PASSIVE, None),
    ("RC0603JR-070RL", "Yageo", "Res 0R jumper", "0603", "0R", PartCategory.PASSIVE, None),
    ("ERJ-3EKF1003V", "Panasonic", "Res 100k 1% 0.1W", "0603", "100k", PartCategory.PASSIVE, None),
    (
        "ERJ-6ENF4701V",
        "Panasonic",
        "Res 4.7k 1% 0.125W",
        "0805",
        "4.7k",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "CRCW060349K9FKEA",
        "Vishay",
        "Res 49.9k 1% 0.1W",
        "0603",
        "49.9k",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "WSL2512R0100FEA",
        "Vishay",
        "Res current sense 10mR 1% 1W",
        "2512",
        "10mR",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "BLM18PG221SN1D",
        "Murata",
        "Ferrite bead 220R@100MHz 1.4A",
        "0603",
        "220R",
        PartCategory.PASSIVE,
        None,
    ),
    (
        "STM32F407VGT6",
        "STMicroelectronics",
        "MCU ARM Cortex-M4 1MB Flash 168MHz",
        "LQFP-100",
        None,
        PartCategory.IC,
        3,
    ),
    (
        "STM32G431CBT6",
        "STMicroelectronics",
        "MCU ARM Cortex-M4 128KB Flash 170MHz",
        "LQFP-48",
        None,
        PartCategory.IC,
        3,
    ),
    (
        "ESP32-WROOM-32E-N8",
        "Espressif",
        "Wi-Fi/BT module 8MB flash",
        "Module",
        None,
        PartCategory.IC,
        3,
    ),
    ("ATMEGA328P-AU", "Microchip", "MCU AVR 32KB Flash", "TQFP-32", None, PartCategory.IC, 3),
    (
        "TPS54331DR",
        "Texas Instruments",
        "Buck converter 3.5-28V 3A",
        "SOIC-8",
        None,
        PartCategory.IC,
        1,
    ),
    (
        "TPS62162DSGR",
        "Texas Instruments",
        "Buck converter 3-17V 1A",
        "WSON-8",
        None,
        PartCategory.IC,
        2,
    ),
    (
        "AMS1117-3.3",
        "Advanced Monolithic Systems",
        "LDO 3.3V 1A",
        "SOT-223",
        None,
        PartCategory.IC,
        1,
    ),
    ("LM317DCYR", "Texas Instruments", "Adjustable LDO 1.5A", "SOT-223", None, PartCategory.IC, 2),
    ("MCP2551-I/SN", "Microchip", "CAN transceiver 1Mbps", "SOIC-8", None, PartCategory.IC, 1),
    (
        "MAX3485ESA+",
        "Analog Devices",
        "RS-485 transceiver 3.3V",
        "SOIC-8",
        None,
        PartCategory.IC,
        1,
    ),
    (
        "SN65HVD230DR",
        "Texas Instruments",
        "CAN transceiver 3.3V",
        "SOIC-8",
        None,
        PartCategory.IC,
        1,
    ),
    ("FT232RL-REEL", "FTDI", "USB to UART bridge", "SSOP-28", None, PartCategory.IC, 3),
    ("CH340C", "WCH", "USB to UART bridge, internal clock", "SOIC-16", None, PartCategory.IC, 3),
    ("W25Q64JVSSIQ", "Winbond", "SPI NOR flash 64Mbit", "SOIC-8", None, PartCategory.IC, 1),
    ("24LC256-I/SN", "Microchip", "I2C EEPROM 256Kbit", "SOIC-8", None, PartCategory.IC, 1),
    (
        "ADS1115IDGSR",
        "Texas Instruments",
        "16-bit ADC 4ch I2C",
        "VSSOP-10",
        None,
        PartCategory.IC,
        2,
    ),
    ("LM358DR", "Texas Instruments", "Dual op-amp", "SOIC-8", None, PartCategory.IC, 1),
    (
        "INA219AIDR",
        "Texas Instruments",
        "Current/power monitor I2C",
        "SOIC-8",
        None,
        PartCategory.IC,
        2,
    ),
    (
        "USBLC6-2SC6",
        "STMicroelectronics",
        "USB ESD protection",
        "SOT-23-6",
        None,
        PartCategory.IC,
        1,
    ),
    (
        "ULN2003ADR",
        "Texas Instruments",
        "Darlington array 7ch",
        "SOIC-16",
        None,
        PartCategory.IC,
        1,
    ),
    ("BSS138", "onsemi", "N-MOSFET 50V 200mA", "SOT-23", None, PartCategory.DISCRETE, 1),
    ("AO3401A", "Alpha & Omega", "P-MOSFET -30V -4A", "SOT-23", None, PartCategory.DISCRETE, 1),
    ("IRLML6344TRPBF", "Infineon", "N-MOSFET 30V 5A", "SOT-23", None, PartCategory.DISCRETE, 1),
    (
        "MMBT3904LT1G",
        "onsemi",
        "NPN transistor 40V 200mA",
        "SOT-23",
        None,
        PartCategory.DISCRETE,
        1,
    ),
    ("SS34", "MDD", "Schottky diode 40V 3A", "SMA", None, PartCategory.DISCRETE, 1),
    ("1N4148W-7-F", "Diodes Inc", "Switching diode 75V", "SOD-123", None, PartCategory.DISCRETE, 1),
    ("SMBJ24A", "Littelfuse", "TVS diode 24V 600W", "SMB", None, PartCategory.DISCRETE, 1),
    ("LTST-C191KGKT", "Lite-On", "LED green 0603", "0603", None, PartCategory.OPTO, None),
    ("LTST-C191KRKT", "Lite-On", "LED red 0603", "0603", None, PartCategory.OPTO, None),
    (
        "PC817X2NIP1B",
        "Sharp",
        "Optocoupler transistor output",
        "DIP-4",
        None,
        PartCategory.OPTO,
        None,
    ),
    (
        "ABM8-8.000MHZ-B2-T",
        "Abracon",
        "Crystal 8MHz 18pF",
        "3.2x2.5mm",
        "8MHz",
        PartCategory.CRYSTAL,
        None,
    ),
    (
        "ABS07-32.768KHZ-T",
        "Abracon",
        "Crystal 32.768kHz",
        "3.2x1.5mm",
        "32.768kHz",
        PartCategory.CRYSTAL,
        None,
    ),
    (
        "SRR1260-100M",
        "Bourns",
        "Power inductor 10uH 4.4A",
        "12x12mm",
        "10uH",
        PartCategory.MAGNETICS,
        None,
    ),
    (
        "LQH3NPN4R7MM0L",
        "Murata",
        "Power inductor 4.7uH 1.1A",
        "1212",
        "4.7uH",
        PartCategory.MAGNETICS,
        None,
    ),
    (
        "61300511121",
        "Würth Elektronik",
        "Pin header 1x5 2.54mm",
        "THT",
        None,
        PartCategory.CONNECTOR,
        None,
    ),
    (
        "61201021621",
        "Würth Elektronik",
        "Box header 2x5 2.54mm",
        "THT",
        None,
        PartCategory.CONNECTOR,
        None,
    ),
    (
        "10118194-0001LF",
        "Amphenol",
        "Micro USB-B receptacle",
        "SMD",
        None,
        PartCategory.CONNECTOR,
        None,
    ),
    (
        "1757255",
        "Phoenix Contact",
        "Terminal block 3-pos 5.08mm",
        "THT",
        None,
        PartCategory.CONNECTOR,
        None,
    ),
    ("B4B-XH-A(LF)(SN)", "JST", "XH header 4-pos 2.5mm", "THT", None, PartCategory.CONNECTOR, None),
    (
        "TS-1187A-B-A-B",
        "XKB",
        "Tactile switch 5.1x5.1mm",
        "SMD",
        None,
        PartCategory.ELECTROMECHANICAL,
        None,
    ),
]

# division code -> (name, description)
DIVISIONS = {
    "IND-AUTO": (
        "Industrial Automation (Sample)",
        "Controllers and I/O modules for factory automation.",
    ),
    "PWR-SYS": ("Power Systems (Sample)", "Power conversion and battery management boards."),
}

# (division, name, client, client_po, start, due, status, modules)
#   module: (code, name, qty, [(assembly code, board name, rev, layers, x, y, finish)])
PROJECTS = [
    (
        "IND-AUTO",
        "PLC I/O Expansion Rack",
        "Sahyadri Process Controls (Sample client)",
        "SPC/PO/2026/118",
        date(2026, 9, 1),
        date(2026, 12, 15),
        ProjectStatus.ACTIVE,
        [
            (
                "MOD-CPU",
                "CPU module",
                25,
                [("CPU1", "PLC CPU board", "B", 4, "100.00", "80.00", "ENIG")],
            ),
            (
                "MOD-DIO",
                "16-channel digital I/O module",
                50,
                [("DIO16", "Digital I/O board", "A", 2, "100.00", "60.00", "HASL lead-free")],
            ),
        ],
    ),
    (
        "IND-AUTO",
        "Conveyor Motor Controller",
        "Godavari Packaging Machines (Sample client)",
        "GPM-4471",
        date(2026, 10, 5),
        date(2027, 1, 31),
        ProjectStatus.DRAFT,
        [
            (
                "MOD-MC",
                "Motor controller unit",
                40,
                [
                    ("MCB", "Motor control board", "A", 4, "120.00", "90.00", "ENIG"),
                    ("HMI", "Operator panel board", "A", 2, "80.00", "50.00", "HASL lead-free"),
                ],
            ),
        ],
    ),
    (
        "PWR-SYS",
        "Battery Management System 48V",
        "Konkan E-Mobility (Sample client)",
        "KEM/2026/BMS/07",
        date(2026, 8, 20),
        date(2026, 11, 30),
        ProjectStatus.ACTIVE,
        [
            (
                "MOD-BMS",
                "BMS master unit",
                100,
                [("BMS16S", "16S BMS main board", "C", 6, "150.00", "100.00", "ENIG")],
            ),
        ],
    ),
]


async def _exists(session: AsyncSession, model: type, **filters: object) -> bool:
    stmt = select(func.count()).select_from(model)
    for key, value in filters.items():
        stmt = stmt.where(getattr(model, key) == value)
    return bool((await session.execute(stmt)).scalar_one())


async def seed_reference_data(session: AsyncSession) -> int:
    created = 0
    by_code: dict[str, InventoryLocation] = {}
    for code, name, kind, parent in LOCATIONS:
        existing = (
            await session.execute(select(InventoryLocation).where(InventoryLocation.code == code))
        ).scalar_one_or_none()
        if existing is None:
            existing = InventoryLocation(
                code=code,
                name=name,
                kind=kind.value,
                parent_id=by_code[parent].id if parent else None,
            )
            session.add(existing)
            await session.flush()
            created += 1
        by_code[code] = existing

    if not await _exists(session, StageTemplate, name="Standard PCBA"):
        template = StageTemplate(
            name="Standard PCBA", description="Default stage list from CLAUDE.md", is_default=True
        )
        session.add(template)
        await session.flush()
        for seq, (code, name, requires_qc) in enumerate(DEFAULT_STAGES, start=1):
            session.add(
                StageTemplateStep(
                    template_id=template.id,
                    seq=seq,
                    stage_code=code.value,
                    name=name,
                    requires_qc=requires_qc,
                )
            )
            created += 1
        created += 1
        await session.flush()
    return created


async def seed_sample_data(session: AsyncSession) -> int:
    if await _exists(session, Division, is_sample=True):
        return 0
    created = 0

    vendors: list[Vendor] = []
    for spec in VENDORS:
        vendor = Vendor(
            **spec,
            contacts=[
                {"name": "Sales desk", "phone": "+91 00000 00000", "email": "sales@example.invalid"}
            ],
            notes=SAMPLE_NOTE,
            is_sample=True,
        )
        session.add(vendor)
        vendors.append(vendor)
    await session.flush()
    created += len(vendors)

    for i, (mpn, mfr, desc, pkg, value, cat, msl) in enumerate(PARTS):
        part = Part(
            mpn=mpn,
            manufacturer=mfr,
            description=desc,
            package=pkg,
            value=value,
            category=cat.value,
            unit="pcs",
            msl_level=msl,
            notes=SAMPLE_NOTE,
            is_sample=True,
        )
        session.add(part)
        await session.flush()
        session.add(
            PartPreferredVendor(part_id=part.id, vendor_id=vendors[i % len(vendors)].id, rank=1)
        )
        created += 2

    template_id = (
        (await session.execute(select(StageTemplate.id).where(StageTemplate.is_default.is_(True))))
        .scalars()
        .first()
    )

    divisions: dict[str, Division] = {}
    for code, (name, description) in DIVISIONS.items():
        divisions[code] = Division(code=code, name=name, description=description, is_sample=True)
        session.add(divisions[code])
    await session.flush()
    created += len(divisions)

    for div, name, client, po, start, due, status, modules in PROJECTS:
        project = Project(
            division_id=divisions[div].id,
            code=await next_number(session, "PRJ"),
            name=name,
            client_name=client,
            client_po_ref=po,
            start_date=start,
            due_date=due,
            status=status.value,
            notes=SAMPLE_NOTE,
            is_sample=True,
        )
        session.add(project)
        await session.flush()
        created += 1
        for mcode, mname, qty, assemblies in modules:
            module = Module(project_id=project.id, code=mcode, name=mname, qty_to_deliver=qty)
            session.add(module)
            await session.flush()
            created += 1
            for acode, board, rev, layers, x, y, finish in assemblies:
                session.add(
                    PcbAssembly(
                        module_id=module.id,
                        code=acode,
                        board_name=board,
                        revision=rev,
                        layer_count=layers,
                        size_x_mm=Decimal(x),
                        size_y_mm=Decimal(y),
                        finish=finish,
                        stage_template_id=template_id,
                    )
                )
                created += 1
    await session.flush()
    return created


SAMPLE_BOQ_NAME = "PLC CPU board BOM (Sample)"

# (MPN, ref des, qty per unit, DNP) for revision A of the sample BOQ.
SAMPLE_BOQ_A: list[tuple[str, str, int, bool]] = [
    ("GRM188R71H104KA93D", "C1-C8", 8, False),
    ("GRM21BR61E106KA73L", "C9,C10", 2, False),
    ("GRM1885C1H220JA01D", "C11,C12", 2, False),
    ("RC0603FR-0710KL", "R1-R6", 6, False),
    ("RC0603FR-071KL", "R7,R8", 2, False),
    ("RC0603FR-074K7L", "R9-R12", 4, False),
    ("BLM18PG221SN1D", "FB1", 1, False),
    ("STM32F407VGT6", "U1", 1, False),
    ("AMS1117-3.3", "U2", 1, False),
    ("MCP2551-I/SN", "U3", 1, False),
    ("RC0603JR-070RL", "R13", 1, True),
]


async def seed_sample_boqs(session: AsyncSession) -> int:
    """One sample BOQ on the sample PLC rack's CPU board. Revision B differs from A by a
    quantity change (C1-C10), a substituted part (R9-R12), a removed DNP line (R13) and an
    added line (U4)."""
    if await _exists(session, Boq, name=SAMPLE_BOQ_NAME):
        return 0
    row = (
        await session.execute(
            select(Project, Module, PcbAssembly)
            .join(Module, Module.project_id == Project.id)
            .join(PcbAssembly, PcbAssembly.module_id == Module.id)
            .where(
                Project.is_sample.is_(True), Module.code == "MOD-CPU", PcbAssembly.code == "CPU1"
            )
        )
    ).first()
    if row is None:  # sample structure not loaded (or deleted): nothing to attach to
        return 0
    project, module, assembly = row
    parts = {
        p.mpn: p
        for p in (await session.execute(select(Part).where(Part.is_sample.is_(True)))).scalars()
    }
    boq = Boq(
        project_id=project.id,
        module_id=module.id,
        assembly_id=assembly.id,
        name=SAMPLE_BOQ_NAME,
        notes=SAMPLE_NOTE,
    )
    session.add(boq)
    await session.flush()
    keys = {mpn: uuid7().hex for mpn, *_ in SAMPLE_BOQ_A}

    def lines(rev: BoqRevision, spec: list[tuple[str, str, int, bool, str]]) -> list[BoqLine]:
        out = []
        for no, (mpn, ref, qty, dnp, key) in enumerate(spec, start=1):
            part = parts[mpn]
            out.append(
                BoqLine(
                    revision_id=rev.id,
                    line_key=key,
                    line_no=no,
                    part_id=part.id,
                    ref_des=",".join(split_ref_des(ref)),
                    qty_per_unit=Decimal(qty),
                    mpn=part.mpn,
                    manufacturer=part.manufacturer,
                    description=part.description,
                    value=part.value,
                    package=part.package,
                    category=part.category,
                    unit=part.unit,
                    dnp=dnp,
                    attrition_pct=Decimal(str(DEFAULT_ATTRITION.get(part.category, 0))),
                )
            )
        return out

    rev_a = BoqRevision(
        boq_id=boq.id,
        revision="A",
        status=RevisionStatus.RELEASED.value,
        build_qty=module.qty_to_deliver,
        released_at=utcnow(),
        attrition_by_category=dict(DEFAULT_ATTRITION),
        notes="Sample: as received from the client.",
    )
    rev_b = BoqRevision(
        boq_id=boq.id,
        revision="B",
        status=RevisionStatus.DRAFT.value,
        build_qty=module.qty_to_deliver,
        attrition_by_category=dict(DEFAULT_ATTRITION),
        notes="Sample: client ECO 7 (extra decoupling, CAN-to-RS-485 option).",
    )
    session.add_all([rev_a, rev_b])
    await session.flush()
    spec_a = [(m, r, q, d, keys[m]) for m, r, q, d in SAMPLE_BOQ_A]
    spec_b: list[tuple[str, str, int, bool, str]] = []
    for mpn, ref, qty, dnp, key in spec_a:
        if mpn == "GRM188R71H104KA93D":
            spec_b.append((mpn, "C1-C10", 10, dnp, key))
        elif mpn == "RC0603FR-074K7L":
            spec_b.append(("ERJ-6ENF4701V", ref, qty, dnp, key))
        elif mpn != "RC0603JR-070RL":
            spec_b.append((mpn, ref, qty, dnp, key))
    spec_b.append(("MAX3485ESA+", "U4", 1, False, uuid7().hex))
    new = lines(rev_a, spec_a) + lines(rev_b, spec_b)
    session.add_all(new)
    await session.flush()
    return 3 + len(new)

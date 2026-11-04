"""factory_boy factories. Build objects with factory_boy, persist with ``create``."""

import itertools
from datetime import date
from decimal import Decimal
from typing import Any, TypeVar

import factory
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boq.models import Boq, BoqLine, BoqRevision
from app.modules.inventory.models import InventoryLocation, LocationKind
from app.modules.org.models import BuildLot, Division, Module, PcbAssembly, Project, SerialUnit
from app.modules.parts.models import Part
from app.modules.procurement.models import GoodsReceipt, GrnLine, PoLine, PurchaseOrder, Vendor

T = TypeVar("T")
_seq = itertools.count(1)


def uniq(prefix: str) -> str:
    return f"{prefix}-{next(_seq):05d}"


async def create(session: AsyncSession, factory_cls: type[factory.Factory], **kwargs: Any) -> Any:
    obj = factory_cls.build(**kwargs)
    session.add(obj)
    await session.flush()
    return obj


class DivisionFactory(factory.Factory):
    class Meta:
        model = Division

    code = factory.LazyFunction(lambda: uniq("DIV"))
    name = factory.Faker("company")


class ProjectFactory(factory.Factory):
    class Meta:
        model = Project

    code = factory.LazyFunction(lambda: uniq("PRJ"))
    name = "Test project"
    client_name = "Test client"
    start_date = date(2026, 1, 1)
    due_date = date(2026, 6, 30)
    status = "active"


class ModuleFactory(factory.Factory):
    class Meta:
        model = Module

    code = factory.LazyFunction(lambda: uniq("MOD"))
    name = "Module"
    qty_to_deliver = 10


class AssemblyFactory(factory.Factory):
    class Meta:
        model = PcbAssembly

    code = factory.LazyFunction(lambda: uniq("ASM"))
    board_name = "Board"
    revision = "A"
    layer_count = 4


class LotFactory(factory.Factory):
    class Meta:
        model = BuildLot

    lot_number = factory.LazyFunction(lambda: uniq("LOT"))
    qty = 10


class SerialFactory(factory.Factory):
    class Meta:
        model = SerialUnit

    serial_number = factory.LazyFunction(lambda: uniq("SN"))


class PartFactory(factory.Factory):
    class Meta:
        model = Part

    mpn = factory.LazyFunction(lambda: uniq("MPN"))
    manufacturer = "Acme"
    description = "Test part"
    category = "Passive"


class VendorFactory(factory.Factory):
    class Meta:
        model = Vendor

    code = factory.LazyFunction(lambda: uniq("V"))
    name = "Test vendor"


class LocationFactory(factory.Factory):
    class Meta:
        model = InventoryLocation

    code = factory.LazyFunction(lambda: uniq("LOC"))
    name = "Location"
    kind = LocationKind.STORES.value


class PurchaseOrderFactory(factory.Factory):
    class Meta:
        model = PurchaseOrder

    number = factory.LazyFunction(lambda: uniq("PO"))


class PoLineFactory(factory.Factory):
    class Meta:
        model = PoLine

    line_no = factory.LazyFunction(lambda: next(_seq))
    qty_ordered = Decimal(100)


class BoqFactory(factory.Factory):
    class Meta:
        model = Boq

    name = factory.LazyFunction(lambda: uniq("BOQ"))


class BoqRevisionFactory(factory.Factory):
    class Meta:
        model = BoqRevision

    revision = "A"
    build_qty = 10


class BoqLineFactory(factory.Factory):
    class Meta:
        model = BoqLine

    line_key = factory.LazyFunction(lambda: uniq("LK"))
    line_no = factory.LazyFunction(lambda: next(_seq))
    qty_per_unit = Decimal(1)


class GoodsReceiptFactory(factory.Factory):
    class Meta:
        model = GoodsReceipt

    number = factory.LazyFunction(lambda: uniq("GRN"))


class GrnLineFactory(factory.Factory):
    class Meta:
        model = GrnLine

    qty_received = Decimal(10)
    qty_accepted = Decimal(10)


async def project_tree(session: AsyncSession) -> dict[str, Any]:
    """Division -> project -> module -> assembly, persisted."""
    division = await create(session, DivisionFactory)
    project = await create(session, ProjectFactory, division_id=division.id)
    module = await create(session, ModuleFactory, project_id=project.id)
    assembly = await create(session, AssemblyFactory, module_id=module.id)
    return {"division": division, "project": project, "module": module, "assembly": assembly}

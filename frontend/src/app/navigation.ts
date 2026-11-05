import type { LucideIcon } from "lucide-react";
import {
  Boxes,
  CircuitBoard,
  ClipboardCheck,
  Factory,
  FileText,
  FolderKanban,
  LayoutDashboard,
  ListChecks,
  Settings,
  ShoppingCart,
  Warehouse,
} from "lucide-react";

export interface NavItem {
  id: string;
  label: string;
  to: string;
  icon: LucideIcon;
  /** Roadmap phase that delivers the feature (see docs/roadmap/phases.md). */
  phase: number;
  summary: string;
}

export const NAV_ITEMS: NavItem[] = [
  { id: "dashboard", label: "Dashboard", to: "/", icon: LayoutDashboard, phase: 13, summary: "Role-aware KPIs, my tasks and project health." },
  { id: "projects", label: "Projects", to: "/projects", icon: FolderKanban, phase: 4, summary: "Divisions, projects, modules and PCB assemblies." },
  { id: "boq", label: "BOQ", to: "/boq", icon: ListChecks, phase: 5, summary: "Bills of quantity with CSV/XLSX import, revisions and compare." },
  { id: "procurement", label: "Procurement", to: "/procurement", icon: ShoppingCart, phase: 6, summary: "Requisitions, purchase orders, goods receipts and the pending tracker." },
  { id: "inventory", label: "Inventory", to: "/inventory", icon: Warehouse, phase: 6, summary: "Locations, stock on hand from the ledger, transfers and reservations." },
  { id: "production", label: "Production", to: "/production", icon: Factory, phase: 7, summary: "Work orders, kitting, serialisation and shop-floor stage tracking." },
  { id: "qc", label: "QC", to: "/qc", icon: ClipboardCheck, phase: 8, summary: "Checklists, photo evidence, NCRs and dispositions." },
  { id: "reports", label: "Reports", to: "/reports", icon: Boxes, phase: 10, summary: "One-click client QC reports with hash verification." },
  { id: "documents", label: "Documents", to: "/documents", icon: FileText, phase: 11, summary: "LLM-assisted drafting of manufacturing documents." },
  { id: "design-lab", label: "Design Lab", to: "/design-lab", icon: CircuitBoard, phase: 12, summary: "KiCad ERC/DRC, DFM checks and ngspice simulation." },
  { id: "settings", label: "Settings", to: "/settings", icon: Settings, phase: 3, summary: "Users, roles, document numbering and AI models." },
];

export type Role =
  | "admin"
  | "project_manager"
  | "purchase"
  | "stores"
  | "production"
  | "qc_inspector"
  | "qc_lead"
  | "engineer"
  | "viewer";

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Admin",
  project_manager: "Project Manager",
  purchase: "Purchase",
  stores: "Stores",
  production: "Production",
  qc_inspector: "QC Inspector",
  qc_lead: "QC Lead",
  engineer: "Engineer",
  viewer: "Viewer (client)",
};

export interface Scope {
  scope_type: "division" | "project";
  scope_id: string;
}

export interface Me {
  id: string;
  username: string;
  full_name: string;
  email: string | null;
  roles: Role[];
  permissions: string[];
  scopes: Scope[];
  must_change_password: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: Me;
}

export interface Numbering {
  doc_type: string;
  description: string;
  prefix: string;
  padding: number;
  yearly_reset: boolean;
  example: string;
}

export interface SetupStatus {
  needs_setup: boolean;
  data_dir: { path: string; exists: boolean; writable: boolean; free_bytes: number | null; ok: boolean; detail: string | null };
  numbering: Numbering[];
}

export interface Branding {
  company_name: string | null;
  has_logo: boolean;
  logo_url: string | null;
  setup_complete: boolean;
}

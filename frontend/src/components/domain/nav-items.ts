import { ClipboardList, Columns3, Gauge, PlusCircle, Wrench } from "lucide-react";
import type { Role } from "@/lib/api/types";

export interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  allowed: Role[];
}

/** Navigation applicative — source unique pour la barre latérale et le tiroir mobile. */
export const NAV_ITEMS: NavItem[] = [
  {
    href: "/vehicules",
    label: "Suivi des véhicules",
    icon: Wrench,
    allowed: ["operatrice", "chauffeur", "administrateur", "atelier"],
  },
  {
    href: "/missions",
    label: "Mes missions",
    icon: ClipboardList,
    allowed: ["chauffeur", "administrateur"],
  },
  {
    href: "/fiches/nouvelle",
    label: "Nouvelle fiche d'achat",
    icon: PlusCircle,
    allowed: ["operatrice", "administrateur"],
  },
  {
    href: "/pipeline",
    label: "Pipeline",
    icon: Columns3,
    allowed: ["administrateur"],
  },
  {
    href: "/pilotage",
    label: "Tableau de bord",
    icon: Gauge,
    allowed: ["administrateur"],
  },
];
